"""Testes do TesouroOficialProvider com CSV sintético — sem rede.

O parsing do arquivo REAL capturado do endpoint é testado adiante
(com fixture própria); aqui valida-se o comportamento do
provider: filtrar a Data Base mais recente, converter % a.a. → fração,
ordenar e expor historico por período.
"""

from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal
from pathlib import Path

import pandas as pd
import pytest
import requests
from conftest import RespostaFake

from rfquant.data.tesouro_oficial import TesouroOficialProvider

CSV_SINTETICO = (
    "Tipo Titulo;Data Vencimento;Data Base;Taxa Compra Manha;Taxa Venda Manha;"
    "PU Compra Manha;PU Venda Manha;PU Base Manha\n"
    "Tesouro Selic;01/03/2029;18/09/2026;0,07;0,08;14520,35;14510,10;14510,10\n"
    "Tesouro Prefixado;01/01/2029;18/09/2026;14,10;14,22;571,16;568,32;568,32\n"
    "Tesouro IPCA+;15/05/2035;17/09/2026;6,20;6,35;3420,55;3419,20;3419,20\n"
)


@pytest.fixture
def provider_oficial(monkeypatch, cache_isolado) -> TesouroOficialProvider:
    monkeypatch.setattr(
        requests, "get", lambda *args, **kwargs: RespostaFake({}, texto=CSV_SINTETICO)
    )
    return TesouroOficialProvider()


def test_titulos_disponiveis_so_data_base_mais_recente(provider_oficial: TesouroOficialProvider) -> None:
    """Sem `data`, retorna apenas a última Data Base do arquivo (2 dos 3 títulos)."""
    df = provider_oficial.titulos_disponiveis()
    assert len(df) == 2
    assert list(df["tipo"]) == ["Prefixado", "Selic"]  # ordenação por tipo
    assert all(df["data_referencia"] == date(2026, 9, 18))


def test_titulos_disponiveis_converte_taxa_percentual_para_fracao(
    provider_oficial: TesouroOficialProvider,
) -> None:
    """O CSV traz % a.a. com vírgula (14,10); o contrato é fração Decimal (0,141)."""
    df = provider_oficial.titulos_disponiveis()
    pref = df[df["nome"] == "Tesouro Prefixado 2029"].iloc[0]
    assert pref["taxa_compra"] == Decimal("0.141")
    assert pref["taxa_venda"] == Decimal("0.1422")
    assert pref["pu_compra"] == Decimal("571.16")
    selic = df[df["nome"] == "Tesouro Selic 2029"].iloc[0]
    assert selic["taxa_compra"] == Decimal("0.0007")


def test_titulos_disponiveis_com_data_especifica(provider_oficial: TesouroOficialProvider) -> None:
    """`data` explícita filtra a Data Base pedida (17/09 tem só o IPCA+)."""
    df = provider_oficial.titulos_disponiveis(data=date(2026, 9, 17))
    assert len(df) == 1
    assert df.iloc[0]["nome"] == "Tesouro IPCA+ 2035"
    assert df.iloc[0]["vencimento"] == date(2035, 5, 15)


def test_historico_taxas_filtra_titulo_e_periodo(provider_oficial: TesouroOficialProvider) -> None:
    """historico_taxas devolve série ordenada com colunas de taxa/PU."""
    serie = provider_oficial.historico_taxas(
        "Tesouro IPCA+ 2035",
        inicio=date(2026, 9, 1),
        fim=date(2026, 9, 30),
    )
    assert isinstance(serie, pd.DataFrame)
    assert list(serie["data"]) == [date(2026, 9, 17)]
    assert serie.iloc[0]["taxa_compra"] == pytest.approx(0.062)
    assert serie.iloc[0]["pu_compra"] == pytest.approx(3420.55)


# ----------------------------------------------------------------------
# Teste de rede (job de CI semanal; deselecionado na suíte
# padrão pelos addopts `-m 'not network'` do pyproject)
# ----------------------------------------------------------------------
@pytest.mark.network
def test_provider_oficial_endpoint_responde() -> None:
    """Endpoint público do Tesouro responde com ≥1 título real, no contrato.

    Freshness: Data Base dentro de 7 dias — cache stale não mascara queda do
    endpoint por mais de uma semana.
    """
    from test_data_contrato import validar_df_titulos

    df = TesouroOficialProvider().titulos_disponiveis()
    assert len(df) >= 1
    validar_df_titulos(df)
    assert max(df["data_referencia"]) >= date.today() - timedelta(days=7)


# ----------------------------------------------------------------------
# Parsing do arquivo REAL capturado, na suíte padrão
#
# A fixture é um excerto byte a byte do CSV do endpoint (últimas
# datas-base), com cabeçalho de auditoria em linhas `#` (path,
# data de captura, versão). O teste remove essas linhas antes de
# alimentar o parser — o código de produção nunca vê comentários.
# ----------------------------------------------------------------------
CAMINHO_FIXTURE_REAL = Path(__file__).parent / "fixtures" / "tesouro_oficial_sample.csv"

COLUNAS_CSV_OFICIAL = [
    "Tipo Titulo",
    "Data Vencimento",
    "Data Base",
    "Taxa Compra Manha",
    "Taxa Venda Manha",
    "PU Compra Manha",
    "PU Venda Manha",
    "PU Base Manha",
]


def _fixture_real() -> str:
    """Conteúdo CSV da fixture real, sem as linhas de cabeçalho `#`."""
    linhas = CAMINHO_FIXTURE_REAL.read_text(encoding="utf-8").splitlines()
    return "\n".join(linha for linha in linhas if not linha.startswith("#"))


@pytest.fixture
def provider_real(monkeypatch, cache_isolado) -> TesouroOficialProvider:
    """Provider alimentado pela fixture REAL (HTTP mockado, cache isolado)."""
    monkeypatch.setattr(
        requests, "get", lambda *args, **kwargs: RespostaFake({}, texto=_fixture_real())
    )
    return TesouroOficialProvider()


def test_fixture_real_tem_cabecalho_de_auditoria() -> None:
    """Cabeçalho de auditoria: path, data de captura e versão no próprio arquivo."""
    linhas = CAMINHO_FIXTURE_REAL.read_text(encoding="utf-8").splitlines()
    cabecalho = [linha for linha in linhas if linha.startswith("#")]
    assert any("path: https://www.tesourotransparente.gov.br" in c for c in cabecalho)
    assert any("data de captura:" in c for c in cabecalho)
    assert any("versão" in c for c in cabecalho)


def test_parsear_fixture_real_mantem_schema() -> None:
    """O parser digere o CSV verdadeiro: 8 colunas, datas como datetime."""
    df = TesouroOficialProvider._parsear(_fixture_real())
    assert list(df.columns) == COLUNAS_CSV_OFICIAL
    assert pd.api.types.is_datetime64_any_dtype(df["Data Base"])
    assert pd.api.types.is_datetime64_any_dtype(df["Data Vencimento"])
    n_dados = len([linha_cruda for linha_cruda in _fixture_real().splitlines() if linha_cruda and not linha_cruda.startswith("#")]) - 1
    assert len(df) == n_dados


def test_provider_com_fixture_real_passa_na_bateria_de_contrato(provider_real) -> None:
    """A bateria de contrato valida o provider sobre dados reais (sem rede)."""
    from test_data_contrato import validar_df_titulos

    df = provider_real.titulos_disponiveis()
    validar_df_titulos(df)
    assert len(df) >= 5  # uma data-base real tem dezenas de títulos


def test_provider_com_fixture_real_taxa_vira_fracao_decimal_exata(provider_real) -> None:
    """% a.a. com vírgula → fração Decimal exata, conferida contra a linha crua.

    O valor esperado é derivado do texto original da fixture (Decimal puro,
    sem passar pelo pandas) — pega artefatos de float que sobrevivam ao
    caminho read_csv → Decimal(str(v)).
    """
    df = provider_real.titulos_disponiveis()
    linha = df.iloc[0]
    tipo_nome = str(linha["nome"]).rsplit(" ", 1)[0]  # "Tesouro X 2035" → "Tesouro X"
    bruta = next(
        linha_cruda
        for linha_cruda in _fixture_real().splitlines()
        if linha_cruda.startswith(tipo_nome + ";")
        and linha_cruda.split(";")[1] == linha["vencimento"].strftime("%d/%m/%Y")
        and linha_cruda.split(";")[2] == linha["data_referencia"].strftime("%d/%m/%Y")
    )
    campos = bruta.split(";")
    assert linha["taxa_compra"] == Decimal(campos[3].replace(",", ".")) / Decimal(100)
    assert linha["taxa_venda"] == Decimal(campos[4].replace(",", ".")) / Decimal(100)
    assert linha["pu_compra"] == Decimal(campos[5].replace(",", "."))
    assert linha["pu_venda"] == Decimal(campos[6].replace(",", "."))
    # sanidade: taxas reais de TD ficam entre 0% e 30% a.a.
    assert Decimal(0) < linha["taxa_compra"] < Decimal("0.30")


def test_historico_com_fixture_real_devolve_serie_ordenada(provider_real) -> None:
    """historico_taxas sobre a fixture real: várias datas, crescentes."""
    df = provider_real.titulos_disponiveis()
    nome = str(df.iloc[0]["nome"])
    serie = provider_real.historico_taxas(
        nome, inicio=date(2000, 1, 1), fim=date(2100, 1, 1)
    )
    assert len(serie) >= 3  # excerto cobre várias datas-base
    datas = list(serie["data"])
    assert datas == sorted(datas)
    assert serie["taxa_compra"].between(0, 0.30).all()


# ----------------------------------------------------------------------
# Edge cases: entrada sem dados devolve DataFrame VAZIO,
# nunca exceção. Conta à mão: a máscara de `historico_taxas` é
# `(nome == titulo) & (inicio <= Data Base <= fim)`; quando ela não
# seleciona linha nenhuma, o DataFrame montado sobre a seleção herda as
# colunas do contrato com 0 registros (vazio não é None nem KeyError).
# ----------------------------------------------------------------------
COLUNAS_HISTORICO = ["data", "taxa_compra", "taxa_venda", "pu_compra", "pu_venda"]


def test_historico_taxas_titulo_inexistente_devolve_vazio_com_colunas(provider_real) -> None:
    """Título fora do arquivo (nenhum vencimento em 2099) → vazio, com colunas.

    A fixture real tem vencimentos até 2084 e a sequência "2099" não ocorre
    nenhuma vez no arquivo (grep -c = 0) — o nome não pode existir.
    """
    serie = provider_real.historico_taxas(
        "Tesouro IPCA+ 2099",
        inicio=date(2026, 9, 1),
        fim=date(2026, 9, 30),
    )
    assert isinstance(serie, pd.DataFrame)
    assert serie.empty
    assert list(serie.columns) == COLUNAS_HISTORICO


def test_historico_taxas_janela_sem_dados_devolve_vazio(provider_real) -> None:
    """Título existente, janela anterior à 1ª Data Base da fixture → vazio.

    A fixture cobre as Data Bases 11/09/2026 a 18/09/2026; a janela abaixo
    termina em 10/09 — nenhuma Data Base cai dentro dela. A checagem de
    sanidade (6 linhas na janela completa) garante que o vazio não é
    vacuamente verde por título ausente: `Tesouro IPCA+;15/05/2035`
    aparece 1× em cada uma das 6 Data Bases da fixture (grep -c = 6).
    """
    cheio = provider_real.historico_taxas(
        "Tesouro IPCA+ 2035", inicio=date(2026, 9, 11), fim=date(2026, 9, 18)
    )
    assert len(cheio) == 6
    serie = provider_real.historico_taxas(
        "Tesouro IPCA+ 2035", inicio=date(2026, 9, 1), fim=date(2026, 9, 10)
    )
    assert serie.empty
    assert list(serie.columns) == COLUNAS_HISTORICO


def test_titulos_disponiveis_data_sem_linhas_devolve_vazio(provider_real) -> None:
    """`data` sem nenhuma Data Base no arquivo → DataFrame vazio, sem exceção.

    01/09/2026 é anterior à 1ª Data Base da fixture (11/09/2026) — nenhum
    título naquele dia.
    """
    df = provider_real.titulos_disponiveis(data=date(2026, 9, 1))
    assert isinstance(df, pd.DataFrame)
    assert df.empty
