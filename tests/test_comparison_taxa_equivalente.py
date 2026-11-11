"""Testes de taxa equivalente."""

from __future__ import annotations

from datetime import date

import pandas as pd
import pytest

from rfquant.comparison import taxa_equivalente
from rfquant.data.sgs_bcb import SGSProvider


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
# CDI do provider SGS/BCB (série 12: % ao dia -> anual base 252)
# ----------------------------------------------------------------------
class _ProviderSGSMockado(SGSProvider):
    """Provider SGS/BCB mockado: série flat fixa, sem rede nem cache.

    Espelha o contrato do real: colunas `data`/`valor`, com `valor` na
    unidade oficial do SGS (% ao dia).
    """

    def __init__(self, valor_dia: float, n_du: int) -> None:
        super().__init__()
        self._valor_dia = valor_dia
        self._n_du = n_du

    def serie_diaria(self, inicio: date, fim: date) -> pd.DataFrame:
        return pd.DataFrame(
            {
                "data": [date(2026, 9, 1 + i) for i in range(self._n_du)],
                "valor": [self._valor_dia] * self._n_du,
            }
        )


def test_cdi_anual_do_provider_caso_a_mao() -> None:
    """Caso à mão — série flat de 5 DU a 0,05 %/dia (ordem do valor real do SGS).

    acumulado = (1,0005)^5 - 1 = 0,0025025012503
    anual     = (1 + acumulado)^(252/5) - 1 = (1,0005)^252 - 1 = 0,13424645 a.a.
    """
    provider = _ProviderSGSMockado(valor_dia=0.05, n_du=5)
    anual = taxa_equivalente.cdi_anual_do_provider(provider, date(2026, 9, 1), date(2026, 9, 5))
    assert anual == pytest.approx(0.13424645086257825, rel=1e-12)


def test_cdi_do_provider_compoe_para_taxa_anual_contrato() -> None:
    """110% do CDI com CDI injetado do provider mockado -> 14,3% a.a.

    Conta à mão: o mock entrega série flat a r = 1,13^(1/252) - 1 =
    0,04851082330077361 %/dia, que a anualização base 252 devolve a 13% a.a.
    (0,13); então 1,10 × 0,13 = 0,143 (em IEEE-754 o pow de anualização deixa
    ~2e-14 abaixo do 0,143 exato — tolerância apertada, contrato preservado).
    """
    provider = _ProviderSGSMockado(valor_dia=0.04851082330077361, n_du=5)
    cdi = taxa_equivalente.cdi_anual_do_provider(provider, date(2026, 9, 1), date(2026, 9, 5))
    assert cdi == pytest.approx(0.13, abs=1e-12)
    taxa = taxa_equivalente.cdi_para_taxa_anual(1.10, cdi)
    # 1,10 × 0,13 = 0,143 -> 14,3% a.a.
    assert taxa == pytest.approx(0.143, abs=1e-12)


def test_cdi_anual_do_provider_serie_vazia_erro() -> None:
    """Série vazia (período sem dados) não anualiza: ValueError pt-BR."""
    provider = _ProviderSGSMockado(valor_dia=0.05, n_du=0)
    with pytest.raises(ValueError, match="vazia"):
        taxa_equivalente.cdi_anual_do_provider(provider, date(2026, 9, 1), date(2026, 9, 5))


def test_docstring_cdi_para_taxa_anual_declara_proxy_di_sem_spread() -> None:
    """Docstring declara o proxy %DI: CDI à vista como proxy do DI, sem
    spread de curva (limitação no padrão das convenções de estilo)."""
    doc = taxa_equivalente.cdi_para_taxa_anual.__doc__ or ""
    assert "proxy" in doc.lower()
    assert "spread" in doc.lower()
    assert "curva" in doc.lower()


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
            assert taxa_equivalente.tributado_equivalente_a_isento(
                r.equivalente_cdb, r.produto.prazo_dias
            ) == pytest.approx(r.taxa_liquida_anual, rel=1e-12)
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
    e onde ela está documentada (docs/formulas.md) — e não diz mais que a
    variante composta "fica para uma versão futura" (ela existe agora)."""
    doc = taxa_equivalente.taxa_liquida_anual.__doc__ or ""
    assert "linear" in doc.lower()
    assert "aproximação" in doc.lower()
    assert "formulas.md" in doc
    assert "versão futura" not in doc.lower()


# ----------------------------------------------------------------------
# Líquido composto (variante exata) — t = prazo_dias/365
# ----------------------------------------------------------------------
def test_composto_igual_linear_em_t_1() -> None:
    """Em t = 1 ano (365 d) a composta coincide com a linear (tol 1e-12).

    365 d cai na faixa de IR de 17,5% (>360): linear = 12% x 0,825 = 9,9%.
    """
    p = taxa_equivalente.ProdutoRF("CDB 12% a 365d", 0.12, 365)
    assert taxa_equivalente.taxa_liquida_anual_composta(p) == pytest.approx(
        taxa_equivalente.taxa_liquida_anual(p), abs=1e-12
    )


def test_composto_caso_a_mao_2_anos() -> None:
    """Caso à mão — 2 anos (730 d), 12% bruta, IR 15% (>720 d).

    Bruto total: 1,12^2 = 1,2544 -> ganho de 25,44% -> líquido total
    1 + 0,85 x 0,2544 = 1,21624 -> anualizada: 1,21624^(1/2) - 1
    = 10,2833% a.a. A linear dá 12% x 0,85 = 10,2% a.a.: a composta é
    ~0,08 p.p. maior porque o IR incide uma única vez no resgate (o IR
    "não pago" nos anos intermediários rende juros até a saída).
    """
    p = taxa_equivalente.ProdutoRF("CDB 12% a 730d", 0.12, 730)
    comp = taxa_equivalente.taxa_liquida_anual_composta(p)
    assert comp == pytest.approx(0.1028327162, rel=1e-9)  # sqrt(1,21624) - 1
    lin = taxa_equivalente.taxa_liquida_anual(p)
    assert comp > lin
    assert comp - lin == pytest.approx(0.0008327162, rel=1e-3)  # ~0,08 p.p.


def test_composto_horizonte_curto_pune() -> None:
    """Espelho do caso de 2 anos: em t < 1 a composta fica ABAIXO da linear
    (o IR incide antes de os juros completarem o ano). 182 d (IR 20%),
    12% bruta, t = 182/365 ≈ 0,4986: 1,12^(182/365) = 1,0581362 ->
    líquido total 1 + 0,8 x 0,0581362 = 1,0465090 -> anualizada
    1,0465090^(365/182) - 1 ≈ 9,5455% a.a. vs linear 12% x 0,8 = 9,6%."""
    p = taxa_equivalente.ProdutoRF("CDB 12% a 182d", 0.12, 182)
    comp = taxa_equivalente.taxa_liquida_anual_composta(p)
    assert comp == pytest.approx(0.09545466, rel=1e-6)
    assert comp < taxa_equivalente.taxa_liquida_anual(p)


def test_composto_isento_devolve_a_propria_bruta() -> None:
    """Sem IR a composta degenera: ((1+b)^t)^(1/t) - 1 = b para qualquer t."""
    p = taxa_equivalente.ProdutoRF("LCI 12% a 730d", 0.12, 730, isento=True)
    assert taxa_equivalente.taxa_liquida_anual_composta(p) == pytest.approx(0.12, rel=1e-15)


def test_composto_prazo_invalido_erro() -> None:
    """prazo_dias <= 0 não define horizonte: ValueError explícito."""
    p = taxa_equivalente.ProdutoRF("CDB sem taxa definida", 0.12, 0)
    with pytest.raises(ValueError, match="Prazo inválido"):
        taxa_equivalente.taxa_liquida_anual_composta(p)


def test_composto_taxa_menor_que_menos_um_erro() -> None:
    """Taxa bruta < -100% não tem rendimento composto real: base negativa
    elevada a t fracionário viraria complex silenciosamente em Python 3
    (ex.: (1-1,2)^2,47 = 0,002+0,019j) -> ValueError no domínio float."""
    p = taxa_equivalente.ProdutoRF("CDB -120%", -1.2, 730)
    with pytest.raises(ValueError, match="-100%"):
        taxa_equivalente.taxa_liquida_anual_composta(p)


def test_composto_taxa_menos_um_perda_total_e_float() -> None:
    """-100% exato (perda total) é computável: 0,0^t = 0 -> líquido total
    0,15 -> anualizada negativa em float, sem complex."""
    p = taxa_equivalente.ProdutoRF("CDB -100%", -1.0, 730)
    comp = taxa_equivalente.taxa_liquida_anual_composta(p)
    assert isinstance(comp, float)
    assert comp < 0


# ----------------------------------------------------------------------
# Seam 2: resumir_fundo (análise unificada do Informe Diário + % CDI)
# ----------------------------------------------------------------------
def test_resumir_fundo_calcula_acumulada_anualizada_e_pct_cdi_em_uma_passagem() -> None:
    """Seam 2: `resumir_fundo` calcula rentabilidade acumulada, anualizada (base 252
    com DU reais) e % do CDI sobre a mesma janela `(inicio, fim]`."""
    df_fundo = pd.DataFrame(
        {
            "data_competencia": [date(2026, 9, 1), date(2026, 9, 8)],
            "valor_cota": [1.0, 1.002],
        }
    )
    # Entre 01/09/2026 (terça) e 08/09/2026 (terça), com feriado de 07/09 (segunda),
    # há exatamente 4 dias úteis reais: 02, 03, 04 e 08/09.
    provider = _ProviderSGSMockado(valor_dia=0.05, n_du=4)
    resumo = taxa_equivalente.resumir_fundo(df_fundo, provider)

    acumulada_esp = 0.002
    anualizada_esp = (1.0 + acumulada_esp) ** (252 / 4) - 1.0
    cdi_anual_esp = (1.0005**252) - 1.0

    assert isinstance(resumo, taxa_equivalente.ResumoFundo)
    assert resumo.data_inicio == date(2026, 9, 1)
    assert resumo.data_fim == date(2026, 9, 8)
    assert resumo.dias_uteis == 4
    assert resumo.rentabilidade_acumulada == pytest.approx(acumulada_esp, rel=1e-12)
    assert resumo.rentabilidade_anualizada == pytest.approx(anualizada_esp, rel=1e-12)
    assert resumo.percentual_cdi == pytest.approx(anualizada_esp / cdi_anual_esp, rel=1e-12)


def test_resumir_fundo_entradas_degeneradas_retornam_zeros() -> None:
    """Seam 2: DataFrames vazios, sem colunas ou com 0 DU retornam ResumoFundo zerado."""
    provider = _ProviderSGSMockado(valor_dia=0.05, n_du=4)
    vazio = taxa_equivalente.resumir_fundo(pd.DataFrame(), provider)
    assert vazio.rentabilidade_acumulada == 0.0
    assert vazio.rentabilidade_anualizada == 0.0
    assert vazio.percentual_cdi == 0.0
    assert vazio.dias_uteis == 0

    df_mesmo_dia = pd.DataFrame(
        {
            "data_competencia": [date(2026, 9, 1), date(2026, 9, 1)],
            "valor_cota": [1.0, 1.001],
        }
    )
    mesmo_dia = taxa_equivalente.resumir_fundo(df_mesmo_dia, provider)
    assert mesmo_dia.dias_uteis == 0
    assert mesmo_dia.rentabilidade_anualizada == 0.0
    assert mesmo_dia.percentual_cdi == 0.0


def test_guardas_validacao_taxa_equivalente() -> None:
    """Guardas de validação de entradas inválidas em taxa_equivalente."""
    with pytest.raises(ValueError, match="positivo"):
        taxa_equivalente.cdi_para_taxa_anual(0.0, 0.13)
    with pytest.raises(ValueError, match="positivo"):
        taxa_equivalente.cdi_para_taxa_anual(1.10, 0.0)
    with pytest.raises(ValueError, match="positivo"):
        taxa_equivalente.taxa_anual_para_cdi(0.13, 0.0)
    with pytest.raises(ValueError, match="-100%"):
        taxa_equivalente.pre_para_ipca_mais(0.12, -1.0)
    with pytest.raises(ValueError, match="-100%"):
        taxa_equivalente.ipca_mais_para_pre(0.06, -1.0)


# ----------------------------------------------------------------------
# Seam 4: ProdutoRF(..., categoria=...) e comparar(..., convencao=...)
# ----------------------------------------------------------------------
def test_produto_rf_deriva_isento_por_categoria_e_valida_lista_fechada() -> None:
    """Seam 4: `ProdutoRF` deriva `isento` automaticamente de `categoria`
    (`LCI`, `LCA`, `debênture-incentivada`) e rejeita categorias desconhecidas."""
    cdb = taxa_equivalente.ProdutoRF("CDB", 0.12, 720, categoria="CDB")
    lci = taxa_equivalente.ProdutoRF("LCI", 0.10, 720, categoria="LCI")
    lca = taxa_equivalente.ProdutoRF("LCA", 0.10, 720, categoria="LCA")
    deb_comum = taxa_equivalente.ProdutoRF("Deb", 0.13, 720, categoria="debênture-comum")
    deb_inc = taxa_equivalente.ProdutoRF("Deb Inc", 0.11, 720, categoria="debênture-incentivada")

    assert cdb.isento is False
    assert lci.isento is True
    assert lca.isento is True
    assert deb_comum.isento is False
    assert deb_inc.isento is True

    with pytest.raises(ValueError, match="Categoria desconhecida"):
        taxa_equivalente.ProdutoRF("Invalido", 0.12, 720, categoria="CRA-inexistente")


def test_comparar_suporta_convencao_linear_e_composta() -> None:
    """Seam 4 (ADR-0003): `comparar` aceita `convencao='linear'` (default) e
    `convencao='composta'`, ordenando pela taxa líquida da convenção escolhida."""
    cdb = taxa_equivalente.ProdutoRF("CDB 12% 2a", 0.12, 730, categoria="CDB")
    lci = taxa_equivalente.ProdutoRF("LCI 10.24% 2a", 0.1024, 730, categoria="LCI")

    # Em 730d (IR 15%), CDB 12% tem:
    # - líquido linear = 12% * 0.85 = 10.20% (< LCI 10.24%)
    # - líquido composto = sqrt(1 + 0.85*(1.12^2 - 1)) - 1 ≈ 10.2833% (> LCI 10.24%)
    res_lin = taxa_equivalente.comparar([cdb, lci], convencao="linear")
    res_comp = taxa_equivalente.comparar([cdb, lci], convencao="composta")

    assert res_lin[0].produto.nome == "LCI 10.24% 2a"
    assert res_comp[0].produto.nome == "CDB 12% 2a"
    assert res_comp[0].taxa_liquida_anual == pytest.approx(
        taxa_equivalente.taxa_liquida_anual_composta(cdb), rel=1e-12
    )
    with pytest.raises(ValueError, match="Convenção desconhecida"):
        taxa_equivalente.comparar([cdb], convencao="invalida")  # type: ignore[arg-type]
