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


# ----------------------------------------------------------------------
# Aproximada (fórmula linear por duration) e curva (lote de títulos)
# ----------------------------------------------------------------------
def test_aproximada_bate_com_a_formula_linear_a_mao() -> None:
    """A aproximada é a fórmula do docstring, à mão:
    PU_compra·(1 - D_mod·Δy) = 1000·(1 - 4·0,005) = 980,00; com Δy = 0
    ela devolve o próprio PU de compra (nenhum efeito de taxa)."""
    assert marktomarket.aproximada(1000.0, 0.10, 0.105, 4.0) == pytest.approx(980.0, abs=1e-9)
    assert marktomarket.aproximada(1000.0, 0.10, 0.10, 4.0) == pytest.approx(1000.0, abs=1e-12)


def test_curva_aplica_exata_a_cada_titulo_preservando_ordem_e_defaults() -> None:
    """`curva` marca cada título do lote com `exata`, na MESMA ordem da
    entrada; chaves opcionais ausentes assumem os defaults do contrato
    (nominal 1000, cupom 0, 2 cupons/ano) — provado recomputando `exata`
    com os mesmos argumentos e comparando campo a campo."""
    lote = [
        {
            "data_compra": date(2026, 1, 2),
            "data_vencimento": date(2029, 1, 2),
            "pu_compra": 780.0,
            "taxa_compra": 0.115,
            "taxa_mercado": 0.12,
        },
        {
            "data_compra": date(2026, 1, 2),
            "data_vencimento": date(2031, 1, 2),
            "pu_compra": 950.0,
            "taxa_compra": 0.10,
            "taxa_mercado": 0.09,
            "valor_nominal": 500.0,
            "taxa_cupom_anual": 0.06,
            "frequencia_cupom": 1,
        },
    ]
    resultados = marktomarket.curva(date(2026, 6, 2), lote)

    assert len(resultados) == 2
    for res, titulo in zip(resultados, lote, strict=True):
        esperado = marktomarket.exata(
            data_compra=titulo["data_compra"],
            data_hoje=date(2026, 6, 2),
            data_vencimento=titulo["data_vencimento"],
            pu_compra=titulo["pu_compra"],
            taxa_compra=titulo["taxa_compra"],
            taxa_mercado=titulo["taxa_mercado"],
            valor_nominal=titulo.get("valor_nominal", 1000.0),
            taxa_cupom_anual=titulo.get("taxa_cupom_anual", 0.0),
            frequencia_cupom=titulo.get("frequencia_cupom", 2),
        )
        assert res == esperado


def test_curva_com_lote_vazio_devolve_lista_vazia() -> None:
    """Lote vazio ⇒ lista vazia — sem exceção, sem marcação fantasma."""
    assert marktomarket.curva(date(2026, 6, 2), []) == []
