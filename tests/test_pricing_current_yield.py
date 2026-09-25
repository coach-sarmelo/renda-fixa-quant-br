"""Testes do cálculo de Current Yield."""

from __future__ import annotations

import pytest

from rfquant.pricing import current_yield


def test_cy_valor_conhecido() -> None:
    """CY = cupom anual (R$) / PU — 80/1000 = 8%."""
    cy = current_yield.calcular(cupom_anual=80.0, pu_mercado=1000.0)
    assert cy == pytest.approx(0.08, rel=1e-12)


def test_cy_pu_com_desagio() -> None:
    """PU abaixo do nominal eleva o CY proporcionalmente: 80/900 ≈ 8,89%."""
    cy = current_yield.calcular(cupom_anual=80.0, pu_mercado=900.0)
    assert cy == pytest.approx(80.0 / 900.0, rel=1e-12)


@pytest.mark.parametrize(("pu_mercado"), [0.0, -500.0])
def test_cy_rejeita_pu_nao_positivo(pu_mercado: float) -> None:
    """PU ≤ 0 ⇒ ValueError."""
    with pytest.raises(ValueError):
        current_yield.calcular(cupom_anual=80.0, pu_mercado=pu_mercado)
