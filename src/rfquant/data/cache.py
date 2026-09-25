"""Cache simples de requisições HTTP usando diskcache."""

from __future__ import annotations

import hashlib
import json
from typing import Any

import diskcache as dc

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
