"""Fixtures compartilhadas pelos testes do Renda Fixa Quant BR."""

from __future__ import annotations

import time
from datetime import date
from pathlib import Path

import diskcache as dc
import pandas as pd
import pytest
import requests

from rfquant.data import cache
from rfquant.data.tesouro_direto import TesouroDiretoProvider

CAMINHO_SAMPLE = Path(__file__).parent / "fixtures" / "tesouro_sample.csv"


@pytest.fixture
def data_ref() -> date:
    """Data de referência fixa para testes determinísticos."""
    return date(2026, 1, 2)

@pytest.fixture
def vencimento_1a() -> date:
    """Vencimento daqui a ~1 ano."""
    return date(2027, 1, 2)

@pytest.fixture
def vencimento_5a() -> date:
    """Vencimento daqui a ~5 anos."""
    return date(2031, 1, 2)

@pytest.fixture
def tesouro_ipca_2035() -> dict:
    """Título de exemplo: Tesouro IPCA+ 2035."""
    return {
        "nome": "Tesouro IPCA+ 2035",
        "tipo": "IPCA+",
        "data_compra": date(2026, 1, 2),
        "data_vencimento": date(2035, 5, 15),
        "valor_nominal": 1000.0,
        "taxa_anual": 0.062,
        "taxa_cupom_anual": 0.06,
        "frequencia_cupom": 2,
    }

@pytest.fixture
def tesouro_prefixado_2029() -> dict:
    """Título de exemplo: Tesouro Prefixado 2029 (zero-cupom)."""
    return {
        "nome": "Tesouro Prefixado 2029",
        "tipo": "Prefixado",
        "data_compra": date(2026, 1, 2),
        "data_vencimento": date(2029, 1, 1),
        "valor_nominal": 1000.0,
        "taxa_anual": 0.115,
        "taxa_cupom_anual": 0.0,
        "frequencia_cupom": 2,
    }



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
