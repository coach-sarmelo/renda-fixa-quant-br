# Fórmulas

A matemática de precificação e comparação implementada no `rfquant`, com
as convenções usadas e suas limitações. Cada seção corresponde a funções
reais do código (`src/rfquant/pricing/` e `src/rfquant/comparison/`).

## 1. Fluxo de caixa (cupom composto — padrão STN/ANBIMA)

`gerar_fluxos` (`pricing/fluxo_caixa.py`) monta os pagamentos futuros do
título:

- **Zero-cupom** (`taxa_cupom_anual = 0`): um único fluxo, o valor nominal
  no vencimento.
- **Com cupom** (`taxa_cupom_anual > 0`): cupons periódicos
  (`frequencia_cupom` por ano, padrão 2 = semestral) de

$$\text{cupom} = VN \times \left[(1 + i)^{1/f} - 1\right]$$

  mais o principal pago junto ao último cupom. A convenção do cupom é a
  **composta** do padrão STN/ANBIMA para títulos cupomados, e não a linear
  (`VN × i / f`). Numa NTN-F de 10% a.a. com cupom semestral, o cupom é
  R$ 48,81 (1000 × (1,10^(1/2) − 1) = 48,8088...), e não R$ 50,00.

## 2. Preço Unitário (PU)

$$PU = \sum_{t=1}^{n} \frac{FC_t}{(1 + y)^{du_t / 252}}$$

Onde:

- `FC_t` = fluxo de caixa no período `t` (cupom ou principal)
- `y` = taxa de desconto anual (deve ser > −100%; o código recusa valores
  menores ou iguais)
- `du_t` = dias úteis até o fluxo `t`, na base 252 do mercado brasileiro

**Liquidação D+1: cupom na janela sai do preço, resgate fica.** O PU
publicado pelo Tesouro pressupõe liquidação no próximo dia útil da
data-base: um CUPOM pago nessa janela pertence ao vendedor e não entra no
preço do comprador, mas o fluxo final de vencimento permanece embutido
mesmo na véspera (`pu.fluxos_liquidados`). Regra medida contra o oficial,
não assumida: em 27.275 linhas NTN-F do CSV oficial (2004–2026), os 162
casos em que a regra morde melhoram ~10× com o filtro (p.ex. 6,54e-3 vs
6,87e-2); os 64 casos de data-base na sexta com cupom na segunda provam que
a janela é D+1 **útil** (erros de 9e-6 a 9,7e-5 contra 4,9e-2 a 5,5e-2 sem o
filtro); na véspera do vencimento (30/06/2010, venc 01/07/2010) o oficial
mantém o resgate no PU (excluí-lo daria erro 1,0; mantendo, 3,75e-4). A
regressão NTN-F cobre o caso da véspera de cupom (30/06/2026: com o filtro,
erro de 3,24e-6 e 9,39e-5; sem, 4,97e-2).

**Dias úteis reais.** A contagem usa o calendário real B3/SFN
(`rfquant.data.calendario`), montado sobre os feriados do
`pandas-market-calendars` (calendário `'B3'`, consulta offline) com uma
adaptação documentada de meio período: os pregões de fim de ano
(24/12 e 31/12 e, quando 31/12 cai num fim de semana, a sexta anterior)
contam como dias úteis plenos, como no calendário do SFN usado no
desconto dos títulos públicos. A regra é validada a ±0 (nenhuma
tolerância) contra 10 casos oficiais (DU publicado e DU derivado dos PUs
oficiais do Tesouro), registrados em [dados.md](dados.md) e conferidos em
`tests/test_data_calendario.py`. A antiga aproximação
dias corridos × 252/365 não é mais usada no núcleo; a medição do erro
dela permanece em [dados.md](dados.md) como registro histórico.

Implementação: `pu.calcular` (`pricing/pu.py`) e `calendario.dias_uteis`
(`data/calendario.py`).

### NTN-B (Tesouro IPCA+): cotação e VNA

O Tesouro IPCA+ é negociado por uma **cotação em % do VNA** (Valor Nominal
Atualizado pelo IPCA); o PU pago na liquidação é reconstruído a partir do VNA
do dia. O módulo `ntnb` separa as duas camadas reutilizando a matemática
desta seção: os fluxos são gerados sobre a **base 100** e descontados pela
**taxa real** `r` (IPCA+ 6,2% a.a. → r = 0,062):

$$\text{cotação} = \sum_{t=1}^{n} \frac{FC_t^{(100)}}{(1 + r)^{du_t / 252}}$$

Os cupons da NTN-B são os semestrais compostos da seção 1 (6% a.a. →
**2,956301 por semestre por 100 de VNA**), mais o resgate de 100 no
vencimento, com as datas ancoradas no vencimento (venc 15/08 → cupons 15/02
e 15/08; venc 15/05 → 15/05 e 15/11). O PU em reais vem do VNA do dia:

$$PU = VNA \times \frac{\text{cotação}}{100}$$

A **NTN-B Principal** (sem cupons) é o caso `taxa_cupom_anual = 0`: a
cotação reduz à fórmula exata da STN, $100 / (1 + r)^{du/252}$.

A liquidação D+1 desta seção é herdada: `ntnb.cotacao` aplica
`pu.fluxos_liquidados`. O cupom pago na janela do próximo dia útil sai da
cotação. A regressão contra o oficial mediu os casos de data-base 15/xx no
fim de semana: a janela é a do **pagamento útil** (na sexta 13/02/2026, o
cupom de domingo 15/02 paga na segunda 16/02, e é ele que sai do preço).
Nas 4 datas-base de véspera útil de cupom da fixture, o oficial publica o
PU Compra SEM o cupom da janela e o PU Venda COM ele. É visível nos próprios
dados (13/02/2026, NTN-B 15/08/2026: PU Compra 4.518,23 < PU Venda 4.646,84
apesar da taxa de venda MAIOR).

**Evidência da regressão** (`tests/fixtures/tesouro_regressao_ntnb.csv`): o
CSV oficial não publica o VNA da NTN-B, então o confronto com a verdade
externa é pela **razão de PUs**, |PU_Compra/PU_Venda −
cot_compra/cot_venda| / (PU_Compra/PU_Venda), com o filtro D+1 só no
numerador. Nas 16 linhas (12 NTN-B + 4 NTN-B Principal) de 8 datas-base de
2024–2026, prazos de 46 a 12.942 dias corridos, o erro medido é de
**3,447e-4 a 1,082e-3** (15 de 16 ≤ 1e-3; a exceção é a sexta 13/02/2026, o
dia em que o viés do PU Venda oficial é maior). A tolerância é 5e-3 (~4,6× o
pior caso), e não mais apertada, porque o resíduo tem viés multiplicativo de
+4,2e-4 de mediana consistente com o PU Venda oficial referenciado à
liquidação; absorvido na tolerância, não corrigido na fórmula. Metodologia,
escolha por medição e controles negativos em [dados.md](dados.md).

Implementação: `ntnb.cotacao` (cotação em % do VNA) e `ntnb.calcular`
(PU = VNA × cotação/100), em `pricing/ntnb.py`. Na CLI, `rfq tesouro
precificar --vna <VNA_do_dia>` (com `--cupom 0.06` para a NTN-B e sem cupom
para a NTN-B Principal).

## 3. Duration de Macaulay

$$D_{mac} = \frac{\sum_{t=1}^{n} t_{anos} \cdot \frac{FC_t}{(1+y)^{t_{anos}}}}{PU}$$

O prazo médio ponderado dos fluxos de caixa, em anos, com
`t_anos = du_t / 252`. Implementação: `duration.macaulay`.

## 4. Duration Modificada

$$D_{mod} = \frac{D_{mac}}{1 + y}$$

Mede a sensibilidade do PU a variações na taxa:

$$\Delta PU \approx -D_{mod} \cdot \Delta y \cdot PU$$

Implementação: `duration.modificada`.

## 5. DV01 (Dollar Value of a Basis Point)

Variação absoluta do PU (em R$) para um choque de +1 ponto-base
(+0,01%) na taxa:

$$DV01 = \left|PU(y) - PU(y + 0{,}0001)\right|$$

Calculado por **re-precificação** (diferença finita). Captura a
não-linearidade preço × taxa que a aproximação linear ignora. Quando o PU
e a Duration Modificada já estão calculados, há a aproximação rápida:

$$DV01 \approx D_{mod} \cdot PU \cdot 0{,}0001$$

menos precisa para taxas altas ou prazos longos. Implementação:
`risco.dv01` (re-precificação) e `risco.dv01_rapido` (aproximação), em
`pricing/risco.py`.

## 6. Convexidade e variação de 2ª ordem

Curvatura da relação preço × taxa (segunda derivada normalizada pelo PU),
em forma fechada na convenção brasileira base 252:

$$C = \frac{1}{PU \cdot (1+y)^2} \sum_{t=1}^{n} t \cdot (t+1) \cdot \frac{FC_t}{(1+y)^t}$$

onde `t = du_t / 252` (prazo em anos). A convexidade corrige a
aproximação linear da duration, variação percentual do PU de 2ª ordem:

$$\frac{\Delta PU}{PU} \approx -D_{mod} \cdot \Delta y + \frac{1}{2} \cdot C \cdot (\Delta y)^2$$

Implementação: `risco.convexidade` e `risco.variacao_pu`
(`pricing/risco.py`).

## 7. Yield to Maturity (YTM)

Dado um PU de mercado, resolve-se a taxa que iguala preço e fluxos:

$$PU_{mercado} = \sum_{t=1}^{n} \frac{FC_t}{(1 + YTM)^{du_t / 252}}$$

O `rfquant` resolve por método numérico (`scipy.optimize.brentq`), com
intervalo de busca inicial de −5% a 50% a.a. expandido automaticamente
quando necessário (PUs com ágio ou deságio extremos). Implementação:
`ytm.calcular` (`pricing/ytm.py`).

## 8. Current Yield

$$CY = \frac{\text{cupom anual (em R\$)}}{PU}$$

O cupom anual é o somatório dos cupons efetivamente pagos no ano, na
convenção composta da seção 1, e não a divisão linear $VN \cdot i$. Para
a frequência padrão (2 semestrais), $2 \cdot VN \cdot [(1+i)^{1/2} - 1]$.
Rendimento de cupom sobre o preço, sem considerar amortização do principal.
Implementação: `current_yield.calcular` (o comando `rfq tesouro precificar`
fornece o cupom anual composto).

## 9. Marcação a Mercado

### Aproximação linear (`marktomarket.aproximada`)

$$PU_{mercado} \approx PU_{compra} \cdot [1 - D_{mod} \cdot (y_{mercado} - y_{compra})]$$

Válida para variações pequenas de taxa (< 1 p.p.) e no instante da
compra: parte de `PU_compra` e ignora o carrego entre a compra e a data
atual.

### Exata (`marktomarket.exata`)

Re-precifica o fluxo remanescente na data de hoje, duas vezes:

- `pu_curva`: fluxo remanescente descontado pela **taxa de compra** (o
  "carrego" do título, não um resultado de mercado);
- `pu_mercado`: o mesmo fluxo descontado pela **taxa de mercado** atual.

A variação é `pu_mercado − pu_curva` (absoluta e percentual), com a
duration modificada e os dias úteis decorridos no resultado. A função
`marktomarket.curva` aplica o mesmo cálculo a uma lista de títulos.

## 10. Tabela Regressiva de IR

| Prazo (dias corridos) | Alíquota |
|----------------------|----------|
| Até 180 | 22,5% |
| 181 a 360 | 20,0% |
| 361 a 720 | 17,5% |
| Acima de 720 | 15,0% |

Produtos isentos: LCI, LCA, CRI, CRA e debêntures incentivadas
(Lei 12.431). Implementação: `ir.aliquota`, `ir.ir_devido`, `ir.calcular`
(`comparison/ir.py`).

## 11. IOF Regressivo

Aplicável apenas a resgates com prazo < 30 dias. No 1º dia, 96% do
rendimento é consumido por IOF; no 29º, 3%; a partir do 30º dia, zero.
A tabela completa dia a dia está em `comparison/ir.py` (`IOF_TABELA`).

Na função de alto nível `ir.calcular`, a ordem de tributação é:
primeiro IOF, depois IR sobre o rendimento restante.

## 12. Taxa Equivalente entre Isento e Tributado

Dado um produto tributado com taxa bruta `y_trib` e alíquota `α` do prazo:

$$y_{isento} = y_{trib} \cdot (1 - \alpha)$$

Inversamente, dado um produto isento:

$$y_{trib} = \frac{y_{isento}}{1 - \alpha}$$

É essa segunda forma que produz a coluna "Equivalente CDB" do comando
`rfq comparar`: qual taxa bruta de CDB renderia o mesmo líquido do produto
isento. Implementação: `taxa_equivalente.isento_equivalente_a_tributado` e
`tributado_equivalente_a_isento`.

### Percentual do CDI

$$y_{anual} = \%CDI \times CDI_{anual}$$

Ex.: 110% do CDI com CDI a 13,0% a.a. → 14,3% a.a. Implementação:
`taxa_equivalente.cdi_para_taxa_anual` (e a inversa
`taxa_anual_para_cdi`).

## 13. Relação de Fisher (Prefixado ↔ IPCA+)

$$(1 + y_{prefixado}) = (1 + y_{real}) \cdot (1 + \pi_{esperado})$$

Onde `y_real` é a taxa IPCA+ e `π_esperado` é o IPCA esperado no período.
Disponível nos dois sentidos (`curva_juros.taxa_pre_para_pos` /
`taxa_pos_para_pre`, e em `taxa_equivalente.pre_para_ipca_mais` /
`ipca_mais_para_pre`).

> **Nota de nomenclatura.** Aqui "pré ↔ pós" do `curva_juros` significa
> prefixado ↔ IPCA+ (taxa real), **não** pós-fixado indexado a CDI/Selic
> do jargão de mercado. Para o par prefixado ↔ IPCA+ os nomes explícitos
> são `taxa_equivalente.pre_para_ipca_mais` / `ipca_mais_para_pre`,
> preferidos em código novo. Exemplo de uso está em
> [uso.md](uso.md#tributação-e-comparação).

### Taxa efetiva ↔ nominal capitalizada

$$i_{nominal} = m \cdot \left[(1 + i_{efetiva})^{1/m} - 1\right]$$

com `m` capitalizações por ano (padrão 2). Implementação:
`curva_juros.taxa_efetiva_para_nominal` e a inversa
`taxa_nominal_para_efetiva`.

## 14. Curva de Juros (ETTJ)

A classe `ETTJ` (`pricing/curva_juros.py`) interpola a estrutura a termo a
partir de pontos `(prazo em anos, taxa anual)`.

### Flat-forward (padrão B3/ANBIMA) — método default

Assume o forward **constante** entre vértices consecutivos: o fator de
desconto é interpolado log-linearmente entre os nós `t₁` e `t₂` que
cercam o prazo `τ`:

$$(1 + r(\tau))^{\tau} = (1 + r_1)^{t_1} \cdot \left[\frac{(1 + r_2)^{t_2}}{(1 + r_1)^{t_1}}\right]^{\frac{\tau - t_1}{t_2 - t_1}}$$

É o **default** da classe (`metodo="flat_forward"`): o padrão de
interpolação da curva de juros da B3/ANBIMA, sem oportunidades de
arbitragem entre vértices. Para prazo fora do intervalo dos nós, usa a
taxa do nó mais próximo (extrapolação flat).

### Interpolação linear (disponível)

$$y(\tau) = y_1 + (y_2 - y_1) \cdot \frac{\tau - \tau_1}{\tau_2 - \tau_1}$$

Simples e robusta; não produz curva suave entre pontos distantes.

### Nelson-Siegel (disponível)

$$y(\tau) = \beta_0 + \beta_1 \cdot \frac{1 - e^{-\tau/\lambda}}{\tau/\lambda} + \beta_2 \cdot \left[\frac{1 - e^{-\tau/\lambda}}{\tau/\lambda} - e^{-\tau/\lambda}\right]$$

Ajuste paramétrico suave (padrão de mercado), com parâmetros estimados por
mínimos quadrados (`scipy.optimize.curve_fit`). Se o ajuste não converge, o
fallback **não é** a interpolação linear: o código fixa uma curva flat na
última taxa observada (β₀ = última taxa, β₁ = β₂ = 0) até nova execução.

A ETTJ também expõe o fator de desconto `(1 + y(τ))^(−τ)`.

## 15. Convenção de taxa líquida na comparação (limitação declarada)

O comando `rfq comparar` e `taxa_equivalente.taxa_liquida_anual` aplicam o
IR de forma **linear**:

$$y_{liq} = y_{bruta} \cdot (1 - \alpha_{prazo})$$

usando a alíquota da tabela regressiva **do prazo informado**. Essa
convenção é exata para um horizonte de 1 ano. Para prazos diferentes, a
alíquota aplicada continua sendo a do resgate, o que é uma aproximação:
em horizontes curtos a diferença para o cálculo composto pode ser
perceptível. É uma limitação conhecida e declarada, não um erro de
implementação.

A variante **composta** (`taxa_equivalente.taxa_liquida_anual_composta`)
é exata para horizontes `t ≠ 1` ano: o IR incide uma única vez, no
resgate, sobre o ganho acumulado:

$$y_{total} = 1 + (1-\alpha)\cdot\left((1+y_{bruta})^{t}-1\right), \qquad y_{a.a.} = y_{total}^{1/t}-1$$

com `t = prazo_dias/365` (dias corridos, a mesma régua da tabela
regressiva do IR); em `t = 1` ano as duas convenções coincidem.

## Referências

- **Fabozzi, F. J.** — *Fixed Income Analysis* (CFA Institute)
- **Nelson, C. R. & Siegel, A. F. (1987)** — *Parsimonious Modeling of Yield Curves*, Journal of Business
