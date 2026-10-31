"""Testes da ETTJ — interpolação linear, flat-forward e Nelson-Siegel."""

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


def test_taxa_de_no_menor_ou_igual_a_menos_100_levanta_value_error() -> None:
    """Nó com taxa <= -100% (fator de capitalização nulo ou negativo) ⇒
    ValueError na construção, com a mesma mensagem do núcleo de PU.
    Antes da validação, o flat-forward (método default) quebrava com
    ZeroDivisionError opaco em (fator2 / fator1) ao interpolar sobre o
    segmento de taxa -100%; com taxa < -100% o pow devolvia complexo."""
    with pytest.raises(ValueError, match="-100%"):
        ETTJ([(1.0, -1.0), (2.0, 0.10)])
    with pytest.raises(ValueError, match="-100%"):
        ETTJ([(1.0, 0.10), (2.0, -1.5)])


@pytest.mark.parametrize(("prazo"), [0.0, -1.0])
def test_prazo_nao_positivo_levanta_value_error(prazo: float) -> None:
    """Prazo ≤ 0 na consulta ⇒ ValueError."""
    e = ETTJ(PONTOS, metodo="linear")
    with pytest.raises(ValueError):
        e.taxa(prazo)


# ----------------------------------------------------------------------
# taxas_vetor e utilitários de conversão de taxas
# ----------------------------------------------------------------------
def test_taxa_vetor_devolve_a_taxa_de_cada_prazo() -> None:
    """`taxa_vetor` é a consulta ponto a ponto empacotada em array: o
    resultado coincide com `taxa` chamada prazo a prazo, na mesma ordem."""
    e = ETTJ(PONTOS, metodo="linear")
    prazos = [1.0, 3.5, 10.0]
    vetor = e.taxa_vetor(prazos)
    assert vetor == pytest.approx([e.taxa(p) for p in prazos], rel=1e-12)
    # interpolação dentro da faixa e reprodução do nó de 10 anos
    assert 0.118 <= vetor[1] <= 0.125
    assert vetor[2] == pytest.approx(0.135, abs=1e-12)


def test_taxa_efetiva_para_nominal_bate_com_a_formula_e_inverte() -> None:
    """Efetiva→nominal é a fórmula j_nom = n·((1+j_ef)^(1/n) - 1): 10% a.a.
    efetivo com capitalização semestral dá ~9,7618% nominal — e o caminho
    de volta recupera a efetiva original (conversões inversas)."""
    nominal = curva_juros.taxa_efetiva_para_nominal(0.10, periodos=2)
    assert nominal == pytest.approx(2 * ((1.10) ** 0.5 - 1), rel=1e-12)
    assert curva_juros.taxa_nominal_para_efetiva(nominal, periodos=2) == pytest.approx(
        0.10, rel=1e-12
    )


def test_taxa_nominal_para_efetiva_bate_com_a_conta_a_mao() -> None:
    """Nominal 10% com capitalização mensal capitaliza (1 + 0,10/12)^12:
    efetiva ≈ 10,4713% — maior que a nominal, como esperado."""
    efetiva = curva_juros.taxa_nominal_para_efetiva(0.10, periodos=12)
    assert efetiva == pytest.approx((1 + 0.10 / 12) ** 12 - 1, rel=1e-12)
    assert efetiva > 0.10


@pytest.mark.parametrize(("periodos"), [0, -2])
def test_periodos_nao_positivo_nas_conversoes_levanta_value_error(periodos: int) -> None:
    """Número de períodos ≤ 0 nas duas conversões de capitalização ⇒
    ValueError (entrada sem sentido não vira número absurdo)."""
    with pytest.raises(ValueError):
        curva_juros.taxa_efetiva_para_nominal(0.10, periodos=periodos)
    with pytest.raises(ValueError):
        curva_juros.taxa_nominal_para_efetiva(0.10, periodos=periodos)


def test_relacao_de_fisher_conecta_pre_e_real_nos_dois_sentidos() -> None:
    """Fisher exata: (1+pre) = (1+real)·(1+ipca). Prefixado 12% com IPCA
    esperado de 5% ⇒ real ≈ 6,6667%; o caminho de volta reconstrói o 12%."""
    real = curva_juros.taxa_pre_para_pos(0.12, 0.05)
    assert real == pytest.approx(1.12 / 1.05 - 1, rel=1e-12)
    assert curva_juros.taxa_pos_para_pre(real, 0.05) == pytest.approx(0.12, rel=1e-12)


# ----------------------------------------------------------------------
# Flat-forward (padrão B3/ANBIMA)
# ----------------------------------------------------------------------
def test_flat_forward_reproduz_nos_exatamente() -> None:
    """Flat-forward reproduz cada nó com tolerância 1e-12."""
    e = ETTJ(PONTOS, metodo="flat_forward")
    for prazo, taxa_no in PONTOS:
        assert e.taxa(prazo) == pytest.approx(taxa_no, abs=1e-12)


def test_flat_forward_interpola_sem_arbitragem() -> None:
    """Taxa interpolada fica entre os nós vizinhos (sem arbitragem)."""
    e = ETTJ(PONTOS, metodo="flat_forward")
    taxa_3_5 = e.taxa(3.5)
    # 3.5 está entre nós 2.0 (11.8%) e 5.0 (12.5%)
    assert 0.118 <= taxa_3_5 <= 0.125


def test_flat_forward_difere_da_linear() -> None:
    """Flat-forward produz resultado diferente da interpolação linear
    (senão não houve mudança real)."""
    e_ff = ETTJ(PONTOS, metodo="flat_forward")
    e_lin = ETTJ(PONTOS, metodo="linear")
    # 3.5 anos: os dois métodos diferem (FF é não-linear em taxa)
    assert e_ff.taxa(3.5) != pytest.approx(e_lin.taxa(3.5), abs=1e-6)


def test_flat_forward_forward_constante_entre_vertices() -> None:
    """Dentro de um segmento, a forward implícita é constante.

    Forward de t a t+dt: f = [(1+r(t+dt))^(t+dt) / (1+r(t))^t]^(1/dt) - 1
    Em flat-forward, f(t→t+dt) é constante para t ∈ [t₁, t₂)."""
    e = ETTJ(PONTOS, metodo="flat_forward")

    def forward_1y(t: float) -> float:
        dt = 0.01
        r_t = e.taxa(t)
        r_tdt = e.taxa(t + dt)
        return float(((1 + r_tdt) ** (t + dt) / (1 + r_t) ** t) ** (1 / dt) - 1)

    # Dentro do segmento 2→5 anos, a forward deve ser constante
    f_25 = forward_1y(2.5)
    f_35 = forward_1y(3.5)
    f_45 = forward_1y(4.5)
    assert f_25 == pytest.approx(f_35, rel=1e-6)
    assert f_35 == pytest.approx(f_45, rel=1e-6)


def test_flat_forward_e_default() -> None:
    """O método padrão agora é flat_forward (padrão B3/ANBIMA)."""
    e = ETTJ(PONTOS)  # sem metodo explícito
    assert e.metodo == "flat_forward"


def test_flat_forward_extrapolacao_flat() -> None:
    """Prazo fora do intervalo dos nós: extrapola flat."""
    e = ETTJ(PONTOS, metodo="flat_forward")
    assert e.taxa(0.5) == pytest.approx(PONTOS[0][1], abs=1e-12)
    assert e.taxa(15.0) == pytest.approx(PONTOS[-1][1], abs=1e-12)
