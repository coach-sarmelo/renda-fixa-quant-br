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

> **Atenção:** o valor padrão de `--fonte` é `brapi`. Sem `BRAPI_TOKEN` a
> CLI falha com mensagem explícita (exit 1) — não há substituição
> silenciosa de fonte. Como o endpoint de renda fixa da brapi hoje exige
> plano pago (abaixo), use sempre `--fonte=oficial`.

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
aproximação D6 dá
du = round(170 × 252/365) = 117; PU = 1000/(1,105)^(117/252) = 954,70.
O PU oficial de 954,32 implica du oficial = 252·ln(1000/954,32)/ln(1,105) =
118,01 → **118 dias úteis reais** — 1 DU de diferença explica o erro.

### Limitação medida da aproximação D6 de dias úteis

O núcleo (`pu.calcular`, `src/rfquant/pricing/pu.py`) estima dias úteis por
D6 (dias corridos × 252/365 — ver [formulas.md](formulas.md)); o PU oficial
do Tesouro desconta pelos dias úteis **reais** do calendário brasileiro
(com feriados). O erro relativo do PU resultante **cresce com o prazo** —
medido na data-base 30/06/2026 (só 1 dos 5 LTNs fica dentro de 1e-3):

| Vencimento | Taxa compra | PU oficial | `pu.calcular` (D6) | Erro rel. | du D6 | du oficial* |
|---|---|---|---|---|---|---|
| 01/01/2027 | 13,78% | 937,01 | 936,5308 | 5,11e-4 | 128 | 127 |
| 01/01/2028 | 14,07% | 820,81 | 819,9533 | 1,04e-3 | 380 | 378 |
| 01/01/2029 | 14,25% | 718,25 | 715,9790 | 3,16e-3 | 632 | 626 |
| 01/01/2031 | 14,37% | 548,54 | 545,9246 | 4,77e-3 | 1136 | 1127 |
| 01/01/2032 | 14,42% | 478,48 | 476,1842 | 4,80e-3 | 1388 | 1379 |

\* du oficial = expoente implícito ao inverter o PU oficial
(du = 252·ln(1000/PU)/ln(1+y)) — chega a 9 DU de desvio no prazo de 5,5 anos.

É esse crescimento que motivou fixar a data-base da fixture de regressão em
15/07/2024 (a última com ≥ 3 LTNs de prazo curto suficiente). Corrigir a
raiz exige calendário real de feriados (hoje no radar, sem data); a
tolerância 1e-3 da regressão **não muda** e a fixture só é regravada quando
a fórmula de PU mudar (mesmo padrão de cabeçalho de auditoria).

### brapi.dev — não utilizável hoje (exige plano pago para renda fixa)

- **URL do endpoint de treasury:** https://brapi.dev/api/v2/treasury
- **Auth:** `BRAPI_TOKEN` obrigatório (401 sem token)
- **Paywall (verificado 2026-09-20, curl com token válido):** o endpoint de treasury/renda fixa é feature do **plano Pro (R$ 139,99/mês)** — com token autenticado de conta **Gratuita** a API responde `HTTP 403` com `{"error":true,"code":"FEATURE_NOT_AVAILABLE","details":{"feature":"canAccessFixedIncome","currentPlan":"free","requiredPlan":"pro"}}` (o fato de a resposta nomear o plano da conta prova que o token foi aceito).

Por isso a fonte documentada é a oficial (`--fonte=oficial`), que não
requer token nem assinatura. A integração brapi permanece registrada apenas
como **plano futuro** — se um dia for ativada, exigirá plano pago e será
documentada aqui.

## Indicadores macro (BCB SGS) — referência externa

- **BCB (SGS):** [https://api.bcb.gov.br/dados/serie/bcdata.sgs.{codigo}/dados](https://api.bcb.gov.br/dados/serie/bcdata.sgs.%7Bcodigo%7D/dados) — séries como Selic meta (432), CDI e IPCA, JSON sem autenticação.

Integrar essas séries como providers da ferramenta está no radar (ver
"Próximos passos"). Hoje elas não são consumidas pelo `rfquant`.

## Limitações conhecidas

| Fonte / cálculo | Limitação |
|---|---|
| brapi (conta gratuita) | Endpoint de renda fixa exige plano Pro (403 em conta gratuita) — integração é plano futuro; use `--fonte=oficial` |
| Debêntures | Não há API pública consolidada (ANBIMA requer assinatura) |
| CDB / LCI / LCA | Não há API centralizada; o usuário informa as taxas |
| Núcleo de pricing vs Tesouro | Dias úteis por D6 (252/365): erro do PU vs oficial cresce com o prazo — 5,11e-4 a 4,80e-3 nos 5 LTNs da data-base 30/06/2026 (seção "Limitação medida da aproximação D6"); calendário real de feriados está no radar |

## Próximos passos

- [ ] Calendário brasileiro real de feriados para dias úteis exatos (remove a limitação D6)
- [ ] Séries macro (Selic/CDI/IPCA) via SGS/BCB como providers
- [ ] Scraper do portal do Tesouro Direto como **fonte contingencial — planejada, não implementada** (só seria acionada se o CSV oficial deixasse de funcionar)
- [ ] Integração com ANBIMA para debêntures
- [ ] Adapter para OpenBB (`openbb-br` provider)
