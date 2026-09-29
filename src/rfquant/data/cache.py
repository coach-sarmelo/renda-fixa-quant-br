"""Cache simples de requisições HTTP usando diskcache."""

from __future__ import annotations

import hashlib
import json
from typing import Any

import diskcache as dc
import numpy as np
import pandas as pd

from rfquant.config import settings

settings.ensure_dirs()
_cache = dc.Cache(str(settings.cache_dir / "http"))


def _key(url: str, params: dict[str, Any] | None = None) -> str:
    raw = url + json.dumps(params or {}, sort_keys=True, default=str)
    return hashlib.sha256(raw.encode()).hexdigest()


def get(url: str, params: dict[str, Any] | None = None) -> Any | None:
    """Recupera um valor do cache, ou None se não existir."""
    return _cache.get(_key(url, params))


def set(url: str, value: Any, params: dict[str, Any] | None = None, ttl: int = 3600) -> None:
    """Armazena um valor no cache com TTL em segundos (padrão: 1h)."""
    _cache.set(_key(url, params), value, expire=ttl)


def clear() -> None:
    """Limpa todo o cache HTTP."""
    _cache.clear()


def frame_para_cache(df: pd.DataFrame) -> dict[str, Any]:
    """Serializa um frame em estrutura portável para o cache.

    O pandas 3.x, com pyarrow instalado, faz TODA coluna de string de um
    DataFrame virar ``ArrowStringArray`` — o pickle de qualquer frame assim
    referencia o pyarrow e não desserializa em ambiente sem o pacote, não
    importando o dtype: ``astype(object)``, ``to_numpy`` e a re-inferência na
    inserção mantêm o bloco aliasado ou re-criam o dtype arrow. A saída
    portável é um dict de arrays numpy (strings como ``object`` de ``str``
    python) que o ambiente LEITOR reconstrói com os dtypes nativos dele —
    ``frame_do_cache``. O ganho da cache do frame parseado se preserva: o
    ``read_csv`` integral continua rodando só no cache miss.
    """
    return {nome: np.asarray(df[nome]) for nome in df.columns}


def frame_do_cache(payload: Any) -> pd.DataFrame | None:
    """Reconstrói o frame de um payload de ``frame_para_cache``.

    Devolve ``None`` se o payload não é do formato portável (entrada
    legada de frame picklado direto, pré-portabilidade) — o chamador
    trata como cache miss e regrava no formato novo.
    """
    if not isinstance(payload, dict) or not all(isinstance(k, str) for k in payload):
        return None
    return pd.DataFrame(dict(payload))
