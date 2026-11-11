"""Testes do cálculo de Preço Unitário (PU)."""

from __future__ import annotations

from datetime import date

import pytest

from rfquant.pricing import pu
from rfquant.pricing.fluxo_caixa import Fluxo, gerar_fluxos


def test_zero_cupom_pu_exato_1e9() -> None:
    """Zero-cupom com prazo de exatamente 252 DU do calendário real
    (05/01/2026 → 08/01/2027) a 10% deve ter PU = 1000/1,1 com tolerância
    relativa 1e-9. Antes do calendário real o caso usava 365 dc pela
    aproximação ``dias corridos × 252/365`` — substituída pelo calendário
    real (tests/test_data_calendario.py)."""
    p = pu.calcular(
        data_compra=date(2026, 1, 5),
        data_vencimento=date(2027, 1, 8),
        taxa_anual=0.10,
        valor_nominal=1000.0,
        taxa_cupom_anual=0.0,
    )
    assert p == pytest.approx(1000.0 / 1.10, rel=1e-9)


def test_pu_cupom_semestral_soma_dos_fluxos_descontados() -> None:
    """PU com cupons semestrais = soma dos fluxos descontados,
    verificado com a soma re-derivada explicitamente no teste."""
    data_compra, vencimento = date(2026, 1, 1), date(2027, 1, 1)
    taxa, cupom = 0.10, 0.08
    p = pu.calcular(data_compra, vencimento, taxa, 1000.0, cupom)

    esperado = sum(
        f.valor / (1 + taxa) ** (pu.dias_uteis(data_compra, f.data) / 252)
        for f in gerar_fluxos(
            data_compra=data_compra,
            data_vencimento=vencimento,
            valor_nominal=1000.0,
            taxa_cupom_anual=cupom,
            frequencia_cupom=2,
        )
    )
    assert p == pytest.approx(esperado, rel=1e-9)


@pytest.mark.parametrize(("taxa"), [-1.0, -1.5, -2.0])
def test_taxa_menos_ou_igual_menos_100_pct_levanta_value_error(taxa: float) -> None:
    """Taxa <= -100% deve levantar ValueError com mensagem pt-BR
    (hoje: -1,0 vira ZeroDivisionError; -1,5 vira PU negativo silencioso)."""
    with pytest.raises(ValueError, match="-100%"):
        pu.calcular(date(2026, 1, 1), date(2031, 1, 1), taxa, 1000.0, 0.0)


def test_zero_cupom_taxa_zero() -> None:
    """Com taxa zero, PU deve ser igual ao valor nominal."""
    p = pu.calcular(
        data_compra=date(2026, 1, 1),
        data_vencimento=date(2027, 1, 1),
        taxa_anual=0.0,
        valor_nominal=1000.0,
        taxa_cupom_anual=0.0,
    )
    assert p == pytest.approx(1000.0, rel=1e-9)


def test_pu_dimiui_com_taxa() -> None:
    """PU deve ser decrescente em relação à taxa de desconto."""
    p_baixo = pu.calcular(date(2026, 1, 1), date(2029, 1, 1), 0.08, 1000.0, 0.0)
    p_alto = pu.calcular(date(2026, 1, 1), date(2029, 1, 1), 0.15, 1000.0, 0.0)
    assert p_alto < p_baixo


def test_pu_com_cupom_maior_que_zero_cupom() -> None:
    """Um título com cupom deve ter PU maior que o mesmo zero-cupom."""
    p_sem_cupom = pu.calcular(
        date(2026, 1, 1), date(2031, 1, 1), 0.10, 1000.0, taxa_cupom_anual=0.0
    )
    p_com_cupom = pu.calcular(
        date(2026, 1, 1), date(2031, 1, 1), 0.10, 1000.0, taxa_cupom_anual=0.08
    )
    assert p_com_cupom > p_sem_cupom


def test_pu_data_invalida() -> None:
    """Vencimento anterior à compra deve levantar ValueError."""
    with pytest.raises(ValueError):
        pu.calcular(date(2027, 1, 1), date(2026, 1, 1), 0.10)


def test_dias_uteis_positivo() -> None:
    """Dias úteis entre duas datas deve ser sempre positivo."""
    du = pu.dias_uteis(date(2026, 1, 1), date(2026, 6, 1))
    assert du > 0


def test_fluxos_liquidados_aplica_a_regra_de_liquidacao_d1() -> None:
    """Convenção do PU oficial: cupom pago no dia útil seguinte à data-base
    pertence ao vendedor (sai do preço); do segundo dia útil em diante, fica.
    Caso medido: 30/06/2026 × cupom de 01/07/2026 — sem o filtro o erro
    contra o oficial era 4,97e-2 (regressão NTN-F)."""
    data_base = date(2026, 6, 30)  # terça; próximo dia útil = 01/07 (quarta)
    fluxos = [
        Fluxo(data=date(2026, 7, 1), valor=48.81, tipo="cupom"),
        Fluxo(data=date(2026, 7, 2), valor=48.81, tipo="cupom"),
        Fluxo(data=date(2027, 1, 1), valor=1048.81, tipo="principal"),
    ]
    liquidados = pu.fluxos_liquidados(fluxos, data_base)
    assert [f.data for f in liquidados] == [date(2026, 7, 2), date(2027, 1, 1)]


def test_fluxos_liquidados_mantem_o_fluxo_final_na_janela_d1() -> None:
    """Na véspera do vencimento o oficial mantém o resgate no PU — a exceção
    é só para cupons intermediários. Medido: 30/06/2010 (venc 01/07/2010) —
    excluir o fluxo final daria erro 1,0 contra o oficial (3,75e-4 mantendo)."""
    data_base = date(2026, 6, 30)
    fluxos = [Fluxo(data=date(2026, 7, 1), valor=1048.81, tipo="principal")]
    assert [f.data for f in pu.fluxos_liquidados(fluxos, data_base)] == [date(2026, 7, 1)]


def test_pu_na_vespera_do_vencimento_e_o_fluxo_final_descontado() -> None:
    """PU a 1 dia útil do vencimento = fluxo final descontado por 1 DU —
    o comportamento do oficial na véspera (não é zero)."""
    compra, venc = date(2026, 12, 31), date(2027, 1, 4)  # próximo dia útil de 31/12
    esperado = 1000.0 / 1.10 ** (1 / 252)
    assert pu.calcular(compra, venc, 0.10) == pytest.approx(esperado, rel=1e-9)


def test_precificar_nominal_retorna_avaliacao_completa_consistente() -> None:
    """Seam 1: `rfquant.pricing.precificar` retorna `AvaliacaoTitulo` com PU,
    durations, DV01, convexidade e current yield consistentes em 1 passagem."""
    from rfquant.pricing import AvaliacaoTitulo, precificar

    # Caso 1: zero-cupom de exatos 252 DU (t = 1,0 ano) a 10% a.a.
    av_zero = precificar(
        data_base=date(2026, 1, 5),
        data_vencimento=date(2027, 1, 8),
        taxa_anual=0.10,
        valor_nominal=1000.0,
        taxa_cupom_anual=0.0,
    )
    assert isinstance(av_zero, AvaliacaoTitulo)
    assert av_zero.cotacao is None
    assert av_zero.pu == pytest.approx(1000.0 / 1.10, rel=1e-12)
    assert av_zero.duration_macaulay == pytest.approx(1.0, rel=1e-12)
    assert av_zero.duration_modificada == pytest.approx(1.0 / 1.10, rel=1e-12)
    assert av_zero.dv01 == pytest.approx(1000.0 / 1.10 - 1000.0 / 1.1001, rel=1e-12)
    assert av_zero.convexidade == pytest.approx(2.0 / (1.10**2), rel=1e-12)
    assert av_zero.current_yield == 0.0

    # Caso 2: título com cupom semestral de 6% a.a. (README: 2026-10-01 -> 2035-05-15 a 6,2%)
    av_cupom = precificar(
        data_base=date(2026, 10, 1),
        data_vencimento=date(2035, 5, 15),
        taxa_anual=0.062,
        valor_nominal=1000.0,
        taxa_cupom_anual=0.06,
    )
    cupom_anual_esperado = 2 * 1000.0 * ((1.06**0.5) - 1.0)
    assert av_cupom.cotacao is None
    assert av_cupom.current_yield == pytest.approx(cupom_anual_esperado / av_cupom.pu, rel=1e-12)


def test_precificar_modo_vna_ntnb_unifica_cotacao_pu_e_risco() -> None:
    """Seam 1 (IPCA+/VNA): `precificar(..., vna=4500.0)` calcula cotação (% VNA),
    PU em R$, DV01 escalado pelo VNA e Current Yield sobre o cupom composto."""
    from rfquant.pricing import precificar

    av_ntnb = precificar(
        data_base=date(2026, 10, 1),
        data_vencimento=date(2035, 5, 15),
        taxa_anual=0.062,
        taxa_cupom_anual=0.06,
        vna=4500.0,
    )
    av_base100 = precificar(
        data_base=date(2026, 10, 1),
        data_vencimento=date(2035, 5, 15),
        taxa_anual=0.062,
        valor_nominal=100.0,
        taxa_cupom_anual=0.06,
    )
    assert av_ntnb.cotacao is not None
    assert av_ntnb.cotacao == pytest.approx(av_base100.pu, rel=1e-12)
    assert av_ntnb.pu == pytest.approx(4500.0 * av_base100.pu / 100.0, rel=1e-12)
    assert av_ntnb.duration_macaulay == pytest.approx(av_base100.duration_macaulay, rel=1e-12)
    assert av_ntnb.duration_modificada == pytest.approx(av_base100.duration_modificada, rel=1e-12)
    assert av_ntnb.convexidade == pytest.approx(av_base100.convexidade, rel=1e-12)
    assert av_ntnb.dv01 == pytest.approx(av_base100.dv01 * 45.0, rel=1e-12)
    assert av_ntnb.current_yield == pytest.approx(av_base100.current_yield, rel=1e-12)
