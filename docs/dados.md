# Fontes de Dados

O `rfquant` usa fontes públicas brasileiras. Este documento descreve a
fonte em produção, por que ela foi escolhida e suas limitações medidas.

## Tesouro Direto — fonte oficial: Tesouro Transparente (CKAN)

- **Dataset:** `taxas-dos-titulos-ofertados-pelo-tesouro-direto`
- **URL do recurso (CSV):** https://www.tesourotransparente.gov.br/ckan/dataset/df56aa42-484a-4a59-8184-7676580c81e3/resource/796d2059-14e9-44e3-80c9-2d9e30b405c1/download/precotaxatesourodireto.csv
- **Descoberta via API CKAN:** `https://www.tesourotransparente.gov.br/ckan/api/3/action/package_show?id=taxas-dos-titulos-ofertados-pelo-tesouro-direto` (JSON, público)
- **Formato:** CSV `;` com decimais pt-BR (vírgula) e datas `DD/MM/AAAA` — colunas:
  `Tipo Titulo; Data Vencimento; Data Base; Taxa Compra Manha; Taxa Venda Manha; PU Compra Manha; PU Venda Manha; PU Base Manha`
- **Conteúdo:** histórico completo de taxas/PU (compra e venda, manhã) por `Data Base` diária desde 31/12/2004; ~14,5 MB / ~176k linhas (medido 2026-09-19)
- **Auth:** nenhuma · **Licença:** ODbL (Open Data Commons) · **Cadência:** diária (~10h)
- **Taxas em % a.a.** (ex.: `14,10` = 14,10% a.a. para Prefixado; `0,07` = 0,07% para Selic) — o parser confere a escala e converte para fração decimal
- **Cache local:** o provider (`TesouroOficialProvider`) reusa `rfquant.data.cache` (diskcache — SQLite por baixo), TTL de 24 h: o arquivo de 14,5 MB é baixado no máximo 1×/dia e o parsing filtra a `Data Base` de interesse

### Por que o CSV oficial (avaliação das alternativas, verificada com curl em 2026-09-19)

| Candidato | Resultado do probe | Veredito |
|---|---|---|
| Site do TD (`tesourodireto.com.br/json/.../titulosPublicos.json`) | HTTP 403 — desafio Cloudflare ("Just a moment...") para cliente não-browser | ✗ Evadir anti-bot é frágil e cinzento; descartado |
| **Tesouro Transparente CKAN (CSV)** | HTTP 200 `text/csv`, ODbL, diário, histórico desde 2004 | ✓ **Escolhido** (requisitos: público, sem token, ≥1 título) |
| SGS/BCB (`api.bcb.gov.br/dados/serie/bcdata.sgs.{n}/...`) | HTTP 200 JSON sem auth (ex.: série 432 Selic meta) | ✗ para títulos: serve **séries macro** (Selic/CDI/IPCA), não é fonte de títulos |
| Tesouro em Foco (`api.tesouroemfoco.com/v1`) | HTTP 200 `/v1/health`; OpenAPI público, sem auth | ✗ para fonte oficial: autodescrito como **simulação**, não é fonte do Tesouro |
| B3 Developers API | requer cadastro/token | ✗ viola "sem token" |
| brapi v2 `/api/v2/treasury` | HTTP 401 sem `BRAPI_TOKEN`; **HTTP 403 `FEATURE_NOT_AVAILABLE` com token válido de conta Gratuita** (verificado 2026-09-20) | ✗ para fonte sem token e ✗ com plano Gratuito (ver seção brapi abaixo) |

Em resumo: o CSV oficial do Tesouro Transparente é o único candidato que
satisfaz os três requisitos — público, sem cadastro/token e com os títulos
de que a ferramenta precisa — sem depender de anti-bot ou paywall.

### Uso na CLI

```bash
rfq tesouro listar --fonte=oficial                 # todos os títulos
rfq tesouro listar --fonte=oficial --tipo IPCA+    # filtro por tipo
rfq hoje                                           # resumo do dia
```

> **Atenção:** o valor padrão de `--fonte` é `auto` — mapa declarado em
> `rfquant.data.fontes`: títulos pela fonte oficial do Tesouro, CDI pela
> série 12 do SGS/BCB e fundos pelo informe diário da CVM, com a fonte
> usada anunciada na saída. O pino `--fonte=brapi` existe para
> reprodutibilidade e exige `BRAPI_TOKEN`: sem o token a CLI falha com
> mensagem explícita (exit 1) — não há substituição silenciosa de fonte.

### Fixture de regressão com valores oficiais

`tests/fixtures/tesouro_regressao_oficial.csv` é um excerto byte a byte do
mesmo CSV oficial CKAN (path acima), com as 5 linhas de LTN
(`Tesouro Prefixado`, zero-cupom) da **data-base 15/07/2024** e cabeçalho
`#` de auditoria (path, data-base, data de captura, schema, critério da
excisão).

**Escolha da data-base por medição** (nunca presumida): varredura do CSV
completo (176.390 linhas, 28.125 de LTN, todas as datas-base desde
31/12/2004) comparando `pu.calcular(data_base, venc, taxa_compra/100)` com
o `PU Compra Manha` oficial. A data-base 15/07/2024 é a **mais recente**
em que ≥ 3 LTNs ficam dentro da tolerância de regressão (erro relativo
≤ 1e-3) — depois dela, nenhuma data-base tem ≥ 3 LTNs na tolerância
(máximo 2).

Títulos da data-base 15/07/2024 (erro = |`pu.calcular` − PU oficial| / PU oficial):

| Vencimento | Taxa compra | PU oficial | `pu.calcular` | Erro rel. | ≤ 1e-3 |
|---|---|---|---|---|---|
| 01/01/2025 | 10,50% | 954,32 | 954,7013 | 4,00e-4 | ✓ |
| 01/01/2026 | 11,11% | 856,68 | 857,0464 | 4,28e-4 | ✓ |
| 01/01/2027 | 11,39% | 767,23 | 766,5801 | 8,47e-4 | ✓ |
| 01/01/2029 | 11,74% | 611,11 | 608,9637 | 3,51e-3 | ✗ |
| 01/01/2031 | 11,90% | 485,60 | 483,2308 | 4,88e-3 | ✗ |

Exemplo de derivação à mão (01/01/2025): dc = 170 dias corridos; a
aproximação (dias corridos × 252/365) dá
du = round(170 × 252/365) = 117; PU = 1000/(1,105)^(117/252) = 954,70.
O PU oficial de 954,32 implica du oficial = 252·ln(1000/954,32)/ln(1,105) =
118,01 → **118 dias úteis reais** — 1 DU de diferença explica o erro.

### Fixture de regressão da NTN-B (razão de PUs)

`tests/fixtures/tesouro_regressao_ntnb.csv` é um excerto byte a byte do
mesmo CSV oficial CKAN (path acima), capturado em 2026-10-06 (arquivo
inteiro: 177.028 linhas desde 31/12/2004 — 44.064 da NTN-B, 'Tesouro IPCA+
com Juros Semestrais', e 18.900 da NTN-B Principal, 'Tesouro IPCA+'). São
**16 linhas em 8 datas-base de 2024 a 2026** (15/02/2024, 14/08/2024,
10/03/2025, 14/08/2025, 13/02/2026, 14/05/2026, 30/06/2026 e 05/10/2026),
uma dupla por data-base — 12 NTN-B + 4 Principal — com prazos de 46 dias
corridos (NTN-B 15/08/2026 na base 30/06/2026) a 12.942 (NTN-B 15/08/2060
na base 10/03/2025) e 4 datas-base de véspera útil de cupom (14/08/2024,
14/08/2025, 14/05/2026 e 13/02/2026 — cupom de domingo 15/02, pagamento na
segunda 16/02).

**Por que a razão de PUs, e não o PU absoluto: o CSV não publica o VNA.** A
coluna 'PU Base Manha' é **igual a 'PU Venda Manha'** em 10.128/10.128
linhas IPCA+ do escopo 2024–2026 (16/16 da fixture) — é o PU do lado da
venda, não um valor nominal atualizado. Usá-la como VNA NÃO replica o PU
oficial: erro medido de 8,882e-3 a 8,156e-1 nas 16 linhas (mediana 1,148e-1;
0 de 691 datas-base a ≤ 1e-3 no escopo) — controle negativo do teste. O que
a fixture permite calibrar com verdade externa é a razão entre os dois lados
do spread:

$$\text{erro} = \frac{|PU_C/PU_V - \text{cot}_C/\text{cot}_V|}{PU_C/PU_V}$$

com as cotações sobre base 100 (cupom composto de 6% a.a., calendário real
de dias úteis, desconto a (1+r)^(du/252) pela taxa REAL) e a liquidação D+1
SÓ no numerador: nas vésperas úteis de cupom o oficial publica PU Compra SEM
o cupom da janela D+1 e PU Venda COM ele.

**Escolha das datas-base por medição** (nunca presumida): validação integral
do escopo 2024–2026 (6.237 linhas de NTN-B em 691 datas-base + 3.891 da
Principal). Nas 10.078 linhas sem cupom na janela D+1, a razão fecha com
mediana 4,165e-4, p95 8,343e-4 e máximo 2,595e-3 (98,1% ≤ 1e-3; 96,5% das
datas-base); nas 50 linhas D+1 (11 datas-base: 14/02, 14/05, 14/08 e 14/11
de 2024 e 2025, 13/02, 14/05 e 14/08 de 2026 — quando o cupom 15/xx cai no
fim de semana, a janela é a do pagamento útil), mediana 4,132e-4 e máximo
1,302e-3. Erros medidos na fixture (B = NTN-B, Pr = NTN-B Principal):

| Data-base | Dupla eleita | Erros rel. |
|---|---|---|
| 15/02/2024 | B 15/08/2026 (912 d) · B 15/08/2050 (9.678 d) | 4,747e-4 · 4,758e-4 |
| 14/08/2024 | B 15/08/2032 (véspera) · Pr 15/05/2035 | 3,447e-4 · 3,467e-4 |
| 10/03/2025 | B 15/08/2026 (523 d) · B 15/08/2060 (12.942 d) | 7,748e-4 · 7,387e-4 |
| 14/08/2025 | B 15/08/2030 (véspera) · Pr 15/08/2050 | 3,735e-4 · 3,501e-4 |
| 13/02/2026 | B 15/08/2026 (véspera, 183 d) · B 15/05/2055 | 1,082e-3 · 9,668e-4 |
| 14/05/2026 | B 15/05/2037 (véspera) · Pr 15/05/2029 | 5,063e-4 · 5,227e-4 |
| 30/06/2026 | B 15/08/2026 (46 d) · B 15/08/2060 | 5,384e-4 · 3,999e-4 |
| 05/10/2026 | B 15/08/2030 · Pr 15/05/2035 | 5,094e-4 · 5,040e-4 |

**Tolerância 5e-3** — ~4,6× o pior caso medido (1,082e-3) —, e não 1e-4 nem
1e-3, porque o resíduo do escopo tem viés multiplicativo de +4,18e-4 de
mediana (99,7% das linhas positivas; +6,25e-4 nas sextas) consistente com o
PU Venda oficial referenciado à data de liquidação — descontar o lado da
venda no próximo dia útil reduziria o viés a +1,35e-4. O viés é do oficial,
não do núcleo: absorvido na tolerância, não corrigido na fórmula.

**Controles negativos medidos** (o que a razão de fato discrimina): (i) o PU
Base como VNA — 8,882e-3 a 8,156e-1, as 16/16 linhas fora; (ii) nas 4
vésperas de cupom, o filtro D+1 nos DOIS lados (2,902e-2 a 3,275e-2) ou em
NENHUM (2,887e-2 a 3,245e-2), ambos ~6–7× a tolerância. O cupom LINEAR
(3,0 por semestre por 100 de VNA), que discrimina o PU absoluto da NTN-F,
NÃO discrimina a razão — medido 3,467e-4 a 1,501e-3, dentro de 5e-3: um
shift multiplicativo no cupom sobe numerador e denominador juntos.

A fixture só é regravada quando a fórmula de cotação/PU da NTN-B mudar
(mesmo padrão de cabeçalho de auditoria).

### Medição HISTÓRICA (pré-calendário real): erro da aproximação de dias úteis (252/365)

> **Registro histórico.** A medição abaixo foi feita quando o núcleo ainda
> estimava dias úteis por dias corridos × 252/365. **Hoje o núcleo usa o
> calendário real** B3/SFN (`rfquant.data.calendario`, feriados do
> `pandas-market-calendars` com adaptação documentada de meio período de
> fim de ano), validado a ±0 contra os dias úteis oficiais registrados
> nesta página e na bateria de calendário dos testes — ver
> [formulas.md](formulas.md). O trabalho de medição permanece preservado
> abaixo como o registro que motivou a mudança; não descreve o
> comportamento atual.

O núcleo (`pu.calcular`, `src/rfquant/pricing/pu.py`) estimava dias úteis
por dias corridos × 252/365; o PU oficial do Tesouro desconta pelos dias
úteis **reais** do calendário brasileiro (com feriados). O erro relativo
do PU resultante **crescia com o prazo** — medido na data-base 30/06/2026
(só 1 dos 5 LTNs ficava dentro de 1e-3):

| Vencimento | Taxa compra | PU oficial | `pu.calcular` (aprox. 252/365) | Erro rel. | du aprox. | du oficial* |
|---|---|---|---|---|---|---|
| 01/01/2027 | 13,78% | 937,01 | 936,5308 | 5,11e-4 | 128 | 127 |
| 01/01/2028 | 14,07% | 820,81 | 819,9533 | 1,04e-3 | 380 | 378 |
| 01/01/2029 | 14,25% | 718,25 | 715,9790 | 3,16e-3 | 632 | 626 |
| 01/01/2031 | 14,37% | 548,54 | 545,9246 | 4,77e-3 | 1136 | 1127 |
| 01/01/2032 | 14,42% | 478,48 | 476,1842 | 4,80e-3 | 1388 | 1379 |

\* du oficial = expoente implícito ao inverter o PU oficial
(du = 252·ln(1000/PU)/ln(1+y)) — chega a 9 DU de desvio no prazo de 5,5 anos.

Foi esse crescimento que motivou fixar a data-base da fixture de regressão
de LTN em 15/07/2024 (a última com ≥ 3 LTNs de prazo curto suficiente) e
que motivou o calendário real, hoje implementado. Com o calendário real e o
cupom composto STN/ANBIMA, os erros medidos caem para ≤ 1,7e-5 (os 5 LTNs)
e ≤ 9,39e-5 (NTN-F, pior caso = liquidação D+1) — as tolerâncias dos testes
de regressão foram apertadas ao erro medido: 1e-4 (LTN) e 5e-4 (NTN-F),
margem de ~5–6×. A fixture só é regravada quando a fórmula de PU muda
(mesmo padrão de cabeçalho de auditoria). A regressão NTN-F (9 datas-base
de 2026, `tests/fixtures/tesouro_regressao_ntnf.csv`) fecha dentro da
tolerância de 5e-4.

### brapi.dev — não utilizável hoje (exige plano pago para renda fixa)

- **URL do endpoint de treasury:** https://brapi.dev/api/v2/treasury
- **Auth:** `BRAPI_TOKEN` obrigatório (401 sem token)
- **Paywall (verificado 2026-09-20, curl com token válido):** o endpoint de treasury/renda fixa é feature do **plano Pro (R$ 139,99/mês)** — com token autenticado de conta **Gratuita** a API responde `HTTP 403` com `{"error":true,"code":"FEATURE_NOT_AVAILABLE","details":{"feature":"canAccessFixedIncome","currentPlan":"free","requiredPlan":"pro"}}` (o fato de a resposta nomear o plano da conta prova que o token foi aceito).

Por isso a fonte documentada é a oficial (`--fonte=oficial`), que não
requer token nem assinatura. A integração brapi permanece registrada apenas
como **plano futuro** — se um dia for ativada, exigirá plano pago e será
documentada aqui.

## Fundos de Investimento (CVM)

- **URL:** https://dados.cvm.gov.br/dataset/fi-doc-inf_diario
- **Paths padrão:** informe mensal em `/dados/FI/DOC/INF_DIARIO/DADOS/inf_diario_fi_YYYYMM.zip`; cadastro de fundos em `/dados/FI/CAD/DADOS/cad_fi.csv` (arquivo único; ainda não consumido pelo provider)
- **Tamanho medido (captura de 2026-09-23):** informe mensal ~11 MB/mês; cadastro `cad_fi.csv` ~17,1 MB
- **Formato:** ZIP → CSV (`;`, latin-1) no layout vigente de classes/subclasses da RCVM 175
- **Cobertura:** informes diários de fundos (cota, patrimônio líquido, captações, resgates, cotistas)
- **Janela:** últimos 12 meses + históricos anteriores
- **Cadência:** diária (D+1) — o ZIP mensal é atualizado a cada dia útil intramês e congela no fechamento do mês
- **Autenticação:** nenhuma

### Uso na CLI

```bash
rfq fundos resumo --cnpj 00.000.000/0000-00 --mes 2026-08
```

Resume a rentabilidade do fundo no mês em três números — acumulada do
período, anualizada (base 252, dias úteis do calendário real) e expressa
em % do CDI da mesma janela — direto do informe oficial da CVM, sem
token. O download do ZIP do mês (~11 MB) cai no cache em disco com TTL
de 24 h.

## Indicadores macro (BCB SGS) — referência externa

- **BCB (SGS):** [https://api.bcb.gov.br/dados/serie/bcdata.sgs.{codigo}/dados](https://api.bcb.gov.br/dados/serie/bcdata.sgs.%7Bcodigo%7D/dados) — séries como Selic meta (432), CDI e IPCA, JSON sem autenticação.

O `rfquant` já consome o CDI (série 12 do SGS, % ao dia) nos comandos
`comparar --cdi-auto` e `fundos resumo`; as demais séries (Selic meta,
IPCA) seguem apenas como referência externa, no radar de integração (ver
"Próximos passos").

## Limitações conhecidas

| Fonte / cálculo | Limitação |
|---|---|
| brapi (conta gratuita) | Endpoint de renda fixa exige plano Pro (403 em conta gratuita) — integração é plano futuro; use `--fonte=oficial` |
| CVM (CSV) | Arquivos grandes: informe mensal ~11 MB/mês e cadastro `cad_fi.csv` ~17,1 MB — baixados sob demanda, com cache em disco (TTL 24 h) |
| Debêntures | Não há API pública consolidada (ANBIMA requer assinatura) |
| CDB / LCI / LCA | Não há API centralizada; o usuário informa as taxas |
| Núcleo de pricing vs Tesouro | Usa o calendário real de dias úteis (`rfquant.data.calendario`). A medição do erro da antiga aproximação dias corridos × 252/365 (5,11e-4 a 4,80e-3 nos 5 LTNs da data-base 30/06/2026) está preservada como registro histórico na seção "Medição HISTÓRICA (pré-calendário real)" |

## Próximos passos

- [x] Calendário brasileiro real de feriados para dias úteis exatos — feito: o núcleo usa `rfquant.data.calendario` (a medição da antiga aproximação 252/365 permanece como registro histórico)
- [ ] Demais séries macro (Selic meta, IPCA) via SGS/BCB como providers
- [ ] Scraper do portal do Tesouro Direto como **fonte contingencial — planejada, não implementada** (só seria acionada se o CSV oficial deixasse de funcionar)
- [ ] Integração com ANBIMA para debêntures
- [ ] Adapter para OpenBB (`openbb-br` provider)
