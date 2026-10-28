"""Fixtures compartilhadas pelos testes do Renda Fixa Quant BR."""

from __future__ import annotations

import functools
import json
import time
from collections.abc import Callable
from datetime import date
from pathlib import Path
from typing import Any

import diskcache as dc
import pandas as pd
import pytest
import requests

from rfquant.data import cache
from rfquant.data.cvm_fundos import RedeIndisponivel
from rfquant.data.tesouro_direto import TesouroDiretoProvider

CAMINHO_SAMPLE = Path(__file__).parent / "fixtures" / "tesouro_sample.csv"
FIXTURE_ZIP = Path(__file__).parent / "fixtures" / "cvm_informe_sample.zip"
CAMINHO_FIXTURE_SGS = Path(__file__).parent / "fixtures" / "sgs_serie12_sample.json"


@pytest.fixture
def data_ref() -> date:
    """Data de referência fixa para testes determinísticos."""
    return date(2026, 1, 2)


# ----------------------------------------------------------------------
# Padrões de mock/isolamento (replicar em testes novos)
# ----------------------------------------------------------------------
class RespostaFake:
    """Resposta HTTP falsa: o mínimo que os providers pedem
    (``raise_for_status`` + ``json``/``text``). Usar junto com ``fetch_mockado``
    ou direto em ``monkeypatch.setattr(requests, "get", ...)``."""

    def __init__(self, payload: dict, texto: str | None = None) -> None:
        self._payload = payload
        self.text = texto if texto is not None else str(payload)

    def raise_for_status(self) -> None:
        return None

    def json(self) -> dict:
        return self._payload


def fixture_payload() -> list[dict[str, str]]:
    """Conteúdo JSON da fixture real do SGS (série 12 — CDI diário), sem as
    linhas de cabeçalho ``#``. Compartilhada pelos testes do provider e da
    CLI (``--cdi-auto`` e ``fundos resumo`` sem rede)."""
    linhas = CAMINHO_FIXTURE_SGS.read_text(encoding="utf-8").splitlines()
    corpo = "\n".join(linha for linha in linhas if not linha.startswith("#"))
    return json.loads(corpo)


class RespostaZip:
    """Resposta HTTP falsa: corpo é o ZIP da fixture da CVM (lido via
    ``content``). Compartilhada pelos testes do provider e de ``fundos resumo``."""

    def __init__(self, conteudo: bytes) -> None:
        self.content = conteudo

    def raise_for_status(self) -> None:
        return None


class RespostaErro:
    """Resposta HTTP falsa que falha no ``raise_for_status`` (mês sem arquivo).

    Fiel ao ``raise_for_status`` real do requests: o ``HTTPError`` carrega a
    própria resposta (``response=self``) e a resposta expõe ``status_code``
    404 — é por esse status que o provider distingue mês não publicado
    (HTTP 4xx) de falha de rede.
    """

    status_code = 404

    def raise_for_status(self) -> None:
        raise requests.HTTPError("404 Client Error: Not Found for url: fake", response=self)


@pytest.fixture
def payload_brapi_tesouro() -> dict:
    """Payload brapi-shaped (chaves v1: name/type/maturityDate/buyRate/...)
    derivado de ``tesouro_sample.csv`` — os mesmos 5 títulos que o MockProvider
    lê. Sintético, não é captura; o parsing do arquivo real é coberto com
    fixture própria (test_data_tesouro_oficial.py)."""
    df = pd.read_csv(CAMINHO_SAMPLE)
    linhas = [
        {
            "name": str(r["nome"]),
            "type": str(r["tipo"]),
            "maturityDate": str(r["vencimento"]),
            "buyRate": float(r["taxa_compra"]),
            "sellRate": float(r["taxa_venda"]),
            "buyPrice": float(r["pu_compra"]),
            "sellPrice": float(r["pu_venda"]),
        }
        for _, r in df.iterrows()
    ]
    return {"treasury": linhas}


class _FetchContado:
    """``requests.get`` instrumentado: conta chamadas e devolve payload fixo."""

    def __init__(self, payload: dict) -> None:
        self._payload = payload
        self.chamadas = 0

    def __call__(self, url, params=None, timeout=None, **kwargs):
        self.chamadas += 1
        return RespostaFake(self._payload)


@pytest.fixture
def fetch_mockado(monkeypatch, payload_brapi_tesouro) -> _FetchContado:
    """Troca ``requests.get`` por um fetch instrumentado (sem rede).
    Padrão do repo para HTTP em teste: assert no nº de ``.chamadas``."""
    fetch = _FetchContado(payload_brapi_tesouro)
    monkeypatch.setattr(requests, "get", fetch)
    return fetch


@pytest.fixture
def cache_isolado(tmp_path, monkeypatch):
    """Substitui o cache HTTP global (``~/.rfquant``) por um diskcache novo em
    ``tmp_path``. TODO teste que exerça ``rfquant.data.cache`` DEVE usar esta
    fixture — nunca o cache real do usuário (estado vaza entre testes)."""
    novo = dc.Cache(str(tmp_path / "http"))
    monkeypatch.setattr(cache, "_cache", novo)
    yield novo
    novo.close()


class _Relogio:
    """Relógio controlável: ``avancar(segundos)`` move o agora."""

    def __init__(self) -> None:
        self._t = time.time()

    def avancar(self, segundos: float) -> None:
        self._t += segundos

    def __call__(self) -> float:
        return self._t


@pytest.fixture
def relogio(monkeypatch) -> _Relogio:
    """Patch de ``time.time`` — diskcache grava ``expire`` absoluto com
    ``time.time()`` qualificado, então o patch no módulo o alcança. Começa no
    agora REAL para não quebrar bookkeeping interno. Nunca usar ``sleep``."""
    r = _Relogio()
    monkeypatch.setattr(time, "time", r)
    return r


@pytest.fixture
def provider_tesouro_teste() -> TesouroDiretoProvider:
    """Provider apontando para host fake — só faz sentido com ``fetch_mockado``."""
    return TesouroDiretoProvider(token="token-teste", base_url="http://teste.local")


# ----------------------------------------------------------------------
# Tolerância a instabilidade transitória de rede (testes ``network``)
# ----------------------------------------------------------------------
# Limitador de taxa do CSV do Tesouro (medido em out/2026): janela deslizante
# por IP de MINUTOS — o Retry-After: 30 que o servidor envia é otimista, então
# o 429 tem piso de espera próprio e crescente por tentativa.
PAUSA_429 = 60.0
TETO_ESPERA = 120.0


def get_resiliente(
    url: str, timeout: float = 30.0, tentativas: int = 3, pausa: float = 5.0
) -> requests.Response:
    """GET que repete diante de instabilidade transitória do endpoint.

    Timeout, falha de conexão e resposta 5xx gastam uma tentativa e esperam
    ``pausa`` segundos; 429 (limitação de taxa) espera o maior entre o
    ``Retry-After`` recebido e o piso crescente de ``PAUSA_429``. A última
    tentativa devolve a resposta ou propaga a exceção como estão —
    indisponibilidade persistente continua falhando. Os demais 4xx nunca
    são repetidos: quebra real não é instabilidade.
    """
    tentativa = 0
    while True:
        tentativa += 1
        ultima = tentativa == tentativas
        try:
            resposta = requests.get(url, timeout=timeout)
        except (requests.exceptions.Timeout, requests.exceptions.ConnectionError):
            if ultima:
                raise
            time.sleep(pausa)
            continue
        if resposta.status_code == 429 and not ultima:
            time.sleep(_espera_429(tentativa, resposta))
            continue
        if resposta.status_code < 500 or ultima:
            return resposta
        time.sleep(pausa)


def _causa_raiz(exc: BaseException) -> BaseException:
    """A causa original de ``raise ... from`` dos providers (ou a própria)."""
    return exc.__cause__ if exc.__cause__ is not None else exc


def _retry_after(resposta: requests.Response | None) -> float | None:
    """``Retry-After`` em segundos (formato delta), se presente e válido."""
    if resposta is None:
        return None
    try:
        return float(resposta.headers.get("Retry-After"))
    except (TypeError, ValueError):
        return None


def _espera_429(tentativa: int, resposta: requests.Response | None) -> float:
    """Espera diante de 429: máximo entre Retry-After e piso crescente
    (``PAUSA_429`` × tentativa), com teto de segurança ``TETO_ESPERA``."""
    sugerida = _retry_after(resposta) or 0.0
    return min(max(sugerida, PAUSA_429 * tentativa), TETO_ESPERA)


def _e_falha_transitoria(exc: BaseException) -> bool:
    """A exceção é plausivelmente transitória de rede, não defeito.

    Timeout e falha de conexão sempre contam; HTTP 5xx e 429 (limitação de
    taxa) sim, demais 4xx não. Os providers embrulham essas falhas em
    ``ValueError``/exceções próprias via ``raise ... from`` — a causa
    original na cadeia é o que decide, então quebra de domínio (payload
    inválido, arquivo não publicado) continua falhando na primeira
    ocorrência.
    """
    if isinstance(exc, RedeIndisponivel):
        return True  # o provider da CVM já separou 4xx em InformeNaoDisponivel
    causa = _causa_raiz(exc)
    if isinstance(causa, (requests.exceptions.Timeout, requests.exceptions.ConnectionError)):
        return True
    if isinstance(causa, requests.exceptions.HTTPError):
        status = getattr(causa.response, "status_code", None)
        return isinstance(status, int) and (status >= 500 or status == 429)
    return False


def _espera_do_erro(exc: BaseException, tentativa: int, padrao: float) -> float:
    """Espera para retentar: 429 usa ``_espera_429``, o resto usa ``padrao``."""
    causa = _causa_raiz(exc)
    if isinstance(causa, requests.exceptions.HTTPError):
        status = getattr(causa.response, "status_code", None)
        if status == 429:
            return _espera_429(tentativa, causa.response)
    return padrao


def repetir_se_rede_instavel(tentativas: int = 3, pausa: float = 5.0) -> Callable:
    """Decorador que repete a função enquanto a falha for transitória.

    Mesma política de ``get_resiliente``, para testes que exercitam o
    provider inteiro (cache, parse e validação inclusos) em vez de um GET
    isolado: a exceção da última tentativa propaga intocada.
    """

    def decorador(funcao: Callable[..., Any]) -> Callable[..., Any]:
        @functools.wraps(funcao)
        def invocacao(*args: Any, **kwargs: Any) -> Any:
            for indice in range(1, tentativas + 1):
                try:
                    return funcao(*args, **kwargs)
                except (ValueError, requests.RequestException, RedeIndisponivel) as exc:
                    if indice == tentativas or not _e_falha_transitoria(exc):
                        raise
                    time.sleep(_espera_do_erro(exc, indice, pausa))

        return invocacao

    return decorador
