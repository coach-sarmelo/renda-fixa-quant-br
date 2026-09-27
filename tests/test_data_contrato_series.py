"""Bateria de contrato de SÉRIES.

A MESMA bateria (schema, ordenação, tipos — a mesma régua da bateria de
títulos em ``tests/test_data_contrato.py``) roda parametrizada para o
``SGSProvider`` (HTTP mockado com a fixture REAL
``sgs_serie12_sample.json``, sem rede e sem cache do usuário) e para
``MockProvider.historico_taxas`` (série sintética
``serie_historica_sample.csv``) — o mock não tem barra mais baixa: se um
payload mal-formado passa na bateria, ela está frouxa e deve ser endurecida
(teste de não-vacuidade no fim do arquivo).

Toda bateria passa pelo helper central ``validar_df_serie`` — inclusive o
teste ``@pytest.mark.network`` do SGS (tests/test_data_sgs.py; deselecionado
na suíte padrão pelos addopts do pyproject; roda só no job semanal).
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path
from typing import Any

import pandas as pd
import pytest
import requests
from conftest import RespostaFake
from mock_provider import MockProvider

from rfquant.data.sgs_bcb import SGSProvider

CAMINHO_FIXTURE_SGS = Path(__file__).parent / "fixtures" / "sgs_serie12_sample.json"

# Períodos e amostras fixos — determinismo (nunca ``date.today()`` na bateria).
INICIO_SGS = date(2026, 9, 1)
FIM_SGS = date(2026, 9, 30)
TITULO_MOCK = "Tesouro Selic 2029"
INICIO_MOCK = date(2026, 1, 1)
FIM_MOCK = date(2026, 1, 31)

# Mesma régua da bateria de títulos: a amostra expõe ≥ 5 pontos.
MINIMO_LINHAS = 5

COLUNAS_MOCK = ["data", "taxa_compra", "taxa_venda", "pu_compra", "pu_venda"]
COLUNAS_SGS = ["data", "valor"]


@dataclass(frozen=True)
class ContratoSerie:
    """Caso da bateria: schema declarado do contrato + a saída do provider."""

    colunas: list[str]
    df: pd.DataFrame


def validar_df_serie(
    df: pd.DataFrame, colunas: list[str], minimo_linhas: int = MINIMO_LINHAS
) -> None:
    """Invariáveis de contrato de uma série temporal (helper central da bateria).

    Levanta ``AssertionError`` na primeira violação — toda a bateria passa por
    aqui, então qualquer provider fora do contrato falha: colunas exatas;
    ``data`` como ``date`` (não ``datetime``/``Timestamp``, que são subclasses);
    demais colunas com célula ``float`` (não str — o SGS cru manda texto);
    ordenado por ``data`` crescente, sem duplicatas; não vazio.
    """
    assert isinstance(df, pd.DataFrame), f"saída é {type(df).__name__}, não DataFrame"
    assert list(df.columns) == colunas, f"colunas: {list(df.columns)}"
    assert len(df) >= minimo_linhas, f"série com {len(df)} linhas (< {minimo_linhas})"
    datas = list(df["data"])
    for d in datas:
        assert isinstance(d, date) and not isinstance(d, datetime), f"data: {d!r}"
    assert datas == sorted(datas), f"série fora de ordem: {datas}"
    assert len(set(datas)) == len(datas), "datas duplicadas na série"
    for col in colunas[1:]:
        for valor in df[col]:
            assert isinstance(valor, float), f"{col}={valor!r} — não é float"


def _payload_sgs_fixture() -> Any:
    """JSON da fixture REAL, sem as linhas de cabeçalho ``#``."""
    linhas = CAMINHO_FIXTURE_SGS.read_text(encoding="utf-8").splitlines()
    corpo = "\n".join(linha for linha in linhas if not linha.startswith("#"))
    return json.loads(corpo)


class _FetchSGS:
    """``requests.get`` falso: devolve o payload da fixture (sem rede)."""

    def __init__(self, payload: Any) -> None:
        self._payload = payload

    def __call__(self, url, params=None, timeout=None, headers=None, **kwargs):
        return RespostaFake(self._payload)


@pytest.fixture(params=["sgs-provider-fixture-real", "mock-provider-serie-sintetica"])
def serie_contrato(request, monkeypatch) -> ContratoSerie:
    """Série do provider sob teste — o MESMO contrato cobrado dos dois."""
    if request.param == "sgs-provider-fixture-real":
        request.getfixturevalue("cache_isolado")  # provider exerce rfquant.data.cache
        monkeypatch.setattr(requests, "get", _FetchSGS(_payload_sgs_fixture()))
        df = SGSProvider().serie_diaria(INICIO_SGS, FIM_SGS)
        return ContratoSerie(colunas=COLUNAS_SGS, df=df)
    df = MockProvider().historico_taxas(TITULO_MOCK, INICIO_MOCK, FIM_MOCK)
    return ContratoSerie(colunas=COLUNAS_MOCK, df=df)


# ----------------------------------------------------------------------
# A bateria — MESMAS verificações para os dois providers
# ----------------------------------------------------------------------
def test_schema_valido(serie_contrato: ContratoSerie) -> None:
    """Colunas exatas, data como date, valores float, ordenado, não vazio."""
    validar_df_serie(serie_contrato.df, serie_contrato.colunas)


def test_ordenacao_por_data(serie_contrato: ContratoSerie) -> None:
    """Saída ordenada por data crescente — reordenar não muda nada."""
    reordenado = serie_contrato.df.sort_values("data").reset_index(drop=True)
    assert serie_contrato.df.equals(reordenado)


def test_nao_vazia(serie_contrato: ContratoSerie) -> None:
    """Mesma régua da bateria de títulos: ao menos 5 pontos."""
    assert len(serie_contrato.df) >= MINIMO_LINHAS


# ----------------------------------------------------------------------
# Não-vacuidade: payload mal-formado DERRUBA a bateria
# (o SGS cru manda ``valor`` como texto — um provider que esquecesse o
# cast passaria num schema-check frouxo; aqui a bateria pega)
# ----------------------------------------------------------------------
def _df_serie_ok() -> pd.DataFrame:
    """Série no contrato (espelho da saída do mock — 5 pontos, na régua da
    bateria) para mutar nos casos ruins; cada mutação isola UMA violação."""
    return pd.DataFrame(
        {
            "data": [
                date(2026, 1, 1),
                date(2026, 1, 2),
                date(2026, 1, 5),
                date(2026, 1, 6),
                date(2026, 1, 7),
            ],
            "taxa_compra": [0.1150, 0.1150, 0.1150, 0.1150, 0.1150],
            "taxa_venda": [0.1165, 0.1165, 0.1165, 0.1165, 0.1165],
            "pu_compra": [14520.35, 14526.98, 14533.61, 14540.25, 14546.88],
            "pu_venda": [14520.10, 14526.73, 14533.36, 14540.00, 14546.63],
        }
    )


@pytest.mark.parametrize(
    ("mutacao", "trecho_erro"),
    [
        pytest.param(
            lambda df: df.assign(taxa_compra=df["taxa_compra"].astype(str)),
            "não é float",
            id="valor-como-str",
        ),
        pytest.param(
            lambda df: df.assign(
                data=["2026-01-01", "2026-01-02", "2026-01-05", "2026-01-06", "2026-01-07"]
            ),
            "data:",
            id="data-como-str",
        ),
        pytest.param(
            lambda df: df.sort_values("pu_compra", ascending=False).reset_index(drop=True),
            "fora de ordem",
            id="fora-de-ordem",
        ),
        pytest.param(
            lambda df: df.drop(columns=["taxa_venda"]),
            "colunas:",
            id="colunas-faltando",
        ),
        pytest.param(lambda df: df.iloc[0:0], "série com 0 linhas", id="vazio"),
    ],
)
def test_bateria_nao_e_vacua_payload_mal_formado(mutacao, trecho_erro) -> None:
    """Prova "mock sem barra mais baixa": schema plausível com UM tipo/ordem/
    coluna violada é REJEITADO pelo próprio helper — a bateria não é vácuo."""
    with pytest.raises(AssertionError, match=trecho_erro):
        validar_df_serie(mutacao(_df_serie_ok()), COLUNAS_MOCK)


# ----------------------------------------------------------------------
# Contrato de filtragem do historico_taxas do mock
# ----------------------------------------------------------------------
def test_mock_filtra_por_titulo_e_janela() -> None:
    """Filtro por título e janela [inicio, fim] inclusiva — o CSV tem 2 títulos
    justamente para o filtro não ser vacuidade."""
    df = MockProvider().historico_taxas(TITULO_MOCK, date(2026, 1, 6), date(2026, 1, 9))
    assert list(df["data"]) == [
        date(2026, 1, 6),
        date(2026, 1, 7),
        date(2026, 1, 8),
        date(2026, 1, 9),
    ]
    df_pref = MockProvider().historico_taxas("Tesouro Prefixado 2029", INICIO_MOCK, FIM_MOCK)
    assert len(df_pref) == 3
    assert set(df_pref["data"]) == {date(2026, 1, 1), date(2026, 1, 2), date(2026, 1, 5)}


def test_mock_janela_sem_dados_vazio_com_colunas() -> None:
    """Título/janela sem dados ⇒ DataFrame vazio COM as colunas do contrato
    (padrão do TesouroOficialProvider) — nunca KeyError cru."""
    df = MockProvider().historico_taxas(TITULO_MOCK, date(2099, 1, 1), date(2099, 1, 31))
    assert isinstance(df, pd.DataFrame)
    assert df.empty
    assert list(df.columns) == COLUNAS_MOCK


# O teste de rede do SGS (job de CI semanal) mora em tests/test_data_sgs.py —
# arquivo do módulo, ao lado dos testes offline do provider; ele passa nesta
# MESMA bateria via validar_df_serie.
