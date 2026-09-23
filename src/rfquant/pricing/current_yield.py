"""Cálculo do Current Yield."""

from __future__ import annotations


def calcular(cupom_anual: float, pu_mercado: float) -> float:
    """Current Yield = cupom anual / PU de mercado.

    Args:
        cupom_anual: Valor do cupom anual em reais.
        pu_mercado: Preço Unitário atual.

    Returns:
        Current Yield (ex: 0.05 = 5%).
    """
    if pu_mercado <= 0:
        raise ValueError("PU de mercado deve ser positivo.")
    return cupom_anual / pu_mercado
