# Fórmulas

Toda a matemática implementada no `rfquant`, com as convenções usadas e
suas limitações. Cada seção corresponde a funções reais do código
(`src/rfquant/pricing/` e `src/rfquant/comparison/`).

## 1. Fluxo de caixa

`gerar_fluxos` (`pricing/fluxo_caixa.py`) monta os pagamentos futuros do
título:

- **Zero-cupom** (`taxa_cupom_anual = 0`): um único fluxo — o valor nominal
  no vencimento.
- **Com cupom** (`taxa_cupom_anual > 0`): cupons periódicos
  (`frequencia_cupom` por ano, padrão 2 = semestral) de
  `valor_nominal × taxa_cupom_anual / frequencia_cupom`, mais o principal
  junto ao último cupom.

> **Limitação declarada:** o cupom é **linear** (`VN × i / f`). O padrão
> STN/ANBIMA para títulos cupomados é **composto** —
> `VN × ((1 + i)^(1/f) − 1)` — que daria R$ 48,81 por cupom numa NTN-F de
> 10% a.a., contra os R$ 50,00 da fórmula linear (desvio de ~2,4% por
> cupom). A convenção composta é aprimoramento planejado; até lá, o PU de
> títulos cupomados diverge do oficial também por este motivo, além da
> aproximação de dias úteis.

## 2. Preço Unitário (PU)

$$PU = \sum_{t=1}^{n} \frac{FC_t}{(1 + y)^{du_t / 252}}$$

Onde:

- `FC_t` = fluxo de caixa no período `t` (cupom ou principal)
- `y` = taxa de desconto anual (deve ser > −100%; o código recusa valores
  menores ou iguais)
- `du_t` = dias úteis até o fluxo `t`, na base 252 do mercado brasileiro

**A aproximação D6 (dias úteis).** O `rfquant` estima os dias úteis por

$$du = \text{round}\left(dc \times \frac{252}{365}\right)$$

onde `dc` é o número de dias corridos (mínimo 1). É uma aproximação de
proporcionalidade: ela acerta a média de longo prazo, mas ignora onde os
feriados caem. O Tesouro oficial desconta pelos dias úteis **reais** do
calendário brasileiro, então o PU calculado diverge do oficial — e o erro
**cresce com o prazo** (tabelas medidas em [dados.md](dados.md), seção
"Limitação medida da aproximação D6"). Para prazos curtos a divergência é
pequena (tipicamente < 1 dia útil); para prazos de anos ela se acumula.

Implementação: `pu.calcular` (`pricing/pu.py`).

## 3. Duration de Macaulay

$$D_{mac} = \frac{\sum_{t=1}^{n} t_{anos} \cdot \frac{FC_t}{(1+y)^{t_{anos}}}}{PU}$$

O prazo médio ponderado dos fluxos de caixa, em anos. Implementação:
`duration.macaulay`.

## 4. Duration Modificada

$$D_{mod} = \frac{D_{mac}}{1 + y}$$

Mede a sensibilidade do PU a variações na taxa:

$$\Delta PU \approx -D_{mod} \cdot \Delta y \cdot PU$$

Implementação: `duration.modificada`.

## 5. Yield to Maturity (YTM)

Dado um PU de mercado, resolve-se a taxa que iguala preço e fluxos:

$$PU_{mercado} = \sum_{t=1}^{n} \frac{FC_t}{(1 + YTM)^{du_t / 252}}$$

O `rfquant` resolve por método numérico (`scipy.optimize.brentq`), com
intervalo de busca inicial de −5% a 50% a.a. expandido automaticamente
quando necessário (PUs com ágio ou deságio extremos). Implementação:
`ytm.calcular` (`pricing/ytm.py`).

## 6. Current Yield

$$CY = \frac{\text{cupom anual (em R\$)}}{PU}$$

Rendimento de cupom sobre o preço, sem considerar amortização do principal.
Implementação: `current_yield.calcular`.

## 7. Marcação a Mercado

### Aproximação linear (`marktomarket.aproximada`)

$$PU_{mercado} \approx PU_{compra} \cdot [1 - D_{mod} \cdot (y_{mercado} - y_{compra})]$$

Válida para variações pequenas de taxa (< 1 p.p.).

### Exata (`marktomarket.exata`)

Re-precifica o fluxo remanescente na data de hoje, duas vezes:

- `pu_curva`: fluxo remanescente descontado pela **taxa de compra** — o
  "carrego" do título, não um resultado de mercado;
- `pu_mercado`: o mesmo fluxo descontado pela **taxa de mercado** atual.

A variação é `pu_mercado − pu_curva` (absoluta e percentual), com a
duration modificada e os dias úteis decorridos no resultado. A função
`marktomarket.curva` aplica o mesmo cálculo a uma lista de títulos.

## 8. Tabela Regressiva de IR

| Prazo (dias corridos) | Alíquota |
|----------------------|----------|
| Até 180 | 22,5% |
| 181 a 360 | 20,0% |
| 361 a 720 | 17,5% |
| Acima de 720 | 15,0% |

Produtos isentos: LCI, LCA, CRI, CRA e debêntures incentivadas
(Lei 12.431). Implementação: `ir.aliquota`, `ir.ir_devido`, `ir.calcular`
(`comparison/ir.py`).

## 9. IOF Regressivo

Aplicável apenas a resgates com prazo < 30 dias. No 1º dia, 96% do
rendimento é consumido por IOF; no 29º, 3%; a partir do 30º dia, zero.
A tabela completa dia a dia está em `comparison/ir.py` (`IOF_TABELA`).

Na função de alto nível `ir.calcular`, a ordem de tributação é:
primeiro IOF, depois IR sobre o rendimento restante.

## 10. Taxa Equivalente entre Isento e Tributado

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

## 11. Relação de Fisher (Prefixado ↔ IPCA+)

$$(1 + y_{prefixado}) = (1 + y_{real}) \cdot (1 + \pi_{esperado})$$

Onde `y_real` é a taxa IPCA+ e `π_esperado` é o IPCA esperado no período.
Disponível nos dois sentidos (`curva_juros.taxa_pre_para_pos` /
`taxa_pos_para_pre`, e em `taxa_equivalente.pre_para_ipca_mais` /
`ipca_mais_para_pre`).

> **Nota de nomenclatura.** Aqui "pré ↔ pós" do `curva_juros` significa
> prefixado ↔ IPCA+ (taxa real), **não** pós-fixado indexado a CDI/Selic
> do jargão de mercado. Para o par prefixado ↔ IPCA+ os nomes explícitos
> são `taxa_equivalente.pre_para_ipca_mais` / `ipca_mais_para_pre` —
> preferidos em código novo. Exemplo de uso está em
> [uso.md](uso.md#tributação-e-comparação).

### Taxa efetiva ↔ nominal capitalizada

$$i_{nominal} = m \cdot \left[(1 + i_{efetiva})^{1/m} - 1\right]$$

com `m` capitalizações por ano (padrão 2). Implementação:
`curva_juros.taxa_efetiva_para_nominal` e a inversa
`taxa_nominal_para_efetiva`.

## 12. Curva de Juros (ETTJ)

A classe `ETTJ` (`pricing/curva_juros.py`) interpola a estrutura a termo a
partir de pontos `(prazo em anos, taxa anual)`:

### Interpolação linear

$$y(\tau) = y_1 + (y_2 - y_1) \cdot \frac{\tau - \tau_1}{\tau_2 - \tau_1}$$

Simples e robusta; não produz curva suave entre pontos distantes.

### Nelson-Siegel

$$y(\tau) = \beta_0 + \beta_1 \cdot \frac{1 - e^{-\tau/\lambda}}{\tau/\lambda} + \beta_2 \cdot \left[\frac{1 - e^{-\tau/\lambda}}{\tau/\lambda} - e^{-\tau/\lambda}\right]$$

Ajuste paramétrico suave (padrão de mercado), com parâmetros estimados por
mínimos quadrados (`scipy.optimize.curve_fit`). Se o ajuste não converge, o
fallback **não é** a interpolação linear: o código fixa uma curva flat na
última taxa observada (β₀ = última taxa, β₁ = β₂ = 0) até nova execução.

A ETTJ também expõe o fator de desconto `(1 + y(τ))^(−τ)`.

## 13. Convenção de taxa líquida na comparação (limitação declarada)

O comando `rfq comparar` e `taxa_equivalente.taxa_liquida_anual` aplicam o
IR de forma **linear**:

$$y_{liq} = y_{bruta} \cdot (1 - \alpha_{prazo})$$

usando a alíquota da tabela regressiva **do prazo informado**. Essa
convenção é exata para um horizonte de 1 ano. Para prazos diferentes, a
alíquota aplicada continua sendo a do resgate, o que é uma aproximação —
em horizontes curtos a diferença para o cálculo composto pode ser
perceptível. É uma limitação conhecida e declarada, não um erro de
implementação.

## Referências

- **Fabozzi, F. J.** — *Fixed Income Analysis* (CFA Institute)
- **Nelson, C. R. & Siegel, A. F. (1987)** — *Parsimonious Modeling of Yield Curves*, Journal of Business
