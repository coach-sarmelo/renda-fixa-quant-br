"""Testes do provider SGS/BCB série 12 (CDI diário) — sem rede.

Parsing validado contra fixture REAL excisada (cabeçalho de auditoria em
linhas ``#``); período sem dados contra o payload de erro REAL
capturado do endpoint (sonda 2026-09-23); TTL do cache por comportamento com
``cache_isolado`` + ``relogio`` (patch de time.time — nunca sleep). Exceção
única de rede: o teste ``@pytest.mark.network`` do fim do arquivo — job de CI
semanal, desselecionado na suíte padrão pelos addopts do pyproject.
"""

from __future__ import annotations

from datetime import date, timedelta
from typing import Any

import pandas as pd
import pytest
import requests
from conftest import (
    CAMINHO_FIXTURE_SGS,
    RespostaFake,
    fixture_payload,
    repetir_se_rede_instavel,
)

from rfquant.data.sgs_bcb import TTL_SGS, USER_AGENT, SGSProvider

# Payload de erro REAL do SGS para período sem dados, capturado em 2026-09-23:
# curl "https://api.bcb.gov.br/dados/serie/bcdata.sgs.12/dados?formato=json&dataInicial=01/09/2099&dataFinal=30/09/2099"
PAYLOAD_MES_SEM_DADOS = {
    "erro": {
        "statusCode": 404,
        "detail": "br.gov.bcb.pec.sgs.comum.excecoes.SGSNegocioException: Value(s) not found",
    }
}


class _FetchContadoSGS:
    """``requests.get`` instrumentado: conta chamadas, guarda a User-Agent e
    devolve payload fixo (padrão ``fetch_mockado`` do conftest, com UA)."""

    def __init__(self, payload: Any) -> None:
        self._payload = payload
        self.chamadas = 0
        self.user_agent: str | None = None

    def __call__(self, url, params=None, timeout=None, headers=None, **kwargs):
        self.chamadas += 1
        self.user_agent = (headers or {}).get("User-Agent")
        return RespostaFake(self._payload)


@pytest.fixture
def provider_sgs(cache_isolado) -> SGSProvider:
    """Provider da série 12 com cache isolado (sem rede, sem estado do usuário)."""
    return SGSProvider()


@pytest.fixture
def fetch_sgs_fixture(monkeypatch, cache_isolado) -> _FetchContadoSGS:
    """Fetch instrumentado devolvendo a fixture REAL (setembro/2026 excisado)."""
    fetch = _FetchContadoSGS(fixture_payload())
    monkeypatch.setattr(requests, "get", fetch)
    return fetch


# ----------------------------------------------------------------------
# Fixture real: cabeçalho de auditoria + parse do JSON oficial
# ----------------------------------------------------------------------
def test_fixture_real_tem_cabecalho_de_auditoria() -> None:
    """Cabeçalho da fixture: path, data de captura, critério da excisão e cadência."""
    linhas = CAMINHO_FIXTURE_SGS.read_text(encoding="utf-8").splitlines()
    cabecalho = [linha for linha in linhas if linha.startswith("#")]
    assert any("path: https://api.bcb.gov.br" in c for c in cabecalho)
    assert any("data de captura:" in c for c in cabecalho)
    assert any("excisão:" in c for c in cabecalho)
    assert any("cadência:" in c for c in cabecalho)


def test_parse_fixture_real_schema_e_ordenacao(provider_sgs, fetch_sgs_fixture) -> None:
    """JSON oficial → DataFrame com colunas data/valor, ordenado por data.

    A fixture traz os 15 dias úteis de 09/2026 (mês completo até o último
    ponto publicado, 22/09/2026) — conta registrada no cabeçalho da fixture.
    """
    df = provider_sgs.serie_diaria(date(2026, 9, 1), date(2026, 9, 30))
    assert list(df.columns) == ["data", "valor"]
    assert len(df) == 15
    datas = list(df["data"])
    assert datas == sorted(datas)
    assert datas[0] == date(2026, 9, 1)
    assert datas[-1] == date(2026, 9, 22)
    assert pd.api.types.is_float_dtype(df["valor"])


def test_parse_fixture_real_datas_date_e_valores_float(provider_sgs, fetch_sgs_fixture) -> None:
    """Datas parseadas de DD/MM/AAAA → ``date``; valores → ``float`` exatos.

    O esperado é derivado da linha crua da fixture (sem passar pelo provider):
    o primeiro registro e a virada de taxa em 17/09 (0,051660 → 0,050788 ao
    dia) batem com os valores verificados no endpoint na captura.
    """
    bruto = fixture_payload()
    df = provider_sgs.serie_diaria(date(2026, 9, 1), date(2026, 9, 30))

    primeiro = df.iloc[0]
    assert isinstance(primeiro["data"], date)
    assert primeiro["data"] == date(2026, 9, 1)
    assert primeiro["valor"] == float(bruto[0]["valor"]) == pytest.approx(0.051660)
    assert isinstance(primeiro["valor"], float)

    virada = df[df["data"] == date(2026, 9, 17)].iloc[0]
    assert virada["valor"] == pytest.approx(0.050788)  # valor verificado no endpoint
    cru_17 = next(r for r in bruto if r["data"] == "17/09/2026")
    assert virada["valor"] == float(cru_17["valor"])


# ----------------------------------------------------------------------
# Mês sem dados ⇒ erro explícito pt-BR (comportamento real do SGS)
# ----------------------------------------------------------------------
def test_mes_sem_dados_erro_explicito_ptbr(monkeypatch, cache_isolado) -> None:
    """Período sem dados: SGS responde ``{"erro": ...}`` (payload real capturado
    em 2026-09-23 com dataInicial=01/09/2099) e o provider levanta ValueError
    em pt-BR citando a série e o período — nunca DataFrame vazio silencioso.
    """
    monkeypatch.setattr(requests, "get", _FetchContadoSGS(PAYLOAD_MES_SEM_DADOS))
    provider = SGSProvider()
    with pytest.raises(ValueError) as excinfo:
        provider.serie_diaria(date(2099, 9, 1), date(2099, 9, 30))
    mensagem = str(excinfo.value)
    assert "sem dados" in mensagem
    assert "série 12" in mensagem
    assert "01/09/2099 a 30/09/2099" in mensagem


def test_payload_fora_do_contrato_erro_ptbr(monkeypatch, cache_isolado) -> None:
    """JSON válido mas fora do contrato (não é lista de registros) ⇒ ValueError
    pt-BR, não TypeError/KeyError cru."""
    monkeypatch.setattr(requests, "get", _FetchContadoSGS("ok"))
    provider = SGSProvider()
    with pytest.raises(ValueError, match="fora do contrato"):
        provider.serie_diaria(date(2026, 9, 1), date(2026, 9, 30))


def test_registro_fora_do_contrato_erro_ptbr(monkeypatch, cache_isolado) -> None:
    """Registro sem as chaves data/valor ⇒ ValueError pt-BR identificando o
    registro (sem KeyError cru)."""
    monkeypatch.setattr(requests, "get", _FetchContadoSGS([{"dia": "01/09/2026"}]))
    provider = SGSProvider()
    with pytest.raises(ValueError, match="registro fora do contrato"):
        provider.serie_diaria(date(2026, 9, 1), date(2026, 9, 30))


class _RespostaSemJSON:
    """Resposta HTTP com corpo não-JSON — caso real sondado (série inexistente
    responde HTML do portal do BCB)."""

    def __init__(self) -> None:
        self.url = "https://api.bcb.gov.br/dados/serie/bcdata.sgs.999999/dados"

    def raise_for_status(self) -> None:
        return None

    def json(self) -> Any:
        raise ValueError("Expecting value: line 1 column 1 (char 0)")


def test_resposta_nao_json_erro_ptbr(monkeypatch, cache_isolado) -> None:
    """Corpo 200 não-JSON (HTML do BCB) ⇒ ValueError pt-BR, não JSONDecodeError
    cru."""
    monkeypatch.setattr(requests, "get", lambda *a, **k: _RespostaSemJSON())
    provider = SGSProvider()
    with pytest.raises(ValueError, match="não é JSON válido"):
        provider.serie_diaria(date(2026, 9, 1), date(2026, 9, 30))


def test_lista_vazia_devolve_dataframe_vazio_com_colunas(monkeypatch, cache_isolado) -> None:
    """Lista vazia ⇒ DataFrame vazio COM as colunas do contrato (defensivo — o
    SGS real responde ``{"erro": ...}`` para período sem dados, coberto acima;
    o ramo vazio fica documentado no docstring do provider)."""
    monkeypatch.setattr(requests, "get", _FetchContadoSGS([]))
    provider = SGSProvider()
    df = provider.serie_diaria(date(2026, 9, 1), date(2026, 9, 30))
    assert isinstance(df, pd.DataFrame)
    assert df.empty
    assert list(df.columns) == ["data", "valor"]


# ----------------------------------------------------------------------
# Cache com TTL explícito (cache_isolado + relogio)
# ----------------------------------------------------------------------
def test_ttl_um_hit_dentro_do_ttl(provider_sgs, fetch_sgs_fixture, cache_isolado, relogio) -> None:
    """Chamadas dentro do TTL → um único fetch HTTP (as demais são hit)."""
    provider_sgs.serie_diaria(date(2026, 9, 1), date(2026, 9, 30))
    provider_sgs.serie_diaria(date(2026, 9, 1), date(2026, 9, 30))
    assert fetch_sgs_fixture.chamadas == 1

    relogio.avancar(TTL_SGS - 1)  # 1 s antes de expirar
    provider_sgs.serie_diaria(date(2026, 9, 1), date(2026, 9, 30))
    assert fetch_sgs_fixture.chamadas == 1  # ainda hit


def test_ttl_dois_hits_apos_expiracao(
    provider_sgs, fetch_sgs_fixture, cache_isolado, relogio
) -> None:
    """Relógio avança além do TTL → cache expira → segundo fetch real."""
    provider_sgs.serie_diaria(date(2026, 9, 1), date(2026, 9, 30))
    assert fetch_sgs_fixture.chamadas == 1

    relogio.avancar(TTL_SGS + 1)
    provider_sgs.serie_diaria(date(2026, 9, 1), date(2026, 9, 30))
    assert fetch_sgs_fixture.chamadas == 2


def test_cache_chave_inclui_periodo(provider_sgs, fetch_sgs_fixture) -> None:
    """Períodos distintos não colidem no cache (2 fetches); repetir o período
    é hit (continua 2)."""
    provider_sgs.serie_diaria(date(2026, 9, 1), date(2026, 9, 30))
    provider_sgs.serie_diaria(date(2026, 8, 1), date(2026, 8, 31))
    assert fetch_sgs_fixture.chamadas == 2
    provider_sgs.serie_diaria(date(2026, 8, 1), date(2026, 8, 31))
    assert fetch_sgs_fixture.chamadas == 2


def test_user_agent_explicito_no_fetch(provider_sgs, fetch_sgs_fixture) -> None:
    """O fetch manda User-Agent explícita do rfquant — nunca a
    default de biblioteca (``python-requests/...``)."""
    provider_sgs.serie_diaria(date(2026, 9, 1), date(2026, 9, 30))
    assert fetch_sgs_fixture.user_agent == USER_AGENT
    assert "rfquant" in fetch_sgs_fixture.user_agent


# ----------------------------------------------------------------------
# Teste de rede (job de CI semanal; deselecionado na suíte padrão
# pelos addopts `-m 'not network'` do pyproject — marker registrado, strict).
# Nasce SEM xfail e SEM skip: o endpoint já foi confirmado na captura da
# fixture, então falha de endpoint no job semanal é regressão, não
# expectativa. O corpo é o MESMO da bateria de séries: validar_df_serie +
# freshness de 7 dias.
# ----------------------------------------------------------------------
@pytest.mark.network
@repetir_se_rede_instavel()
def test_sgs_endpoint_responde_rede_real() -> None:
    """Endpoint vivo do SGS (série 12, CDI) passa na MESMA bateria.

    Janela de 14 dias ⇒ ≥ 5 pontos úteis mesmo com feriado. Freshness: último
    ponto publicado dentro de 7 dias (fins de semana/feriado não têm ponto) —
    o provider sem cache_isolado grava o cache do usuário, TTL 24 h, inofensivo
    (padrão do teste de rede do TesouroOficialProvider).
    """
    from test_data_contrato_series import COLUNAS_SGS, validar_df_serie

    hoje = date.today()
    df = SGSProvider().serie_diaria(hoje - timedelta(days=14), hoje)
    validar_df_serie(df, COLUNAS_SGS)
    assert max(df["data"]) >= hoje - timedelta(days=7)
