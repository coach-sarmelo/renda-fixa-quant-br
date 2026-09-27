"""Bateria de contrato de providers.

A MESMA bateria roda para o ``TesouroDiretoProvider`` (HTTP mockado com payload
derivado do ``tesouro_sample.csv``, sem rede e sem cache do usuário) e para o
``MockProvider`` — o mock não tem barra mais baixa.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal

import pandas as pd
import pytest
from mock_provider import MockProvider

DATA_REF = date(2026, 1, 2)

COLUNAS_ESPERADAS = [
    "nome",
    "tipo",
    "vencimento",
    "taxa_compra",
    "taxa_venda",
    "pu_compra",
    "pu_venda",
    "data_referencia",
    "isento_ir",
    "emissor",
    "categoria",
]
TIPOS_VALIDOS = {"Prefixado", "IPCA+", "Selic", "CDI", "Outro"}
CAMPOS_DECIMAL_OU_NONE = ["taxa_compra", "taxa_venda", "pu_compra", "pu_venda"]


def validar_df_titulos(df: pd.DataFrame) -> None:
    """Invariáveis de contrato da saída de ``titulos_disponiveis``.

    Levanta ``AssertionError`` na primeira violação — toda a bateria passa por
    aqui, então qualquer provider fora do contrato falha.
    """
    assert isinstance(df, pd.DataFrame), f"saída é {type(df).__name__}, não DataFrame"
    assert list(df.columns) == COLUNAS_ESPERADAS, f"colunas: {list(df.columns)}"
    assert len(df) >= 1, "nenhum título retornado"
    for _, t in df.iterrows():
        assert isinstance(t["nome"], str) and t["nome"], f"nome vazio: {t['nome']!r}"
        assert t["tipo"] in TIPOS_VALIDOS, f"tipo inválido: {t['tipo']!r}"
        assert isinstance(t["vencimento"], date), f"vencimento: {t['vencimento']!r}"
        assert isinstance(t["data_referencia"], date), f"data_referencia: {t['data_referencia']!r}"
        assert isinstance(t["isento_ir"], bool), f"isento_ir: {t['isento_ir']!r}"
        assert isinstance(t["emissor"], str) and t["emissor"], f"emissor vazio: {t['emissor']!r}"
        assert t["categoria"] is None or isinstance(t["categoria"], str), (
            f"categoria: {t['categoria']!r}"
        )
        for campo in CAMPOS_DECIMAL_OU_NONE:
            valor = t[campo]
            assert valor is None or isinstance(valor, Decimal), (
                f"{campo}={valor!r} — nem Decimal nem None"
            )


@pytest.fixture(params=["tesouro-provider-com-fixture", "mock-provider"])
def df_titulos(request) -> pd.DataFrame:
    """DataFrame de títulos do provider sob teste — mesmo contrato para ambos."""
    if request.param == "tesouro-provider-com-fixture":
        provider = request.getfixturevalue("provider_tesouro_teste")
        request.getfixturevalue("fetch_mockado")
        request.getfixturevalue("cache_isolado")
        return provider.titulos_disponiveis(data=DATA_REF)
    return MockProvider().titulos_disponiveis(data=DATA_REF)


def test_schema_valido(df_titulos: pd.DataFrame) -> None:
    """Colunas, tipos e nulabilidade no contrato (helper central da bateria)."""
    validar_df_titulos(df_titulos)


def test_pelo_menos_5_titulos(df_titulos: pd.DataFrame) -> None:
    """A fonte de amostra expõe 5 títulos."""
    assert len(df_titulos) >= 5


def test_ordenacao_por_tipo_e_vencimento(df_titulos: pd.DataFrame) -> None:
    """Saída ordenada por (tipo, vencimento) crescente — contrato da CLI."""
    reordenado = df_titulos.sort_values(["tipo", "vencimento"]).reset_index(drop=True)
    assert df_titulos.equals(reordenado)


def test_bateria_nao_e_vacua_dict_mal_formado() -> None:
    """Prova de não-vacuidade: schema completo mas taxa como float (não Decimal)
    é rejeitado pela própria bateria — ela falharia para um provider assim."""
    df_ruim = pd.DataFrame(
        [
            {
                "nome": "Título Malformado",
                "tipo": "Selic",
                "vencimento": date(2029, 1, 1),
                "taxa_compra": 0.115,  # float, não Decimal
                "taxa_venda": None,
                "pu_compra": 14520.35,  # float, não Decimal
                "pu_venda": None,
                "data_referencia": DATA_REF,
                "isento_ir": False,
                "emissor": "Tesouro Nacional",
                "categoria": None,
            }
        ]
    )
    with pytest.raises(AssertionError, match="nem Decimal nem None"):
        validar_df_titulos(df_ruim)
