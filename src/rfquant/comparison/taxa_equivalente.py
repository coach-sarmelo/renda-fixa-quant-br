"""Conversão de taxas e análise comparativa entre produtos e fundos de renda fixa.

Cobre:
    - CDB pré vs CDI (% do CDI)
    - Isento (LCI/LCA) vs tributado (CDB)
    - Prefixado vs IPCA+ (Fisher)
    - Taxa bruta vs taxa líquida de IR
    - Resumo de rentabilidade de Informe Diário de fundos vs CDI
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Literal

import pandas as pd

from rfquant.comparison import ir
from rfquant.data.base import Titulo, isento_por_categoria, validar_categoria
from rfquant.data.calendario import dias_uteis as _dias_uteis_calendario
from rfquant.data.sgs_bcb import SGSProvider

DU_ANO = 252  # base de dias úteis do mercado brasileiro


# ----------------------------------------------------------------------
# CDI
# ----------------------------------------------------------------------
def cdi_para_taxa_anual(percentual_cdi: float, cdi_anual: float) -> float:
    """Converte 'X% do CDI' em taxa anual efetiva.

    Ex: 110% do CDI com CDI a 13,0% → 14,3% a.a.

    Limitação declarada (proxy %DI): para papéis cotados em % do DI, usa-se
    o CDI à vista como proxy — sem spread de curva. A curva DI/ETTJ negocia
    spread sobre o CDI; enquanto ela não é consumida aqui, "100% do CDI"
    vale como DI à vista e o erro do proxy é o spread.
    """
    if percentual_cdi <= 0:
        raise ValueError("Percentual do CDI deve ser positivo.")
    if cdi_anual <= 0:
        raise ValueError("CDI deve ser positivo.")
    return percentual_cdi * cdi_anual


def taxa_anual_para_cdi(taxa_anual: float, cdi_anual: float) -> float:
    """Converte taxa anual efetiva em 'X% do CDI'."""
    if cdi_anual <= 0:
        raise ValueError("CDI deve ser positivo.")
    return taxa_anual / cdi_anual


def cdi_anual_do_provider(provider: SGSProvider, inicio: date, fim: date) -> float:
    """Deriva o CDI anual (decimal a.a.) da série diária do provider
    SGS/BCB (série 12, o CDI diário) no período ``[inicio, fim]``.

    A série chega em % ao dia (ex.: 0,051660 = 0,051660 %/dia). Anualização
    base 252: acumula os fatores diários da janela — um registro por dia
    útil, o nº de DU vem da própria série — e escalona para 252 DU:

        acumulado = (1 + v_1/100) × ... × (1 + v_n/100) - 1
        cdi_anual = (1 + acumulado)^(252/n_du) - 1

    O resultado alimenta `cdi_para_taxa_anual` (ex.: 110% do CDI). Série
    vazia (período sem dados) levanta ValueError em pt-BR.
    """
    serie = provider.serie_diaria(inicio, fim)
    if serie.empty:
        raise ValueError(
            f"CDI: série do provider SGS/BCB vazia no período {inicio:%d/%m/%Y} a {fim:%d/%m/%Y}."
        )
    fatores = 1.0 + serie["valor"] / 100.0
    acumulado = float(fatores.prod()) - 1.0
    n_du = len(fatores)
    return float((1.0 + acumulado) ** (DU_ANO / n_du) - 1.0)


# ----------------------------------------------------------------------
# Resumo de Informe Diário de Fundos (CVM) vs CDI
# ----------------------------------------------------------------------
@dataclass(frozen=True)
class ResumoFundo:
    """Resumo integrado de rentabilidade de um fundo no período."""

    rentabilidade_acumulada: float
    rentabilidade_anualizada: float
    percentual_cdi: float
    data_inicio: date | None
    data_fim: date | None
    dias_uteis: int


def rentabilidade_periodo(df_fundo: pd.DataFrame) -> float:
    """Calcula a rentabilidade acumulada a partir da série de cota.

    Assume que `df_fundo` está ordenado por data e contém a coluna `valor_cota`.
    """
    if df_fundo.empty or "valor_cota" not in df_fundo.columns:
        return 0.0
    cotas = df_fundo["valor_cota"].dropna()
    if len(cotas) < 2 or cotas.iloc[0] == 0:
        return 0.0
    return float(cotas.iloc[-1] / cotas.iloc[0] - 1)


def cdi_equivalente(rentabilidade: float, dias_uteis: int) -> float:
    """Anualiza uma rentabilidade pelo número de dias úteis (base 252)."""
    if dias_uteis <= 0:
        return 0.0
    return float((1 + rentabilidade) ** (DU_ANO / dias_uteis) - 1)


def rentabilidade_anualizada(df_fundo: pd.DataFrame) -> float:
    """Anualiza (base 252) a rentabilidade acumulada com DU do calendário real."""
    acumulada = rentabilidade_periodo(df_fundo)
    if df_fundo.empty or "data_competencia" not in df_fundo.columns:
        return 0.0
    datas = pd.to_datetime(df_fundo["data_competencia"])
    du = _dias_uteis_calendario(datas.iloc[0].date(), datas.iloc[-1].date())
    return cdi_equivalente(acumulada, du)


def resumir_fundo(df_fundo: pd.DataFrame, cdi_provider: SGSProvider) -> ResumoFundo:
    """Calcula acumulada, anualizada (base 252) e % CDI em uma única passagem."""
    if (
        df_fundo.empty
        or "data_competencia" not in df_fundo.columns
        or "valor_cota" not in df_fundo.columns
    ):
        return ResumoFundo(0.0, 0.0, 0.0, None, None, 0)

    acumulada = rentabilidade_periodo(df_fundo)
    datas = pd.to_datetime(df_fundo["data_competencia"])
    inicio, fim = datas.iloc[0].date(), datas.iloc[-1].date()
    du = _dias_uteis_calendario(inicio, fim)
    if du <= 0:
        return ResumoFundo(acumulada, 0.0, 0.0, inicio, fim, 0)

    anualizada = cdi_equivalente(acumulada, du)
    cdi_anual = cdi_anual_do_provider(cdi_provider, inicio, fim)
    pct_cdi = taxa_anual_para_cdi(anualizada, cdi_anual)
    return ResumoFundo(
        rentabilidade_acumulada=acumulada,
        rentabilidade_anualizada=anualizada,
        percentual_cdi=pct_cdi,
        data_inicio=inicio,
        data_fim=fim,
        dias_uteis=du,
    )


def percentual_cdi(df_fundo: pd.DataFrame, cdi_provider: SGSProvider) -> float:
    """Expressa a rentabilidade anualizada do fundo em % do CDI."""
    return resumir_fundo(df_fundo, cdi_provider).percentual_cdi


# ----------------------------------------------------------------------
# Isento vs tributado
# ----------------------------------------------------------------------
def isento_equivalente_a_tributado(
    taxa_isento: float,
    prazo_dias: int,
) -> float:
    """Dada uma taxa de produto isento, retorna a taxa bruta equivalente
    de um produto tributado que renderia o mesmo líquido.

    Ex: LCI a 10% a.a. com IR de 15% ≈ CDB a 11,76% a.a.
    """
    aliq = ir.aliquota(prazo_dias)
    if aliq >= 1:
        raise ValueError("Alíquota inválida.")
    return taxa_isento / (1 - aliq)


def tributado_equivalente_a_isento(
    taxa_tributado: float,
    prazo_dias: int,
) -> float:
    """Dada uma taxa bruta de produto tributado, retorna a taxa de um
    produto isento equivalente.

    Ex: CDB a 12% a.a. com IR de 15% ≈ LCI a 10,2% a.a.
    """
    aliq = ir.aliquota(prazo_dias)
    return taxa_tributado * (1 - aliq)


# ----------------------------------------------------------------------
# Prefixado vs IPCA+ (Fisher canônica)
# ----------------------------------------------------------------------
def pre_para_ipca_mais(prefixado: float, ipca_esperado: float) -> float:
    """Taxa prefixada → taxa real (IPCA+) equivalente (Fisher exata)."""
    if ipca_esperado <= -1:
        raise ValueError("IPCA esperado deve ser maior que -100%.")
    return (1 + prefixado) / (1 + ipca_esperado) - 1


def ipca_mais_para_pre(ipca_mais: float, ipca_esperado: float) -> float:
    """Taxa real (IPCA+) → taxa prefixada equivalente."""
    if ipca_esperado <= -1:
        raise ValueError("IPCA esperado deve ser maior que -100%.")
    return (1 + ipca_mais) * (1 + ipca_esperado) - 1


# ----------------------------------------------------------------------
# Comparação multi-produto
# ----------------------------------------------------------------------
@dataclass
class ProdutoRF:
    """View de um produto para comparação líquida de IR.

    Pode ser construída a partir do `Titulo` canônico via `de_titulo()` ou
    diretamente com `categoria` (validada contra `CATEGORIAS` e derivando
    `isento` automaticamente para `LCI`, `LCA` e `debênture-incentivada`).
    """

    nome: str
    taxa_anual: float  # taxa bruta anual (ex: 0.12 = 12%)
    prazo_dias: int
    isento: bool = False
    liquidez_diaria: bool = False
    emissor: str = ""
    categoria: str | None = None

    def __post_init__(self) -> None:
        validar_categoria(self.categoria)
        if isento_por_categoria(self.categoria):
            self.isento = True

    @classmethod
    def de_titulo(
        cls,
        titulo: Titulo,
        *,
        prazo_dias: int,
        taxa_anual: float | None = None,
        liquidez_diaria: bool = False,
    ) -> ProdutoRF:
        """Constrói a view a partir do `Titulo` canônico.

        `prazo_dias` é o prazo da análise (não vive no `Titulo`).
        `taxa_anual` informada pelo usuário prevalece; sem ela, usa
        a `taxa_compra` do `Titulo`. Levanta ValueError se nenhuma taxa
        estiver disponível.
        """
        taxa = taxa_anual
        if taxa is None and titulo.taxa_compra is not None:
            taxa = float(titulo.taxa_compra)
        if taxa is None:
            raise ValueError(
                f"Produto '{titulo.nome}' sem taxa: informe taxa_anual ou taxa_compra no Titulo."
            )
        return cls(
            nome=titulo.nome,
            taxa_anual=taxa,
            prazo_dias=prazo_dias,
            isento=titulo.isento_ir,
            liquidez_diaria=liquidez_diaria,
            emissor=titulo.emissor,
            categoria=titulo.categoria,
        )


@dataclass
class ResultadoComparacao:
    """Resultado de comparação entre produtos."""

    produto: ProdutoRF
    taxa_liquida_anual: float
    equivalente_cdb: float  # taxa bruta de CDB que iguala o líquido


def taxa_liquida_anual(produto: ProdutoRF) -> float:
    """Calcula a taxa anual líquida (após IR) de um produto.

    Convenção linear: taxa_liq = taxa_bruta x (1 - alíquota de saída),
    exata para horizonte de 1 ano. Limitação: para prazo != 1 ano, a
    alíquota aplicada é a do resgate (prazo informado) — aproximação
    documentada em docs/formulas.md; a variante composta, exata para
    t != 1 ano, vive em `taxa_liquida_anual_composta`.

    Assume que a taxa informada é bruta e já representa o rendimento
    acumulado anualizado. Aplica apenas o IR.

    Default de `comparar` e do CLI: a linear não muda silenciosamente
    os contratos do núcleo; o ranking usa a composta.
    """
    aliq = 0.0 if produto.isento else ir.aliquota(produto.prazo_dias)
    return produto.taxa_anual * (1 - aliq)


def liquida_composta(
    taxa_anual: float,
    prazo_dias: int,
    isento: bool,
    nome: str,
) -> float:
    """Líquido composto por escalares — única implementação da fórmula.

    liquido_total = 1 + (1 - alíquota) x ((1 + bruta)^t - 1), anualizada
    por liquido_total^(1/t) - 1: o IR incide uma única vez, no resgate,
    sobre o ganho acumulado. Em t = 1 ano coincide com a linear (tol
    1e-12). t = prazo_dias / 365 — dias corridos, a mesma régua da
    tabela regressiva do IR.

    Levanta ValueError para prazo <= 0 e para taxa bruta < -100% (base
    negativa elevada a t fracionário não tem rendimento real em float).

    Escalares (não ProdutoRF) porque dois núcleos de dataclasses
    distintos a consomem: `taxa_liquida_anual_composta` (view de
    comparação) e o núcleo de ranking (view de ranking, fora do pacote
    público). `nome` só qualifica as mensagens de erro.
    """
    if prazo_dias <= 0:
        raise ValueError(f"Prazo inválido para '{nome}': {prazo_dias} d.")
    if taxa_anual < -1:
        raise ValueError(f"Taxa bruta de '{nome}' menor que -100%: sem rendimento composto real.")
    if isento:
        return taxa_anual
    t = prazo_dias / 365
    aliq = ir.aliquota(prazo_dias)
    liquido_total: float = 1.0 + (1.0 - aliq) * ((1.0 + taxa_anual) ** t - 1.0)
    anualizada: float = liquido_total ** (1.0 / t)
    return anualizada - 1.0


def taxa_liquida_anual_composta(produto: ProdutoRF) -> float:
    """Calcula a taxa anual líquida na convenção composta, exata para
    horizonte t != 1 ano (fórmula e guardas em `liquida_composta`).

    Default do núcleo de ranking (fora do pacote público): o horizonte
    do candidato é conhecido lá; `comparar` e o CLI permanecem lineares.
    """
    return liquida_composta(produto.taxa_anual, produto.prazo_dias, produto.isento, produto.nome)


def comparar(
    produtos: list[ProdutoRF],
    *,
    convencao: Literal["linear", "composta"] = "linear",
) -> list[ResultadoComparacao]:
    """Compara produtos por taxa líquida anual (decrescente).

    Default linear: o comparar e o CLI mantêm a convenção linear;
    a variante composta é o default do ranking (e selecionável via convencao='composta').
    """
    if convencao not in ("linear", "composta"):
        raise ValueError(f"Convenção desconhecida: {convencao!r}. Use 'linear' ou 'composta'.")
    resultados: list[ResultadoComparacao] = []
    for p in produtos:
        liq = taxa_liquida_anual(p) if convencao == "linear" else taxa_liquida_anual_composta(p)
        eq_cdb = isento_equivalente_a_tributado(liq, p.prazo_dias) if p.isento else p.taxa_anual
        resultados.append(
            ResultadoComparacao(
                produto=p,
                taxa_liquida_anual=liq,
                equivalente_cdb=eq_cdb,
            )
        )
    return sorted(resultados, key=lambda r: r.taxa_liquida_anual, reverse=True)
