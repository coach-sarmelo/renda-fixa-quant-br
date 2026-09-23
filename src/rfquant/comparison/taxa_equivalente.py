"""Conversão de taxas entre produtos de renda fixa.

Cobre:
    - CDB pré vs CDI (% do CDI)
    - Isento (LCI/LCA) vs tributado (CDB)
    - Prefixado vs IPCA+ (Fisher)
    - Taxa bruta vs taxa líquida de IR
"""

from __future__ import annotations

from dataclasses import dataclass

from rfquant.comparison import ir


# ----------------------------------------------------------------------
# CDI
# ----------------------------------------------------------------------
def cdi_para_taxa_anual(percentual_cdi: float, cdi_anual: float) -> float:
    """Converte 'X% do CDI' em taxa anual efetiva.

    Ex: 110% do CDI com CDI a 13,0% → 14,3% a.a.
    """
    if percentual_cdi <= 0:
        raise ValueError("Percentual do CDI deve ser positivo.")
    return percentual_cdi * cdi_anual

def taxa_anual_para_cdi(taxa_anual: float, cdi_anual: float) -> float:
    """Converte taxa anual efetiva em 'X% do CDI'."""
    if cdi_anual <= 0:
        raise ValueError("CDI deve ser positivo.")
    return taxa_anual / cdi_anual

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
# Prefixado vs IPCA+
# ----------------------------------------------------------------------
def pre_para_ipca_mais(prefixado: float, ipca_esperado: float) -> float:
    """Taxa prefixada → taxa real (IPCA+) equivalente (Fisher exata)."""
    return (1 + prefixado) / (1 + ipca_esperado) - 1

def ipca_mais_para_pre(ipca_mais: float, ipca_esperado: float) -> float:
    """Taxa real (IPCA+) → taxa prefixada equivalente."""
    return (1 + ipca_mais) * (1 + ipca_esperado) - 1

# ----------------------------------------------------------------------
# Comparação multi-produto
# ----------------------------------------------------------------------
@dataclass
class ProdutoRF:
    """Representação mínima de um produto para comparação."""

    nome: str
    taxa_anual: float      # taxa bruta anual (ex: 0.12 = 12%)
    prazo_dias: int
    isento: bool = False
    liquidez_diaria: bool = False
    emissor: str = ""

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
    documentada em docs/formulas.md (variante composta fica para uma
    versão futura).

    Assume que a taxa informada é bruta e já representa o rendimento
    acumulado anualizado. Aplica apenas o IR.
    """
    aliq = 0.0 if produto.isento else ir.aliquota(produto.prazo_dias)
    return produto.taxa_anual * (1 - aliq)

def comparar(produtos: list[ProdutoRF]) -> list[ResultadoComparacao]:
    """Compara produtos por taxa líquida anual (decrescente)."""
    resultados: list[ResultadoComparacao] = []
    for p in produtos:
        liq = taxa_liquida_anual(p)
        eq_cdb = isento_equivalente_a_tributado(liq, p.prazo_dias) if p.isento else p.taxa_anual
        resultados.append(
            ResultadoComparacao(
                produto=p,
                taxa_liquida_anual=liq,
                equivalente_cdb=eq_cdb,
            )
        )
    return sorted(resultados, key=lambda r: r.taxa_liquida_anual, reverse=True)
