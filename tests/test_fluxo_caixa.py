"""Testes da matemática do cupom composto (convenção STN/ANBIMA).

Enquanto test_pricing_fluxo_caixa.py cobre datas, âncoras e validações da
geração de fluxos, este arquivo prova a FÓRMULA do cupom: composto,
valor_nominal × ((1 + taxa)^(1/frequência) - 1), e não linear.
"""

from __future__ import annotations

from datetime import date

import pytest

from rfquant.pricing import pu
from rfquant.pricing.fluxo_caixa import cupom_periodo, gerar_fluxos


def test_cupom_ntn_f_10_porcento_semestral() -> None:
    """Título com cupom de 10% a.a. e frequência semestral paga por cupom
    1000 × ((1 + 0,10)^(1/2) - 1) = 48,808848... (convenção composta
    STN/ANBIMA, valor conferido com aritmética decimal de 50 dígitos) —
    e não 50,00, que seria a divisão linear."""
    fluxos = gerar_fluxos(
        data_compra=date(2030, 1, 1),
        data_vencimento=date(2031, 1, 1),
        valor_nominal=1000.0,
        taxa_cupom_anual=0.10,
        frequencia_cupom=2,
    )
    assert [f.valor for f in fluxos if f.tipo == "cupom"] == [
        pytest.approx(48.808848170151547, rel=1e-9)
    ]
    assert fluxos[-1].tipo == "principal"
    assert fluxos[-1].valor == pytest.approx(1048.808848170151547, rel=1e-9)


@pytest.mark.parametrize(
    ("frequencia", "cupom_esperado"),
    [
        (1, 100.0),
        (2, 48.808848170151547),
        (4, 24.113689084445129),
    ],
)
def test_cupom_composto_conferido_a_mao_por_frequencia(
    frequencia: int, cupom_esperado: float
) -> None:
    """Para frequências 1, 2 e 4 o cupom vale 1000 × ((1 + 0,10)^(1/f) - 1)
    conferido à mão: 100,00 (= 1,10¹ - 1), 48,808848... (= 1,10^½ - 1) e
    24,113689... (= 1,10^¼ - 1) — constantes obtidas com decimal de 50
    dígitos, fora do pow de float da implementação. Para f = 1 não há cupom
    intermediário e o valor entra no fluxo de principal (1000 + cupom) do
    vencimento, coberto pela segunda asserção."""
    fluxos = gerar_fluxos(
        data_compra=date(2031, 1, 1),
        data_vencimento=date(2031, 12, 31),
        valor_nominal=1000.0,
        taxa_cupom_anual=0.10,
        frequencia_cupom=frequencia,
    )
    assert all(f.valor == pytest.approx(cupom_esperado, rel=1e-9) for f in fluxos[:-1])
    assert fluxos[-1].tipo == "principal"
    assert fluxos[-1].valor == pytest.approx(1000.0 + cupom_esperado, rel=1e-9)


def test_cupom_periodo_e_o_valor_pago_pelos_fluxos() -> None:
    """`cupom_periodo` devolve o cupom composto por período (48,808848...
    para 10% a.a. semestral, constante conferida com decimal de 50 dígitos)
    e é exatamente o valor que gerar_fluxos insere em cada data de cupom —
    a fórmula vive num único lugar, sem cópia divergente no consumidor."""
    cupom = cupom_periodo(1000.0, 0.10, 2)
    assert cupom == pytest.approx(48.808848170151547, rel=1e-9)
    fluxos = gerar_fluxos(
        data_compra=date(2030, 1, 1),
        data_vencimento=date(2031, 1, 1),
        valor_nominal=1000.0,
        taxa_cupom_anual=0.10,
        frequencia_cupom=2,
    )
    assert all(f.valor == pytest.approx(cupom, rel=1e-12) for f in fluxos[:-1])


def test_roundtrip_pu_calcular_desconta_fluxos_compostos() -> None:
    """Roundtrip: pu.calcular — chamado posicionalmente, provando a assinatura
    inalterada — devolve a soma dos fluxos de gerar_fluxos descontados a
    (1 + y)^(du/252). A desigualdade final prova que o cupom que atravessou o
    cálculo é o composto (48,808848...) e não o linear (50,00): mesmos
    vencimentos e mesmo desconto — cupom maior daria PU estritamente maior,
    então um PU que voltasse a usar cupom linear falharia nesta comparação."""
    data_compra = date(2030, 1, 1)
    data_vencimento = date(2031, 1, 1)
    taxa = 0.12

    pu_composto = pu.calcular(data_compra, data_vencimento, taxa, 1000.0, 0.10, 2)

    fluxos = gerar_fluxos(data_compra, data_vencimento, 1000.0, 0.10, 2)
    esperado = sum(
        f.valor / (1 + taxa) ** (pu.dias_uteis(data_compra, f.data) / pu.DU_ANO) for f in fluxos
    )
    assert pu_composto == pytest.approx(esperado, rel=1e-12)

    fator_julho = (1 + taxa) ** (pu.dias_uteis(data_compra, date(2030, 7, 1)) / pu.DU_ANO)
    fator_janeiro = (1 + taxa) ** (pu.dias_uteis(data_compra, data_vencimento) / pu.DU_ANO)
    pu_linear = 50.0 / fator_julho + 1050.0 / fator_janeiro
    assert pu_composto < pu_linear
