"""Testes do cálculo de YTM."""

from __future__ import annotations

from datetime import date

import pytest

from rfquant.pricing import pu, ytm


def test_ytm_inversa_do_pu() -> None:
    """Roundtrip PU↔YTM zero-cupom recupera a taxa com tol 1e-6."""
    data_compra = date(2026, 1, 1)
    vencimento = date(2031, 1, 1)
    taxa_original = 0.10

    p = pu.calcular(data_compra, vencimento, taxa_original, 1000.0, 0.0)
    y = ytm.calcular(p, data_compra, vencimento, 1000.0, 0.0)

    assert y == pytest.approx(taxa_original, abs=1e-6)

def test_ytm_zero_cupom_pu_maior() -> None:
    """PU maior que o nominal → YTM negativa."""
    p = 1100.0
    y = ytm.calcular(p, date(2026, 1, 1), date(2027, 1, 1), 1000.0, 0.0)
    assert y < 0

def test_ytm_pu_menor() -> None:
    """PU menor que o nominal → YTM positiva."""
    p = 900.0
    y = ytm.calcular(p, date(2026, 1, 1), date(2027, 1, 1), 1000.0, 0.0)
    assert y > 0

def test_ytm_pu_invalido() -> None:
    """PU não positivo deve levantar ValueError."""
    with pytest.raises(ValueError):
        ytm.calcular(0.0, date(2026, 1, 1), date(2027, 1, 1), 1000.0, 0.0)

def test_ytm_com_cupom() -> None:
    """Roundtrip com cupons semestrais recupera a taxa com tol 1e-6."""
    data_compra = date(2026, 1, 1)
    vencimento = date(2031, 1, 1)
    taxa_original = 0.09
    cupom = 0.06

    p = pu.calcular(data_compra, vencimento, taxa_original, 1000.0, cupom)
    y = ytm.calcular(p, data_compra, vencimento, 1000.0, cupom)

    assert y == pytest.approx(taxa_original, abs=1e-6)
