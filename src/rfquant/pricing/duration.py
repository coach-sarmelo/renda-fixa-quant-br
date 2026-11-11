"""Cálculo de duration (Macaulay e modificada)."""

from __future__ import annotations

from datetime import date

from rfquant.pricing.pu import precificar


def macaulay(
    data_compra: date,
    data_vencimento: date,
    taxa_anual: float,
    valor_nominal: float = 1000.0,
    taxa_cupom_anual: float = 0.0,
    frequencia_cupom: int = 2,
) -> float:
    """Duration de Macaulay em anos.

    Fórmula:
        D_mac = Σ [ t_i · FC_i / (1+y)^t_i ] / PU
    """
    return precificar(
        data_base=data_compra,
        data_vencimento=data_vencimento,
        taxa_anual=taxa_anual,
        valor_nominal=valor_nominal,
        taxa_cupom_anual=taxa_cupom_anual,
        frequencia_cupom=frequencia_cupom,
    ).duration_macaulay


def modificada(
    data_compra: date,
    data_vencimento: date,
    taxa_anual: float,
    valor_nominal: float = 1000.0,
    taxa_cupom_anual: float = 0.0,
    frequencia_cupom: int = 2,
) -> float:
    """Duration modificada.

    Fórmula:
        D_mod = D_mac / (1 + y)
    """
    return precificar(
        data_base=data_compra,
        data_vencimento=data_vencimento,
        taxa_anual=taxa_anual,
        valor_nominal=valor_nominal,
        taxa_cupom_anual=taxa_cupom_anual,
        frequencia_cupom=frequencia_cupom,
    ).duration_modificada
