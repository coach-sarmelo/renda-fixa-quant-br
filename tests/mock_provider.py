"""MockProvider: provider offline que lê ``tesouro_sample.csv``.

Segunda implementação de ``DataProvider`` para a bateria de contrato
(``tests/test_data_contrato.py``): o MESMO contrato exigido do
``TesouroDiretoProvider`` vale aqui — mock sem barra mais baixa.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from pathlib import Path

import pandas as pd

from rfquant.data.base import DataProvider, Titulo

CAMINHO_SAMPLE = Path(__file__).parent / "fixtures" / "tesouro_sample.csv"


def _dec(valor: object) -> Decimal | None:
    """Célula do CSV → Decimal; célula vazia → None (mesma semântica do parser real)."""
    if pd.isna(valor):
        return None
    try:
        return Decimal(str(valor))
    except Exception:
        return None


class MockProvider(DataProvider):
    """Provider determinístico sem rede: os 5 títulos do ``tesouro_sample.csv``."""

    def __init__(self, caminho: Path | None = None) -> None:
        self._caminho = caminho or CAMINHO_SAMPLE

    def titulos_disponiveis(self, data: date | None = None) -> pd.DataFrame:
        data_ref = data or date.today()
        bruto = pd.read_csv(self._caminho)
        titulos = [self._parse(linha, data_ref) for _, linha in bruto.iterrows()]
        saida = pd.DataFrame([t.model_dump() for t in titulos])
        if saida.empty:
            return saida
        return saida.sort_values(["tipo", "vencimento"]).reset_index(drop=True)

    def historico_taxas(self, titulo: str, inicio: date, fim: date) -> pd.DataFrame:
        raise NotImplementedError(
            "MockProvider não implementa historico_taxas (coberto com fixture própria)."
        )

    @staticmethod
    def _parse(linha: pd.Series, data_ref: date) -> Titulo:
        return Titulo(
            nome=str(linha["nome"]),
            tipo=str(linha["tipo"]),  # type: ignore[arg-type]
            vencimento=date.fromisoformat(str(linha["vencimento"])),
            taxa_compra=_dec(linha["taxa_compra"]),
            taxa_venda=_dec(linha["taxa_venda"]),
            pu_compra=_dec(linha["pu_compra"]),
            pu_venda=_dec(linha["pu_venda"]),
            data_referencia=data_ref,
            isento_ir=str(linha["isento_ir"]).lower() == "true",
            emissor=str(linha["emissor"]),
        )
