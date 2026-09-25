"""Testes da ETTJ — interpolação linear e Nelson-Siegel."""

from __future__ import annotations

import pytest

from rfquant.pricing import curva_juros
from rfquant.pricing.curva_juros import ETTJ

PONTOS = [(1.0, 0.115), (2.0, 0.118), (5.0, 0.125), (10.0, 0.135)]


def test_linear_reproduz_nos_exatamente() -> None:
    """A ETTJ linear reproduz cada nó com tolerância 1e-12."""
    e = ETTJ(PONTOS, metodo="linear")
    for prazo, taxa_no in PONTOS:
        assert e.taxa(prazo) == pytest.approx(taxa_no, abs=1e-12)


def test_linear_interpola_entre_nos() -> None:
    """Interpolação linear — taxa(3,5) no meio do segmento 2→5."""
    e = ETTJ(PONTOS, metodo="linear")
    esperado = 0.118 + ((3.5 - 2.0) / (5.0 - 2.0)) * (0.125 - 0.118)
    assert e.taxa(3.5) == pytest.approx(esperado, abs=1e-12)


def test_fator_desconto_consistente() -> None:
    """Fator de desconto = (1 + taxa(prazo))^(-prazo)."""
    e = ETTJ(PONTOS, metodo="linear")
    assert e.fator_desconto(2.0) == pytest.approx((1 + 0.118) ** (-2.0), rel=1e-12)


def test_nelson_siegel_ajusta_nos_com_erro_menor_1e3() -> None:
    """Nelson-Siegel ajusta os nós com erro < 1e-3."""
    e = ETTJ(PONTOS, metodo="nelson_siegel")
    for prazo, taxa_no in PONTOS:
        assert e.taxa(prazo) == pytest.approx(taxa_no, abs=1e-3)


def test_nelson_siegel_interpolacao_dentro_da_faixa_da_curva() -> None:
    """Interpolação paramétrica fica dentro da faixa [mín, máx] dos nós."""
    e = ETTJ(PONTOS, metodo="nelson_siegel")
    for prazo in (3.5, 7.0, 1.5):
        assert 0.110 <= e.taxa(prazo) <= 0.140


def test_fallback_para_linear_se_fit_falhar(monkeypatch) -> None:
    """Fit que falha degrada para flat = taxa longa (fallback)."""

    def fit_que_falha(*args: object, **kwargs: object) -> object:
        raise RuntimeError("fit indisponível")

    monkeypatch.setattr(curva_juros, "curve_fit", fit_que_falha)
    e = ETTJ(PONTOS, metodo="nelson_siegel")
    for prazo in (1.0, 3.5, 10.0):
        assert e.taxa(prazo) == pytest.approx(0.135, abs=1e-12)


def test_menos_de_dois_pontos_levanta_value_error() -> None:
    """ETTJ com < 2 pontos é degenerada ⇒ ValueError."""
    with pytest.raises(ValueError):
        ETTJ([(1.0, 0.115)])


def test_pontos_fora_de_ordem_levanta_value_error() -> None:
    """Nós desordenados ⇒ ValueError."""
    with pytest.raises(ValueError):
        ETTJ([(2.0, 0.118), (1.0, 0.115)])


@pytest.mark.parametrize(("prazo"), [0.0, -1.0])
def test_prazo_nao_positivo_levanta_value_error(prazo: float) -> None:
    """Prazo ≤ 0 na consulta ⇒ ValueError."""
    e = ETTJ(PONTOS, metodo="linear")
    with pytest.raises(ValueError):
        e.taxa(prazo)
