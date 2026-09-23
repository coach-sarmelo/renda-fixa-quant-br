"""Cálculo da Yield to Maturity (YTM)."""

from __future__ import annotations

from datetime import date

from scipy.optimize import brentq

from rfquant.pricing.fluxo_caixa import gerar_fluxos
from rfquant.pricing.pu import _pu_de_fluxos


def calcular(
    pu_mercado: float,
    data_compra: date,
    data_vencimento: date,
    valor_nominal: float = 1000.0,
    taxa_cupom_anual: float = 0.0,
    frequencia_cupom: int = 2,
    tol: float = 1e-6,
) -> float:
    """Calcula a YTM dada pelo PU de mercado.

    Resolve PU_mercado = Σ FC_t / (1+YTM)^(du_t/252) por YTM via brentq.
    """
    if pu_mercado <= 0:
        raise ValueError("PU de mercado deve ser positivo.")

    fluxos = gerar_fluxos(
        data_compra=data_compra,
        data_vencimento=data_vencimento,
        valor_nominal=valor_nominal,
        taxa_cupom_anual=taxa_cupom_anual,
        frequencia_cupom=frequencia_cupom,
    )

    def f(y: float) -> float:
        return _pu_de_fluxos(fluxos, data_compra, y) - pu_mercado

    # Expande o bracket até conter a raiz (PU com ágio profundo → YTM < -5%;
    # PU com deságio extremo → YTM > 50%).
    lo, hi = -0.05, 0.50
    for _ in range(10):
        if f(lo) * f(hi) <= 0:
            break
        lo = max(2 * lo, -0.99)
        hi *= 2

    # float(): brentq não-tipado devolve Any para o mypy.
    return float(brentq(f, lo, hi, xtol=tol, maxiter=200))
