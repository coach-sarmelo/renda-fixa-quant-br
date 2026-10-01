"""Testes das métricas de risco — DV01 e Convexidade."""

from __future__ import annotations

from datetime import date

import pytest

from rfquant.pricing import duration, pu, risco

# Par de datas com exatamente 252 DU do calendário real.
COMPRA_252_DU = date(2026, 1, 5)
VENCIMENTO_252_DU = date(2027, 1, 8)


# ----------------------------------------------------------------------
# DV01
# ----------------------------------------------------------------------
def test_dv01_zero_cupom_positivo() -> None:
    """DV01 de um zero-cupom é sempre positivo."""
    d = risco.dv01(date(2026, 1, 1), date(2031, 1, 1), 0.10)
    assert d > 0


def test_dv01_cresce_com_prazo() -> None:
    """DV01 maior para prazo mais longo (mesma taxa)."""
    d_curto = risco.dv01(date(2026, 1, 1), date(2028, 1, 1), 0.10)
    d_longo = risco.dv01(date(2026, 1, 1), date(2036, 1, 1), 0.10)
    assert d_longo > d_curto


def test_dv01_consistente_com_duration_mod() -> None:
    """DV01 (re-precificação) ≈ D_mod × PU × 0,0001 para variação de 1 bp."""
    compra, venc, taxa = date(2026, 1, 1), date(2031, 1, 1), 0.10
    d_mod = duration.modificada(compra, venc, taxa)
    p = pu.calcular(compra, venc, taxa)
    dv01_aprox = risco.dv01_rapido(p, d_mod)
    dv01_exato = risco.dv01(compra, venc, taxa)
    # Para 1 bp, a aproximação é muito boa (< 1%)
    assert dv01_exato == pytest.approx(dv01_aprox, rel=0.01)


def test_dv01_252du_bate_com_conta_a_mao() -> None:
    """Zero-cupom de 252 DU a 10%: PU = 1000/1,10; PU(10,01%) = 1000/1,1001.
    DV01 = |PU - PU'| ≈ 0,0826..."""
    d = risco.dv01(COMPRA_252_DU, VENCIMENTO_252_DU, 0.10)
    pu_base = 1000.0 / 1.10
    pu_chocado = 1000.0 / 1.1001
    assert d == pytest.approx(abs(pu_base - pu_chocado), rel=1e-4)


# ----------------------------------------------------------------------
# Convexidade
# ----------------------------------------------------------------------
def test_convexidade_zero_cupom_positiva() -> None:
    """Convexidade de qualquer título é sempre positiva."""
    c = risco.convexidade(date(2026, 1, 1), date(2031, 1, 1), 0.10)
    assert c > 0


def test_convexidade_cresce_com_prazo() -> None:
    """Convexidade maior para prazo mais longo."""
    c_curto = risco.convexidade(date(2026, 1, 1), date(2028, 1, 1), 0.10)
    c_longo = risco.convexidade(date(2026, 1, 1), date(2036, 1, 1), 0.10)
    assert c_longo > c_curto


def test_convexidade_252du_bate_com_conta_a_mao() -> None:
    """Zero-cupom 252 DU a 10%: t = 1, C = t·(t+1)/(1+y)² = 2/1,21."""
    c = risco.convexidade(COMPRA_252_DU, VENCIMENTO_252_DU, 0.10)
    assert c == pytest.approx(1.0 * 2.0 / 1.10**2, rel=1e-6)


def test_convexidade_com_cupom_menor_que_zero_cupom() -> None:
    """Cupons reduzem a convexidade em relação a zero-cupom de mesmo prazo."""
    c_zero = risco.convexidade(date(2026, 1, 1), date(2031, 1, 1), 0.10)
    c_cupom = risco.convexidade(date(2026, 1, 1), date(2031, 1, 1), 0.10, taxa_cupom_anual=0.08)
    assert c_cupom < c_zero


# ----------------------------------------------------------------------
# Aproximação de 2ª ordem
# ----------------------------------------------------------------------
def test_variacao_pu_segunda_ordem_melhor_que_primeira() -> None:
    """Δy = +200 bps: a aproximação de 2ª ordem (com convexidade) é mais
    precisa do que a de 1ª ordem (só duration)."""
    compra, venc, taxa = date(2026, 1, 1), date(2036, 1, 1), 0.10
    delta_y = 0.02  # +200 bps

    p = pu.calcular(compra, venc, taxa)
    p_novo = pu.calcular(compra, venc, taxa + delta_y)
    var_real = (p_novo - p) / p

    d_mod = duration.modificada(compra, venc, taxa)
    convex = risco.convexidade(compra, venc, taxa)

    var_1a = -d_mod * delta_y
    var_2a = risco.variacao_pu(d_mod, convex, delta_y)

    # 2ª ordem é mais precisa que 1ª ordem
    assert abs(var_2a - var_real) < abs(var_1a - var_real)
