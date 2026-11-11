"""Interface base dos providers de dados e modelo de Título."""

from __future__ import annotations

from abc import ABC, abstractmethod
from datetime import date
from decimal import Decimal
from typing import Literal

import pandas as pd
from pydantic import BaseModel, Field, field_validator, model_validator

TipoTitulo = Literal[
    "Prefixado",
    "IPCA+",
    "Selic",
    "CDI",
    "Outro",
    "CDB",
    "LCI/LCA",
    "Debênture",
    "Fundo",
]

# Lista fechada de categorias de produto — consumida pelo IR por categoria.
CATEGORIAS: tuple[str, ...] = (
    "CDB",
    "LCI",
    "LCA",
    "debênture-comum",
    "debênture-incentivada",
    "fundo",
)
CATEGORIAS_ISENTAS: tuple[str, ...] = ("LCI", "LCA", "debênture-incentivada")


def validar_categoria(categoria: str | None) -> str | None:
    """Categoria fora da lista fechada ⇒ ValueError em pt-BR."""
    if categoria is not None and categoria not in CATEGORIAS:
        raise ValueError(
            f"Categoria desconhecida: {categoria!r}. Use uma de: {', '.join(CATEGORIAS)}."
        )
    return categoria


def isento_por_categoria(categoria: str | None) -> bool:
    """Deriva isenção de IR exclusivamente pela categoria do produto."""
    return categoria in CATEGORIAS_ISENTAS


class Titulo(BaseModel):
    """Representação normalizada de um título de renda fixa.

    Modelo canônico de produto: `ProdutoRF` (`comparison/taxa_equivalente.py`)
    é a view de comparação, convertida via `de_titulo()` ou diretamente com
    `categoria`. O prazo de análise não vive aqui — é da análise, não do produto.
    """

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
    categoria: str | None = Field(
        default=None,
        description="uma de CATEGORIAS (ex.: 'debênture-incentivada') — "
        "consumida pelo IR por categoria",
    )

    @field_validator("categoria")
    @classmethod
    def _validar_categoria(cls, v: str | None) -> str | None:
        return validar_categoria(v)

    @model_validator(mode="after")
    def _derivar_isento_ir_do_modelo(self) -> Titulo:
        """`isento_ir` deriva de tipo+categoria; True explícito é preservado."""
        self.isento_ir = self.isento_ir or derivar_isento_ir(self.tipo, self.categoria)
        return self


def derivar_isento_ir(tipo: TipoTitulo, categoria: str | None) -> bool:
    """Deriva a isenção de IR a partir de tipo+categoria (regra testada).

    LCI e LCA são isentos para pessoa física; debênture é isenta apenas na
    modalidade incentivada (Lei 12.431/2011, categoria 'debênture-incentivada');
    as demais categorias (CDB, debênture-comum, fundo) e os títulos públicos
    são tributados.
    """
    if tipo == "LCI/LCA":
        return True
    return tipo == "Debênture" and isento_por_categoria(categoria)


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
