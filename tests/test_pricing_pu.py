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
