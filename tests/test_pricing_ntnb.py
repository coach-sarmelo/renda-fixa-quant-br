"""Testes de precificação de NTN-B e NTN-B Principal (módulo ntnb).

Identidades matemáticas usam rel=1e-9/1e-12 (mesma prática de
test_pricing_pu.py); o literal do cupom composto (2,956301, 6 casas)
tem erro de arredondamento medido de 4,1e-7 e tolerância abs=1e-6
(~2,4× o erro).
"""

from __future__ import annotations

from datetime import date

import pytest

from rfquant.pricing import ntnb, pu
from rfquant.pricing.fluxo_caixa import cupom_periodo, gerar_fluxos

# Vencimento longo típico de NTN-B em leilão (data-base 15/05) e taxa real
# de mercado — usado nos testes de proporção PU/VNA e monotonia.
_COMPRA = date(2026, 10, 1)
_VENC = date(2035, 5, 15)
_TAXA_REAL = 0.062


def test_cotacao_principal_exata_em_252_du() -> None:
    """NTN-B Principal (cupom 0) com prazo de exatamente 252 DU do
    calendário real (05/01/2026 → 08/01/2027, o mesmo par medido em
    test_pricing_pu.py): cotação = 100/(1+r)^(252/252) — a fórmula exata
    da STN para o Principal."""
    cot = ntnb.cotacao(date(2026, 1, 5), date(2027, 1, 8), 0.07, taxa_cupom_anual=0.0)
    assert cot == pytest.approx(100.0 / 1.07, rel=1e-9)


def test_cupom_composto_stn_e_2_956301_por_100_de_vna() -> None:
    """Cupom semestral da NTN-B na convenção composta STN: 6% a.a. →
    2,956301 por 100 de VNA — é o valor que gerar_fluxos efetivamente paga
    (e que a cotação embute) sobre a base 100."""
    assert cupom_periodo(100.0, 0.06, 2) == pytest.approx(2.956301, abs=1e-6)
    fluxos = gerar_fluxos(
        date(2026, 1, 2), date(2026, 8, 15), valor_nominal=100.0, taxa_cupom_anual=0.06
    )
    cupom, final = fluxos[0], fluxos[-1]
    assert cupom.tipo == "cupom"
    assert cupom.valor == pytest.approx(2.956301, abs=1e-6)
    assert final.tipo == "principal"
    assert final.valor == pytest.approx(100.0 + 2.956301, abs=1e-6)


@pytest.mark.parametrize("vna", [1.0, 100.0, 4500.0, 12345.67])
def test_calcular_e_vna_x_cotacao_sobre_base_100(vna: float) -> None:
    """PU = VNA × cotação / 100 — identidade paramétrica em VNA."""
    cot = ntnb.cotacao(_COMPRA, _VENC, _TAXA_REAL)
    pu_vna = ntnb.calcular(_COMPRA, _VENC, _TAXA_REAL, vna)
    assert pu_vna == pytest.approx(vna * cot / 100.0, rel=1e-12)


def test_calcular_e_linear_no_vna() -> None:
    """Linearidade em VNA: PU(1000) + PU(2500) = PU(3500)."""
    p1 = ntnb.calcular(_COMPRA, _VENC, _TAXA_REAL, 1000.0)
    p2 = ntnb.calcular(_COMPRA, _VENC, _TAXA_REAL, 2500.0)
    p3 = ntnb.calcular(_COMPRA, _VENC, _TAXA_REAL, 3500.0)
    assert p1 + p2 == pytest.approx(p3, rel=1e-12)


def test_cotacao_e_decrescente_na_taxa_real() -> None:
    """Quanto maior a taxa real de desconto, menor a cotação."""
    cots = [ntnb.cotacao(_COMPRA, _VENC, r) for r in (0.02, 0.062, 0.10)]
    assert cots[0] > cots[1] > cots[2]


@pytest.mark.parametrize("vna", [0.0, -1.0, -4500.0])
def test_calcular_vna_nao_positivo_levanta_value_error(vna: float) -> None:
    """VNA <= 0 não tem sentido econômico: ValueError pt-BR antes de
    qualquer cálculo."""
    with pytest.raises(ValueError, match="VNA"):
        ntnb.calcular(_COMPRA, _VENC, _TAXA_REAL, vna)


@pytest.mark.parametrize("taxa", [-1.0, -1.5])
def test_cotacao_taxa_real_ate_menos_100_pct_levanta_value_error(taxa: float) -> None:
    """Taxa real <= -100% (fator de desconto nulo/negativo): ValueError do
    núcleo de desconto reutilizado, com a mensagem pt-BR de sempre."""
    with pytest.raises(ValueError, match="-100%"):
        ntnb.cotacao(_COMPRA, _VENC, taxa)


def test_cotacao_exclui_cupom_na_janela_d1() -> None:
    """Espelho do contrato D+1 de test_pricing_pu.py: data-base 30/06/2026
    (terça) com cupom em 01/07/2026 — o cupom do próximo dia útil pertence
    ao vendedor e sai da cotação."""
    data_base = date(2026, 6, 30)
    venc = date(2027, 7, 1)
    fluxos_brutos = gerar_fluxos(data_base, venc, valor_nominal=100.0, taxa_cupom_anual=0.06)
    # o cupom na janela D+1 existe no bruto — sem ele o teste não provaria nada
    assert any(f.data == date(2026, 7, 1) and f.tipo == "cupom" for f in fluxos_brutos)

    cot = ntnb.cotacao(data_base, venc, _TAXA_REAL)
    esperado = sum(
        f.valor / (1 + _TAXA_REAL) ** (pu.dias_uteis(data_base, f.data) / 252)
        for f in pu.fluxos_liquidados(fluxos_brutos, data_base)
    )
    assert cot == pytest.approx(esperado, rel=1e-12)
    # com o cupom de 01/07 embutido (sem a regra D+1) o preço seria maior
    sem_filtro = sum(
        f.valor / (1 + _TAXA_REAL) ** (pu.dias_uteis(data_base, f.data) / 252)
        for f in fluxos_brutos
    )
    assert cot < sem_filtro


def test_cotacao_na_vespera_mantem_o_fluxo_final_na_janela_d1() -> None:
    """Na véspera do vencimento o fluxo FINAL fica embutido na cotação —
    a exceção da regra D+1 vale só para cupons intermediários (espelho do
    caso medido em test_pricing_pu.py)."""
    data_base, venc = date(2026, 6, 30), date(2026, 7, 1)  # próximo dia útil
    cot = ntnb.cotacao(data_base, venc, _TAXA_REAL)
    fluxo_final = 100.0 + cupom_periodo(100.0, 0.06, 2)
    esperado = fluxo_final / (1 + _TAXA_REAL) ** (pu.dias_uteis(data_base, venc) / 252)
    assert cot == pytest.approx(esperado, rel=1e-9)


@pytest.mark.parametrize(
    ("vencimento", "datas_esperadas"),
    [
        # par 15/02-15/08 (o caso 15/08/2026) e par 15/05-15/11: juntos,
        # as quatro datas-base da NTN-B
        (date(2026, 8, 15), [date(2026, 2, 15), date(2026, 8, 15)]),
        (date(2026, 11, 15), [date(2026, 5, 15), date(2026, 11, 15)]),
        (
            date(2029, 5, 15),
            [
                date(2026, 5, 15),
                date(2026, 11, 15),
                date(2027, 5, 15),
                date(2027, 11, 15),
                date(2028, 5, 15),
                date(2028, 11, 15),
                date(2029, 5, 15),
            ],
        ),
    ],
)
def test_datas_base_ancoradas_no_vencimento(vencimento: date, datas_esperadas: list[date]) -> None:
    """Cupons ancorados no vencimento caem nas datas-base da NTN-B
    (15/02, 15/05, 15/08, 15/11), com o principal na última."""
    fluxos = gerar_fluxos(date(2026, 1, 2), vencimento, valor_nominal=100.0, taxa_cupom_anual=0.06)
    assert [f.data for f in fluxos] == datas_esperadas
    assert fluxos[-1].tipo == "principal"
