"""Cálculo do Preço Unitário (PU) de um título."""

from __future__ import annotations

from datetime import date

from rfquant.data.calendario import dias_uteis as _dias_uteis_calendario
from rfquant.pricing.fluxo_caixa import Fluxo, gerar_fluxos

# Número de dias úteis por ano (convenção do mercado brasileiro)
DU_ANO = 252


def dias_uteis(inicio: date, fim: date) -> int:
    """Conta os dias úteis reais do calendário B3/SFN no intervalo ``(inicio, fim]``.

    Delega ao calendário real (:mod:`rfquant.data.calendario`, via
    ``pandas_market_calendars``).

    Histórico: antes era a aproximação ``dias corridos × 252/365``, com
    erro relativo de PU medido de 5,11e-4 a 4,80e-3 contra o oficial
    (ver ``docs/dados.md``).
    """
    return _dias_uteis_calendario(inicio, fim)


def calcular(
    data_compra: date,
    data_vencimento: date,
    taxa_anual: float,
    valor_nominal: float = 1000.0,
    taxa_cupom_anual: float = 0.0,
    frequencia_cupom: int = 2,
) -> float:
    """Calcula o PU de um título descontando os fluxos pela taxa anual.

    Fórmula:
        PU = Σ FC_t / (1 + y)^(du_t / 252)
    """
    fluxos: list[Fluxo] = gerar_fluxos(
        data_compra=data_compra,
        data_vencimento=data_vencimento,
        valor_nominal=valor_nominal,
        taxa_cupom_anual=taxa_cupom_anual,
        frequencia_cupom=frequencia_cupom,
    )
    return _pu_de_fluxos(fluxos, data_compra, taxa_anual)


def _pu_de_fluxos(fluxos: list[Fluxo], data_ref: date, taxa_anual: float) -> float:
    """Desconta os fluxos a ``taxa_anual`` — validação central de taxa.

    Raises:
        ValueError: se ``taxa_anual <= -100%`` (fator de desconto nulo ou
            negativo).
    """
    if taxa_anual <= -1:
        raise ValueError("Taxa anual deve ser maior que -100%.")
    pu_total = 0.0
    for f in fluxos:
        du = dias_uteis(data_ref, f.data)
        fator = (1 + taxa_anual) ** (du / DU_ANO)
        pu_total += f.valor / fator
    return pu_total
