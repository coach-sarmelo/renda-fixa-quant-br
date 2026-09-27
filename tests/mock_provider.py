"""MockProvider: provider offline que lê ``tesouro_sample.csv``.

Segunda implementação de ``DataProvider`` para a bateria de contrato
(``tests/test_data_contrato.py``): o MESMO contrato exigido do
``TesouroDiretoProvider`` vale aqui — mock sem barra mais baixa.

``historico_taxas`` serve a série SINTÉTICA ``serie_historica_sample.csv``
(2 títulos × dias úteis de 01/2026 — documentação no cabeçalho ``#`` da
própria fixture) com o MESMO contrato do ``TesouroOficialProvider``
(colunas data/taxa_compra/taxa_venda/pu_compra/pu_venda, ordenado por data) —
a bateria de séries (``tests/test_data_contrato_series.py``)
cobra o histórico também do mock.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from io import StringIO
from pathlib import Path

import pandas as pd

from rfquant.data.base import DataProvider, Titulo

CAMINHO_SAMPLE = Path(__file__).parent / "fixtures" / "tesouro_sample.csv"
CAMINHO_SAMPLE_SERIE = Path(__file__).parent / "fixtures" / "serie_historica_sample.csv"
COLUNAS_SERIE = ["data", "taxa_compra", "taxa_venda", "pu_compra", "pu_venda"]


def _dec(valor: object) -> Decimal | None:
    """Célula do CSV → Decimal; célula vazia → None (mesma semântica do parser real)."""
    if pd.isna(valor):
        return None
    try:
        return Decimal(str(valor))
    except Exception:
        return None


class MockProvider(DataProvider):
    """Provider determinístico sem rede: os 5 títulos do ``tesouro_sample.csv``
    e a série histórica sintética do ``serie_historica_sample.csv``."""

    def __init__(self, caminho: Path | None = None, caminho_serie: Path | None = None) -> None:
        self._caminho = caminho or CAMINHO_SAMPLE
        self._caminho_serie = caminho_serie or CAMINHO_SAMPLE_SERIE

    def titulos_disponiveis(self, data: date | None = None) -> pd.DataFrame:
        data_ref = data or date.today()
        bruto = pd.read_csv(self._caminho)
        titulos = [self._parse(linha, data_ref) for _, linha in bruto.iterrows()]
        saida = pd.DataFrame([t.model_dump() for t in titulos])
        if saida.empty:
            return saida
        return saida.sort_values(["tipo", "vencimento"]).reset_index(drop=True)

    def historico_taxas(self, titulo: str, inicio: date, fim: date) -> pd.DataFrame:
        """Série histórica sintética — mesmo contrato do ``TesouroOficialProvider``.

        Lê ``serie_historica_sample.csv``, filtra por título e pela janela
        ``[inicio, fim]`` (inclusiva) e devolve DataFrame com colunas
        ``data, taxa_compra, taxa_venda, pu_compra, pu_venda`` ordenado por
        ``data`` (``date``; taxas em fração a.a. e PU em R$ — floats).
        Título inexistente ou janela sem dados ⇒ DataFrame vazio COM as
        colunas do contrato (nunca KeyError cru), padrão do provider oficial.
        """
        bruto = self._ler_serie()
        bruto = bruto[bruto["titulo"] == titulo]
        bruto = bruto.assign(data=[date.fromisoformat(str(d)) for d in bruto["data"]])
        sel = bruto[(bruto["data"] >= inicio) & (bruto["data"] <= fim)]
        saida = pd.DataFrame({col: sel[col].to_list() for col in COLUNAS_SERIE})
        return saida.sort_values("data").reset_index(drop=True)

    def _ler_serie(self) -> pd.DataFrame:
        """CSV da série sintética sem as linhas de cabeçalho ``#`` (auditoria)."""
        linhas = self._caminho_serie.read_text(encoding="utf-8").splitlines()
        corpo = "\n".join(linha for linha in linhas if not linha.startswith("#"))
        return pd.read_csv(StringIO(corpo))

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
