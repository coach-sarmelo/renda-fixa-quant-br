"""Fonte oficial do Tesouro Direto — Tesouro Transparente (CKAN).

Endpoint oficial (CSV diário)
``precotaxatesourodireto.csv`` do dataset ``taxas-dos-titulos-ofertados-pelo-tesouro-direto``
(https://www.tesourotransparente.gov.br/ckan/dataset/df56aa42-484a-4a59-8184-7676580c81e3/resource/796d2059-14e9-44e3-80c9-2d9e30b405c1/download/precotaxatesourodireto.csv).

Verificado em 2026-09-19 (curl): HTTP 200 ``text/csv``, ~14,5 MB,
histórico por ``Data Base`` diária desde 31/12/2004, colunas
``Tipo Titulo; Data Vencimento; Data Base; Taxa/PU Compra/Venda Manha``,
separador ``;``, decimais pt-BR (vírgula), conteúdo ASCII. Licença ODbL;
sem autenticação. Taxas em % a.a. — convertidas para fração
(14,10 → 0,141) para casar com o contrato do ``Titulo``.

O arquivo inteiro é baixado no máximo 1×/24 h via ``rfquant.data.cache``
(diskcache/SQLite) e o parsing filtra a ``Data Base`` de interesse —
requisito de cache local (ver docs/dados.md).
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from io import StringIO

import pandas as pd
import requests

from rfquant.data import cache
from rfquant.data.base import DataProvider, Titulo

URL_CSV = (
    "https://www.tesourotransparente.gov.br/ckan/dataset/"
    "df56aa42-484a-4a59-8184-7676580c81e3/resource/"
    "796d2059-14e9-44e3-80c9-2d9e30b405c1/download/precotaxatesourodireto.csv"
)
TTL_CSV = 86_400  # 24 h: o arquivo troca 1×/dia (~10h)


class TesouroOficialProvider(DataProvider):
    """Fonte oficial sem token do Tesouro Direto (fonte: ``--fonte=oficial``)."""

    def __init__(self, csv_url: str | None = None, ttl: int = TTL_CSV) -> None:
        self.url = csv_url or URL_CSV
        self.ttl = ttl

    # ------------------------------------------------------------------
    # API pública
    # ------------------------------------------------------------------
    def titulos_disponiveis(self, data: date | None = None) -> pd.DataFrame:
        bruto = self._ler_csv()
        base = pd.Timestamp(data) if data is not None else bruto["Data Base"].max()
        dia = bruto[bruto["Data Base"] == base]
        titulos = [self._titulo(linha) for _, linha in dia.iterrows()]
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
        bruto = self._ler_csv()
        bruto = bruto.assign(
            nome=bruto["Tipo Titulo"] + " " + bruto["Data Vencimento"].dt.year.astype(str)
        )
        sel = bruto[
            (bruto["nome"] == titulo)
            & (bruto["Data Base"] >= pd.Timestamp(inicio))
            & (bruto["Data Base"] <= pd.Timestamp(fim))
        ]
        return (
            pd.DataFrame(
                {
                    "data": sel["Data Base"].dt.date,
                    "taxa_compra": sel["Taxa Compra Manha"] / 100,
                    "taxa_venda": sel["Taxa Venda Manha"] / 100,
                    "pu_compra": sel["PU Compra Manha"],
                    "pu_venda": sel["PU Venda Manha"],
                }
            )
            .sort_values("data")
            .reset_index(drop=True)
        )

    # ------------------------------------------------------------------
    # Internos
    # ------------------------------------------------------------------
    def _ler_csv(self) -> pd.DataFrame:
        cached: str | None = cache.get(self.url)
        if cached is not None:
            return self._parsear(cached)
        resp = requests.get(self.url, timeout=120)
        resp.raise_for_status()
        texto = resp.text
        cache.set(self.url, texto, ttl=self.ttl)
        return self._parsear(texto)

    @staticmethod
    def _parsear(texto: str) -> pd.DataFrame:
        return pd.read_csv(
            StringIO(texto),
            sep=";",
            decimal=",",
            thousands=".",
            parse_dates=["Data Vencimento", "Data Base"],
            date_format="%d/%m/%Y",
        )

    @staticmethod
    def _titulo(linha: pd.Series) -> Titulo:
        tipo_raw = str(linha["Tipo Titulo"])
        venc = linha["Data Vencimento"].date()

        def dec(valor: object, dividir_por_100: bool = False) -> Decimal | None:
            if pd.isna(valor):
                return None
            try:
                d = Decimal(str(valor))
                return d / Decimal(100) if dividir_por_100 else d
            except Exception:
                return None

        return Titulo(
            nome=f"{tipo_raw} {venc.year}",
            tipo=_map_tipo(tipo_raw),  # type: ignore[arg-type]
            vencimento=venc,
            taxa_compra=dec(linha["Taxa Compra Manha"], dividir_por_100=True),
            taxa_venda=dec(linha["Taxa Venda Manha"], dividir_por_100=True),
            pu_compra=dec(linha["PU Compra Manha"]),
            pu_venda=dec(linha["PU Venda Manha"]),
            data_referencia=linha["Data Base"].date(),
            isento_ir=False,
            emissor="Tesouro Nacional",
        )


def _map_tipo(tipo_raw: str) -> str:
    """Nome do CSV → TipoTitulo (IGPM+ e demais variantes caem em 'Outro')."""
    t = tipo_raw.lower()
    if "selic" in t:
        return "Selic"
    if "ipca" in t:
        return "IPCA+"
    if "prefixado" in t:
        return "Prefixado"
    return "Outro"
