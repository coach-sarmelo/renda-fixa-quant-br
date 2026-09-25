"""Testes de marcação a mercado.

Contrato central: ``pu_curva`` é o PU do fluxo remanescente
re-precificado HOJE pela taxa de compra — não carrego acumulado.
"""

from __future__ import annotations

from datetime import date

import pytest

from rfquant.pricing import marktomarket, pu

COMPRA, HOJE, VENC = date(2026, 1, 2), date(2027, 1, 2), date(2031, 1, 2)


def test_exata_expoe_pu_curva_reprecificado_hoje() -> None:
    """pu_curva = PU re-precificado HOJE pela taxa de compra (não é carrego acumulado)."""
    res = marktomarket.exata(
        data_compra=COMPRA,
        data_hoje=date(2026, 6, 2),
        data_vencimento=date(2029, 1, 1),
        pu_compra=780.0,
        taxa_compra=0.115,
        taxa_mercado=0.12,
    )
    esperado = pu.calcular(
        data_compra=date(2026, 6, 2),
        data_vencimento=date(2029, 1, 1),
        taxa_anual=0.115,
    )
    assert res.pu_curva == pytest.approx(esperado, rel=1e-12)


def test_dy_zero_pu_mercado_igual_pu_curva() -> None:
    """Δy = 0 ⇒ pu_mercado == pu_curva (tol 1e-9), zero-cupom."""
    res = marktomarket.exata(
        data_compra=COMPRA,
        data_hoje=HOJE,
        data_vencimento=VENC,
        pu_compra=780.0,
        taxa_compra=0.115,
        taxa_mercado=0.115,
    )
    assert res.pu_mercado == pytest.approx(res.pu_curva, abs=1e-9)


def test_dy_zero_com_cupom_igual_pu_curva() -> None:
    """Mesmo contrato com cupom semestral."""
    res = marktomarket.exata(
        data_compra=COMPRA,
        data_hoje=HOJE,
        data_vencimento=VENC,
        pu_compra=780.0,
        taxa_compra=0.10,
        taxa_mercado=0.10,
        taxa_cupom_anual=0.06,
    )
    assert res.pu_mercado == pytest.approx(res.pu_curva, abs=1e-9)
    assert res.variacao_absoluta == pytest.approx(0.0, abs=1e-9)


def test_dy_positivo_pu_cai() -> None:
    """Monotonicidade — taxa de mercado acima da de compra ⇒ perda."""
    res = marktomarket.exata(
        data_compra=COMPRA,
        data_hoje=HOJE,
        data_vencimento=VENC,
        pu_compra=780.0,
        taxa_compra=0.10,
        taxa_mercado=0.12,
    )
    assert res.pu_mercado < res.pu_curva
    assert res.variacao_absoluta < 0
    assert res.variacao_percentual < 0


def test_dy_negativo_pu_sobe() -> None:
    """Monotonicidade no outro sentido — queda de taxa ⇒ ganho."""
    res = marktomarket.exata(
        data_compra=COMPRA,
        data_hoje=HOJE,
        data_vencimento=VENC,
        pu_compra=780.0,
        taxa_compra=0.10,
        taxa_mercado=0.08,
    )
    assert res.pu_mercado > res.pu_curva
    assert res.variacao_percentual > 0


def test_aproximada_converge_para_exata_quando_dy_diminui() -> None:
    """A variação relativa da aproximada (-D_mod·Δy) converge
    para a da exata quando Δy → 0 (erro de 2ª ordem encolhe por década)."""
    pu_compra = pu.calcular(COMPRA, VENC, 0.10)
    res_ref = marktomarket.exata(
        data_compra=COMPRA,
        data_hoje=HOJE,
        data_vencimento=VENC,
        pu_compra=pu_compra,
        taxa_compra=0.10,
        taxa_mercado=0.10,
    )
    d_mod = res_ref.duration_modificada

    erros = []
    for dy in (0.01, 0.001, 0.0001):
        res = marktomarket.exata(
            data_compra=COMPRA,
            data_hoje=HOJE,
            data_vencimento=VENC,
            pu_compra=pu_compra,
            taxa_compra=0.10,
            taxa_mercado=0.10 + dy,
        )
        erros.append(abs(-d_mod * dy - res.variacao_percentual))

    assert erros[1] < erros[0]
    assert erros[2] < erros[1]
    assert erros[2] < 1e-4


def test_hoje_antes_da_compra_levanta_value_error() -> None:
    """Data de hoje anterior à compra ⇒ ValueError."""
    with pytest.raises(ValueError):
        marktomarket.exata(
            data_compra=HOJE,
            data_hoje=COMPRA,
            data_vencimento=VENC,
            pu_compra=780.0,
            taxa_compra=0.10,
            taxa_mercado=0.10,
        )


def test_titulo_vencido_levanta_value_error() -> None:
    """Marcação em título já vencido (hoje >= vencimento)."""
    with pytest.raises(ValueError):
        marktomarket.exata(
            data_compra=COMPRA,
            data_hoje=VENC,
            data_vencimento=VENC,
            pu_compra=780.0,
            taxa_compra=0.10,
            taxa_mercado=0.10,
        )
    with pytest.raises(ValueError):
        marktomarket.exata(
            data_compra=COMPRA,
            data_hoje=date(2032, 1, 2),
            data_vencimento=VENC,
            pu_compra=780.0,
            taxa_compra=0.10,
            taxa_mercado=0.10,
        )
