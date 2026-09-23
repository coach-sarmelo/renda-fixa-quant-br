"""Interface base dos providers de dados e modelo de Título."""

from __future__ import annotations

from abc import ABC, abstractmethod
from datetime import date
from decimal import Decimal
from typing import Literal

import pandas as pd
from pydantic import BaseModel, Field

TipoTitulo = Literal["Prefixado", "IPCA+", "Selic", "CDI", "Outro"]

class Titulo(BaseModel):
    """Representação normalizada de um título de renda fixa."""

    nome: str = Field(..., description="Ex: 'Tesouro IPCA+ 2035'")
    tipo: TipoTitulo
    vencimento: date
    taxa_compra: Decimal | None = None
    taxa_venda: Decimal | None = None
    pu_compra: Decimal | None = None
    pu_venda: Decimal | None = None
    data_referencia: date
    isento_ir: bool = False
    emissor: str = "Tesouro Nacional"

class DataProvider(ABC):
    """Interface para acesso a dados de renda fixa."""

    @abstractmethod
    def titulos_disponiveis(self, data: date | None = None) -> pd.DataFrame:
        """Retorna DataFrame com títulos disponíveis na data informada."""

    @abstractmethod
    def historico_taxas(
        self,
        titulo: str,
        inicio: date,
        fim: date,
    ) -> pd.DataFrame:
        """Retorna série histórica de taxas e PU para um título."""
