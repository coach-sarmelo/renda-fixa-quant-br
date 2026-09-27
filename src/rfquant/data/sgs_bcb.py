"""Fonte oficial do CDI diário — SGS/BCB, série 12, sem autenticação.

Endpoint oficial JSON
``https://api.bcb.gov.br/dados/serie/bcdata.sgs.12/dados?formato=json&dataInicial=DD/MM/AAAA&dataFinal=DD/MM/AAAA``
(Sistema Gerenciador de Séries Temporais do Banco Central).

Verificado diretamente no endpoint (2026-09-21; re-verificado na captura
da fixture, 2026-09-23): HTTP 200 sem auth; registros ``{"data": "DD/MM/AAAA",
"valor": "0.051660"}`` — **``valor`` chega como texto** (decimal com ponto) e é
convertido para ``float``; a unidade é a oficial do SGS, **% ao dia** — o
provider NÃO converte (consumidores anualizam por sua conta).

Comportamento com período sem dados (sondado 2026-09-23, ex.: mês futuro):
o SGS responde ``{"erro": {"statusCode": 404, ...}}`` — não devolve lista
vazia. O provider levanta ``ValueError`` com mensagem pt-BR; nunca retorna
DataFrame vazio silencioso.

Todo fetch passa por ``rfquant.data.cache`` (diskcache/SQLite) com TTL
explícito de 24 h — a série troca 1×/dia — e ``User-Agent`` explícito
(UA de biblioteca sofre filtro em fontes públicas).

Contrato próprio de série: NÃO estende a ABC
``DataProvider`` (série macro não é "título"); a disciplina de contrato fica
com a bateria de séries (``tests/test_data_contrato_series.py``).
``BrapiProvider.cdi()`` permanece fora do mapa de fontes automáticas.
"""

from __future__ import annotations

from datetime import date, datetime
from typing import Any

import pandas as pd
import requests

from rfquant.data import cache

SERIE_CDI = 12  # série 12 do SGS: CDI diário (% ao dia)
URL_BASE = "https://api.bcb.gov.br/dados/serie/bcdata.sgs.{serie}/dados"
TTL_SGS = 86_400  # 24 h: a série troca 1×/dia
USER_AGENT = (
    "rfquant/0.1.0 (renda-fixa-quant-br; +https://github.com/coach-sarmelo/renda-fixa-quant-br)"
)
TIMEOUT_SGS = 30  # payload é pequeno (KBs) — 30 s folgam


class SGSProvider:
    """Provider da série SGS/BCB — default: série 12, o CDI diário.

    Args:
        serie: número da série SGS (padrão 12 — CDI diário).
        ttl: TTL do cache em segundos (padrão 24 h — série diária).
        base_url: URL com o placeholder ``{serie}`` (para teste com host fake).

    Uso::

        df = SGSProvider().serie_diaria(date(2026, 9, 1), date(2026, 9, 30))
    """

    def __init__(
        self,
        serie: int = SERIE_CDI,
        ttl: int = TTL_SGS,
        base_url: str | None = None,
    ) -> None:
        self.serie = serie
        self.ttl = ttl
        self.url = (base_url or URL_BASE).format(serie=serie)

    # ------------------------------------------------------------------
    # API pública
    # ------------------------------------------------------------------
    def serie_diaria(self, inicio: date, fim: date) -> pd.DataFrame:
        """Série diária no período ``[inicio, fim]`` — colunas ``data``/``valor``.

        ``data`` é ``datetime.date`` (parse de ``DD/MM/AAAA``) e ``valor`` é
        ``float`` na unidade oficial do SGS (% ao dia, p.ex. 0,051660).
        DataFrame ordenado por data; um registro por dia útil (fins de semana
        e feriados não existem na série).

        Período sem dados (mês futuro, anterior à série, série inexistente)
        levanta ``ValueError`` com mensagem pt-BR — forma de erro real do SGS
        (``{"erro": ...}``, sondada em 2026-09-23).
        """
        params = {
            "formato": "json",
            "dataInicial": inicio.strftime("%d/%m/%Y"),
            "dataFinal": fim.strftime("%d/%m/%Y"),
        }
        return self._parsear(self._fetch(params), inicio, fim)

    # ------------------------------------------------------------------
    # Internos
    # ------------------------------------------------------------------
    def _fetch(self, params: dict[str, str]) -> Any:
        """Payload cru do SGS: cache → rede, com TTL e User-Agent explícitos."""
        cached: Any | None = cache.get(self.url, params)
        if cached is not None:
            return cached
        resp = requests.get(
            self.url,
            params=params,
            headers={"User-Agent": USER_AGENT},
            timeout=TIMEOUT_SGS,
        )
        resp.raise_for_status()
        try:
            payload = resp.json()
        except ValueError as exc:  # JSONDecodeError herda de ValueError
            msg = f"SGS: resposta do BCB não é JSON válido (url={resp.url})."
            raise ValueError(msg) from exc
        cache.set(self.url, payload, params=params, ttl=self.ttl)
        return payload

    def _parsear(self, payload: Any, inicio: date, fim: date) -> pd.DataFrame:
        """JSON SGS → DataFrame (``data``: date; ``valor``: float, % ao dia)."""
        if isinstance(payload, dict):
            # Forma de erro real do SGS (período sem dados / série inexistente).
            msg = (
                f"SGS: sem dados para a série {self.serie} no período "
                f"{inicio:%d/%m/%Y} a {fim:%d/%m/%Y} (o BCB respondeu: {payload})."
            )
            raise ValueError(msg)
        if not isinstance(payload, list):
            msg = (
                f"SGS: payload fora do contrato da API (esperada lista de "
                f"registros data/valor; recebido: {type(payload).__name__})."
            )
            raise ValueError(msg)
        registros = [self._registro(item) for item in payload]
        df = pd.DataFrame(registros, columns=["data", "valor"])
        if df.empty:
            return df
        return df.sort_values("data").reset_index(drop=True)

    @staticmethod
    def _registro(item: Any) -> dict[str, Any]:
        """Um registro SGS → ``{"data": date, "valor": float}`` (dd/mm/AAAA)."""
        try:
            return {
                "data": datetime.strptime(str(item["data"]), "%d/%m/%Y").date(),
                "valor": float(item["valor"]),
            }
        except (KeyError, TypeError, ValueError) as exc:
            msg = (
                f"SGS: registro fora do contrato "
                f"{{'data': 'DD/MM/AAAA', 'valor': número}} — {item!r}."
            )
            raise ValueError(msg) from exc
