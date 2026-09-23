"""Testes de taxa equivalente."""

from __future__ import annotations

import pytest

from rfquant.comparison import taxa_equivalente


# ----------------------------------------------------------------------
# % CDI e o inverso taxa_anual_para_cdi
# ----------------------------------------------------------------------
def test_cdi_para_taxa_anual_valor_do_ac() -> None:
    """110% do CDI com CDI a 13% -> 14,3% a.a. (conta à mão: 1,10 x 0,13 = 0,143)."""
    # 1,10 x 0,13 = 0,143; em IEEE-754 o produto fica 1 ulp acima do double
    # 0,143 (0,14300000000000002), então o "exato" do AC usa tolerância apertada.
    assert taxa_equivalente.cdi_para_taxa_anual(1.10, 0.13) == pytest.approx(0.143, abs=1e-15)

def test_taxa_anual_para_cdi_inverso() -> None:
    """Inverso do AC: 14,3% a.a. com CDI 13% -> 110% do CDI (conta à mão: 0,143 / 0,13 = 1,10)."""
    assert taxa_equivalente.taxa_anual_para_cdi(0.143, 0.13) == pytest.approx(1.10, rel=1e-12)

@pytest.mark.parametrize(
    ("percentual", "cdi"),
    [
        (1.10, 0.13),
        (0.90, 0.13),
        (1.35, 0.145),
    ],
)
def test_cdi_taxa_anual_roundtrip(percentual: float, cdi: float) -> None:
    """Ida e volta cdi <-> taxa anual recupera o percentual (rel 1e-12)."""
    taxa = taxa_equivalente.cdi_para_taxa_anual(percentual, cdi)
    assert taxa_equivalente.taxa_anual_para_cdi(taxa, cdi) == pytest.approx(percentual, rel=1e-12)


# ----------------------------------------------------------------------
# isento <-> tributado (gross-up) por faixa de IR
# ----------------------------------------------------------------------
@pytest.mark.parametrize("prazo", [100, 250, 500, 900])
def test_gross_up_roundtrip_por_faixa(prazo: int) -> None:
    """Isento -> tributado -> isento recupera a taxa (rel 1e-12).

    Prazos cobrem as 4 faixas de IR: 100 d (22,5%), 250 d (20%),
    500 d (17,5%) e 900 d (15%).
    """
    taxa_isento = 0.10
    bruto_eq = taxa_equivalente.isento_equivalente_a_tributado(taxa_isento, prazo)
    assert bruto_eq > taxa_isento
    volta = taxa_equivalente.tributado_equivalente_a_isento(bruto_eq, prazo)
    assert volta == pytest.approx(taxa_isento, rel=1e-12)

def test_gross_up_caso_a_mao_faixa_15() -> None:
    """Caso à mão: LCI 10% a.a. com prazo > 720 d (IR 15%) -> CDB bruto = 10 / 0,85 = 11,7647% a.a."""
    bruto_eq = taxa_equivalente.isento_equivalente_a_tributado(0.10, 900)
    # 10 / 0,85 = 11,764705882352941...% a.a.
    assert bruto_eq == pytest.approx(0.11764705882352941, rel=1e-12)


# ----------------------------------------------------------------------
# Fisher exata ida e volta
# ----------------------------------------------------------------------
def test_fisher_caso_a_mao() -> None:
    """Caso à mão: pré 12% com IPCA 4% -> real = 1,12 / 1,04 - 1 = 7,6923% a.a."""
    real = taxa_equivalente.pre_para_ipca_mais(0.12, 0.04)
    # 1,12 / 1,04 = 1,0769230769... -> 0,07692307692307693
    assert real == pytest.approx(0.07692307692307693, rel=1e-12)

@pytest.mark.parametrize(
    ("prefixado", "ipca"),
    [
        (0.12, 0.04),
        (0.15, 0.05),
        (0.095, 0.065),
    ],
)
def test_fisher_ida_e_volta_pre_real_pre(prefixado: float, ipca: float) -> None:
    """Pre -> real -> pre recupera a taxa original (rel 1e-12)."""
    real = taxa_equivalente.pre_para_ipca_mais(prefixado, ipca)
    assert taxa_equivalente.ipca_mais_para_pre(real, ipca) == pytest.approx(prefixado, rel=1e-12)

@pytest.mark.parametrize(
    ("real", "ipca"),
    [
        (0.07692307692307693, 0.04),  # 7,6923% = 1,12 / 1,04 - 1 (caso à mão acima)
        (0.10, 0.05),
        (0.05, 0.03),
    ],
)
def test_fisher_ida_e_volta_real_pre_real(real: float, ipca: float) -> None:
    """Real -> pre -> real recupera a taxa original (rel 1e-12)."""
    pre = taxa_equivalente.ipca_mais_para_pre(real, ipca)
    assert taxa_equivalente.pre_para_ipca_mais(pre, ipca) == pytest.approx(real, rel=1e-12)


# ----------------------------------------------------------------------
# comparar() ordena por líquido desc e equivalente_cdb consistente
# ----------------------------------------------------------------------
def test_comparar_ordenacao_e_equivalente_cdb() -> None:
    """Sai ordenado por taxa_liquida_anual decrescente; equivalente_cdb coerente.

    Contas à mão (líquido linear):
        CDB 100% CDI: 0,13 x (1 - 0,15) = 0,1105    (900 d -> IR 15%)
        CDB 120% CDI: 0,156 x (1 - 0,225) = 0,1209  (100 d -> IR 22,5%)
        LCI 90% CDI:  isenta -> 0,117
        LCA 95% CDI:  isenta -> 0,1235
    Ordem esperada: LCA (0,1235) > CDB 120% (0,1209) > LCI (0,117) > CDB 100% (0,1105).
    """
    produtos = [
        taxa_equivalente.ProdutoRF("CDB 100% CDI", 0.13, 900, isento=False),
        taxa_equivalente.ProdutoRF("LCI 90% CDI", 0.117, 900, isento=True),
        taxa_equivalente.ProdutoRF("CDB 120% CDI", 0.156, 100, isento=False),
        taxa_equivalente.ProdutoRF("LCA 95% CDI", 0.1235, 500, isento=True),
    ]
    resultados = taxa_equivalente.comparar(produtos)

    nomes = [r.produto.nome for r in resultados]
    assert nomes == ["LCA 95% CDI", "CDB 120% CDI", "LCI 90% CDI", "CDB 100% CDI"]

    taxas = [r.taxa_liquida_anual for r in resultados]
    assert taxas == sorted(taxas, reverse=True)

    liquidos = {r.produto.nome: r.taxa_liquida_anual for r in resultados}
    assert liquidos["CDB 100% CDI"] == pytest.approx(0.1105, rel=1e-12)
    assert liquidos["CDB 120% CDI"] == pytest.approx(0.1209, rel=1e-12)
    assert liquidos["LCI 90% CDI"] == pytest.approx(0.117, rel=1e-12)
    assert liquidos["LCA 95% CDI"] == pytest.approx(0.1235, rel=1e-12)

    for r in resultados:
        if r.produto.isento:
            assert r.equivalente_cdb == pytest.approx(
                taxa_equivalente.isento_equivalente_a_tributado(
                    r.taxa_liquida_anual, r.produto.prazo_dias
                ),
                rel=1e-12,
            )
            # reversibilidade: o CDB equivalente volta ao líquido do isento
            assert (
                taxa_equivalente.tributado_equivalente_a_isento(
                    r.equivalente_cdb, r.produto.prazo_dias
                )
                == pytest.approx(r.taxa_liquida_anual, rel=1e-12)
            )
        else:
            # tributado: equivalente_cdb é a própria taxa bruta
            assert r.equivalente_cdb == r.produto.taxa_anual


# ----------------------------------------------------------------------
# Convenção linear documentada (docstring de taxa_liquida_anual)
# ----------------------------------------------------------------------
def test_taxa_liquida_anual_linear_isento_e_tributado() -> None:
    """CDB 12% com 900 d (IR 15%) -> 12% x (1 - 0,15) = 10,2%; isento permanece 12%."""
    cdb = taxa_equivalente.ProdutoRF("CDB 12%", 0.12, 900)
    lci = taxa_equivalente.ProdutoRF("LCI 12%", 0.12, 900, isento=True)
    assert taxa_equivalente.taxa_liquida_anual(cdb) == pytest.approx(0.102, rel=1e-12)
    assert taxa_equivalente.taxa_liquida_anual(lci) == pytest.approx(0.12, rel=1e-12)

def test_docstring_taxa_liquida_anual_cita_convencao_linear_e_aproximacao() -> None:
    """Docstring cita a convenção linear, a aproximação para prazo != 1 ano
    e onde ela está documentada (docs/formulas.md)."""
    doc = taxa_equivalente.taxa_liquida_anual.__doc__ or ""
    assert "linear" in doc.lower()
    assert "aproximação" in doc.lower()
    assert "formulas.md" in doc
