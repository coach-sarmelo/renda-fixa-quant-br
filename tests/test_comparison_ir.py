"""Testes de cálculo de IR e comparação de produtos."""

from __future__ import annotations

from datetime import date

import pytest

from rfquant.comparison import ir, taxa_equivalente


# ----------------------------------------------------------------------
# Tabela regressiva
# ----------------------------------------------------------------------
@pytest.mark.parametrize(
    ("prazo", "esperado"),
    [
        (90, 0.225),
        (180, 0.225),
        (181, 0.200),
        (360, 0.200),
        (361, 0.175),
        (720, 0.175),
        (721, 0.150),
        (3650, 0.150),
    ],
)
def test_aliquota_ir(prazo: int, esperado: float) -> None:
    assert ir.aliquota(prazo) == pytest.approx(esperado)


def test_ir_devido_isento() -> None:
    assert ir.ir_devido(1000.0, 400, isento=True) == 0.0


def test_ir_devido_normal() -> None:
    assert ir.ir_devido(1000.0, 400) == pytest.approx(175.0)


def test_prazo_invalido() -> None:
    with pytest.raises(ValueError):
        ir.aliquota(0)


# ----------------------------------------------------------------------
# IOF
# ----------------------------------------------------------------------
def test_iof_zero_apos_30_dias() -> None:
    assert ir.iof(1000.0, 30) == 0.0
    assert ir.iof(1000.0, 100) == 0.0


def test_iof_primeiro_dia() -> None:
    """No 1º dia, 96% do rendimento é consumido por IOF."""
    assert ir.iof(1000.0, 1) == pytest.approx(960.0)


# ----------------------------------------------------------------------
# calcular() encadeado e casos-limite
# ----------------------------------------------------------------------
def test_calcular_encadeado_iof_antes_do_ir() -> None:
    """IOF primeiro; IR incide sobre a base já líquida de IOF.
    15 dias, bruto 1000: IOF 50% = 500 → base IR 500 → IR 22,5% = 112,50."""
    r = ir.calcular(1000.0, 15)
    assert r.iof == pytest.approx(500.0)
    assert r.ir == pytest.approx(112.5)
    assert r.rendimento_liquido == pytest.approx(387.5)
    assert r.aliquota_ir == pytest.approx(0.225)


def test_calcular_sem_iof_apos_30_dias() -> None:
    """Resgate com ≥ 30 dias não tem IOF; IR incide sobre o bruto."""
    r = ir.calcular(1000.0, 100)
    assert r.iof == 0.0
    assert r.ir == pytest.approx(225.0)
    assert r.rendimento_liquido == pytest.approx(775.0)


def test_calcular_isento_paga_iof_mas_nao_ir() -> None:
    """Isenção é de IR; IOF regressivo < 30 dias continua devido."""
    r = ir.calcular(1000.0, 15, isento=True)
    assert r.iof == pytest.approx(500.0)
    assert r.ir == 0.0
    assert r.rendimento_liquido == pytest.approx(500.0)


@pytest.mark.parametrize(("rendimento"), [-100.0, 0.0])
def test_rendimento_nao_positivo_ir_zero(rendimento: float) -> None:
    """Rendimento ≤ 0 ⇒ IR 0 (sem IR sobre perda)."""
    assert ir.ir_devido(rendimento, 720) == 0.0
    r = ir.calcular(rendimento, 100)
    assert r.ir == 0.0
    assert r.rendimento_liquido == pytest.approx(rendimento)


def test_datas_invertidas_levanta_value_error() -> None:
    """Data final < inicial ⇒ ValueError."""
    with pytest.raises(ValueError):
        ir.prazo_entre_datas(date(2026, 2, 1), date(2026, 1, 1))
    with pytest.raises(ValueError):
        ir.aliquota_por_datas(date(2026, 2, 1), date(2026, 1, 1))


# ----------------------------------------------------------------------
# Ramos não exercidos - caracterização declarada (verde de 1ª)
# ----------------------------------------------------------------------
def test_aliquota_acima_do_teto_da_tabela() -> None:
    """Prazo acima do último limite (10**9) escapa de todas as faixas do loop
    e cai no fallback: devolve a banda final, 15% (FAIXAS_IR[-1] = (10**9, 0.150))."""
    # 10**9 + 1 > 180, 360, 720 e 10**9 ⇒ nenhuma faixa casa ⇒ fallback 0.150
    assert ir.aliquota(10**9 + 1) == pytest.approx(0.150)


def test_rendimento_liquido_tributado_e_isento() -> None:
    """900 dias > 720 ⇒ IR 15%: 1000 - 1000 × 0.15 = 850. Isento: bruto integral."""
    assert ir.rendimento_liquido(1000.0, 900) == pytest.approx(850.0)
    assert ir.rendimento_liquido(1000.0, 100, isento=True) == pytest.approx(1000.0)


@pytest.mark.parametrize("prazo", [0, -3])
def test_iof_prazo_menor_que_um_dia(prazo: int) -> None:
    """Prazo < 1 dia não tem IOF: a tabela regressiva começa no 1º dia (96%)."""
    assert ir.iof(1000.0, prazo) == 0.0


def test_rentabilidade_liquida_pct_normal_e_guarda() -> None:
    """900 dias: IOF 0 (≥ 30), IR 15% de 1000 = 150, líquido 850 ⇒ 850/1000 = 0.85.
    Guarda: bruto ≤ 0 ⇒ razão indefinida, devolve 0.0 (sem divisão)."""
    r = ir.calcular(1000.0, 900)
    assert r.rentabilidade_liquida_pct == pytest.approx(0.85)
    assert ir.calcular(0.0, 900).rentabilidade_liquida_pct == 0.0
    assert ir.calcular(-500.0, 900).rentabilidade_liquida_pct == 0.0


def test_prazo_entre_datas_ano_bissexto() -> None:
    """2024 é bissexto: 1/jan → 1/jul = 31+29+31+30+31+30 = 182 dias corridos."""
    assert ir.prazo_entre_datas(date(2024, 1, 1), date(2024, 7, 1)) == 182


def test_aliquota_por_datas_isento() -> None:
    """Isento por datas ⇒ alíquota 0 em qualquer prazo (LCI/LCA).
    Contraste no mesmo prazo: 1/jan → 18/jun/2026 = 30+28+31+30+31+18 = 168
    dias ≤ 180 ⇒ 22,5% para o tributado."""
    assert ir.aliquota_por_datas(date(2026, 1, 1), date(2026, 6, 18), isento=True) == 0.0
    assert ir.aliquota_por_datas(date(2026, 1, 1), date(2026, 6, 18)) == pytest.approx(0.225)


# ----------------------------------------------------------------------
# Taxa equivalente
# ----------------------------------------------------------------------
def test_isento_equivalente_maior_que_taxa_isento() -> None:
    """Taxa isenta deve ser menor que a tributada equivalente."""
    taxa_isento = 0.10
    taxa_trib = taxa_equivalente.isento_equivalente_a_tributado(taxa_isento, 720)
    assert taxa_trib > taxa_isento


def test_tributado_equivalente_menor_que_bruto() -> None:
    """Taxa isenta equivalente deve ser menor que a tributada."""
    taxa_trib = 0.12
    taxa_isento = taxa_equivalente.tributado_equivalente_a_isento(taxa_trib, 720)
    assert taxa_isento < taxa_trib


def test_cdi_para_taxa_anual() -> None:
    assert taxa_equivalente.cdi_para_taxa_anual(1.10, 0.13) == pytest.approx(0.143)


def test_pre_para_ipca_mais() -> None:
    """Fisher: prefixado 12%, IPCA 4% → real ~7,69%."""
    real = taxa_equivalente.pre_para_ipca_mais(0.12, 0.04)
    assert real == pytest.approx(0.0769, abs=1e-4)


def test_comparar_produtos() -> None:
    """Comparação deve ordenar por taxa líquida decrescente."""
    produtos = [
        taxa_equivalente.ProdutoRF("CDB 12%", 0.12, 720, isento=False),
        taxa_equivalente.ProdutoRF("LCI 10.5%", 0.105, 720, isento=True),
        taxa_equivalente.ProdutoRF("Tesouro 13%", 0.13, 720, isento=False),
    ]
    resultados = taxa_equivalente.comparar(produtos)
    # Ordenados por taxa líquida decrescente
    taxas = [r.taxa_liquida_anual for r in resultados]
    assert taxas == sorted(taxas, reverse=True)
