"""Provider de dados do Tesouro Direto.

Fonte primária: brapi.dev (endpoint /api/treasury).
Fallback: scraping do site oficial (a ser implementado).
"""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal

import pandas as pd
import requests

from rfquant.config import settings
from rfquant.data import cache
from rfquant.data.base import DataProvider, Titulo


class TesouroDiretoProvider(DataProvider):
    """Acesso aos dados do Tesouro Direto via brapi.dev."""

    def __init__(self, token: str | None = None, base_url: str | None = None) -> None:
        self.token = token or settings.brapi_token
        self.base_url = (base_url or settings.brapi_base_url).rstrip("/")

    # ------------------------------------------------------------------
    # API pública
    # ------------------------------------------------------------------
    def titulos_disponiveis(self, data: date | None = None) -> pd.DataFrame:
        data_ref = data or date.today()
        raw = self._fetch_treasury()
        titulos = [self._parse_titulo(item, data_ref) for item in raw]
        df = pd.DataFrame([t.model_dump() for t in titulos])
        if df.empty:
            return df
        return df.sort_values(["tipo", "vencimento"]).reset_index(drop=True)

    def historico_taxas(
        self,
        titulo: str,
        inicio: date,
        fim: date,
    ) -> pd.DataFrame:
        url = f"{self.base_url}/treasury/indicators"
        params = {
            "name": titulo,
            "from": inicio.isoformat(),
            "to": fim.isoformat(),
            "sortBy": "date",
            "sortOrder": "asc",
            "token": self.token or "",
        }
        cached = cache.get(url, params)
        if cached is not None:
            return pd.DataFrame(cached)

        resp = requests.get(url, params=params, timeout=20)
        resp.raise_for_status()
        payload = resp.json()
        # A fonte responde tanto com {"indicators": [...]} quanto com a
        # lista pura — um corpo sem indicadores vira histórico vazio.
        rows = payload if isinstance(payload, list) else payload.get("indicators", [])
        cache.set(url, rows, params, ttl=3600)
        return pd.DataFrame(rows)

    # ------------------------------------------------------------------
    # Internos
    # ------------------------------------------------------------------
    def _fetch_treasury(self) -> list[dict]:
        url = f"{self.base_url}/treasury"
        params = {"token": self.token or ""}
        cached: list[dict] | None = cache.get(url, params)
        if cached is not None:
            return cached

        resp = requests.get(url, params=params, timeout=20)
        resp.raise_for_status()
        payload = resp.json()
        # Mesmo contrato do histórico: a fonte responde tanto com
        # {"treasury": [...]} quanto com a lista pura — o isinstance vem
        # primeiro, senão payload.get estoura AttributeError na lista.
        rows: list[dict] = payload if isinstance(payload, list) else payload.get("treasury", [])
        cache.set(url, rows, params, ttl=900)
        return rows

    @staticmethod
    def _parse_titulo(item: dict, data_ref: date) -> Titulo:
        tipo_raw = str(item.get("type", "")).lower()
        if "ipca" in tipo_raw or "ntnb-p" in tipo_raw:
            tipo = "IPCA+"
        elif "prefixado" in tipo_raw or "ltn" in tipo_raw or "ntn-f" in tipo_raw:
            tipo = "Prefixado"
        elif "selic" in tipo_raw or "lft" in tipo_raw:
            tipo = "Selic"
        else:
            tipo = "Outro"

        venc = item.get("maturityDate") or item.get("vencimento")
        if isinstance(venc, str):
            vencimento = datetime.fromisoformat(venc.replace("Z", "")).date()
        elif isinstance(venc, date):
            vencimento = venc
        else:
            vencimento = data_ref

        def dec(value) -> Decimal | None:
            if value in (None, "", "-"):
                return None
            try:
                return Decimal(str(value))
            except Exception:
                return None

        return Titulo(
            nome=str(item.get("name") or item.get("nome") or "Desconhecido"),
            tipo=tipo,  # type: ignore[arg-type]
            vencimento=vencimento,
            taxa_compra=dec(item.get("buyRate") or item.get("taxa_compra")),
            taxa_venda=dec(item.get("sellRate") or item.get("taxa_venda")),
            pu_compra=dec(item.get("buyPrice") or item.get("pu_compra")),
            pu_venda=dec(item.get("sellPrice") or item.get("pu_venda")),
            data_referencia=data_ref,
            isento_ir=False,
            emissor="Tesouro Nacional",
        )
