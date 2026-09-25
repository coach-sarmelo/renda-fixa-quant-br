"""Testes dos cálculos de duration."""

from __future__ import annotations

from datetime import date

import pytest

from rfquant.pricing import duration


def test_duration_zero_cupom_igual_prazo() -> None:
    """Zero-cupom: D_mac = prazo em anos pela convenção D6 (du/252)."""
    compra, venc = date(2026, 1, 1), date(2031, 1, 1)
    d = duration.macaulay(
        data_compra=compra,
        data_vencimento=venc,
        taxa_anual=0.10,
        valor_nominal=1000.0,
        taxa_cupom_anual=0.0,
    )
    du_esperado = round((venc - compra).days * 252 / 365)
    assert d == pytest.approx(du_esperado / 252, rel=1e-9)


def test_macaulay_252du_um_exato() -> None:
    """Zero-cupom com exatamente 252 DU (365 dc) ⇒ D_mac = 1,0
    exato (tol 1e-12). Acoplado a D6."""
    d = duration.macaulay(
        data_compra=date(2026, 1, 1),
        data_vencimento=date(2027, 1, 1),
        taxa_anual=0.10,
        valor_nominal=1000.0,
        taxa_cupom_anual=0.0,
    )
    assert d == pytest.approx(1.0, abs=1e-12)


def test_modificada_um_sobre_um_mais_y() -> None:
    """Com 252 DU, D_mod = 1/(1+y) exato (tol 1e-12)."""
    d_mod = duration.modificada(
        data_compra=date(2026, 1, 1),
        data_vencimento=date(2027, 1, 1),
        taxa_anual=0.10,
        valor_nominal=1000.0,
        taxa_cupom_anual=0.0,
    )
    assert d_mod == pytest.approx(1.0 / 1.10, rel=1e-12)


@pytest.mark.parametrize(("taxa"), [-1.0, -1.5, -2.0])
def test_taxa_menos_ou_igual_menos_100_pct_levanta_value_error(taxa: float) -> None:
    """Taxa <= -100% deve levantar ValueError (mensagem pt-BR)."""
    with pytest.raises(ValueError, match="-100%"):
        duration.macaulay(date(2026, 1, 1), date(2031, 1, 1), taxa, 1000.0, 0.0)
    with pytest.raises(ValueError, match="-100%"):
        duration.modificada(date(2026, 1, 1), date(2031, 1, 1), taxa, 1000.0, 0.0)


def test_degenerado_vencimento_igual_compra_levanta_value_error() -> None:
    """Parâmetro degenerado (vencimento = compra) ⇒ ValueError."""
    with pytest.raises(ValueError):
        duration.macaulay(date(2026, 1, 1), date(2026, 1, 1), 0.10, 1000.0, 0.0)


def test_duration_modificada_menor_que_macaulay() -> None:
    """D_mod < D_mac sempre (pois D_mod = D_mac / (1+y))."""
    d_mac = duration.macaulay(date(2026, 1, 1), date(2031, 1, 1), 0.10, 1000.0, 0.0)
    d_mod = duration.modificada(date(2026, 1, 1), date(2031, 1, 1), 0.10, 1000.0, 0.0)
    assert d_mod < d_mac


def test_duration_com_cupom_menor_que_zero_cupom() -> None:
    """Cupons reduzem a duration em relação a zero-cupom com mesmo prazo."""
    d_zero = duration.macaulay(date(2026, 1, 1), date(2031, 1, 1), 0.10, 1000.0, 0.0)
    d_cupom = duration.macaulay(
        date(2026, 1, 1), date(2031, 1, 1), 0.10, 1000.0, taxa_cupom_anual=0.08
    )
    assert d_cupom < d_zero


def test_duration_cresce_com_prazo() -> None:
    """Duration cresce com o prazo até o vencimento."""
    d_curta = duration.macaulay(date(2026, 1, 1), date(2028, 1, 1), 0.10, 1000.0, 0.0)
    d_longa = duration.macaulay(date(2026, 1, 1), date(2036, 1, 1), 0.10, 1000.0, 0.0)
    assert d_longa > d_curta
