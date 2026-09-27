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


class Titulo(BaseModel):
    """Representação normalizada de um título de renda fixa.

    Modelo canônico de produto (ratificado em 2026-09-23): ProdutoRF
    (comparison/taxa_equivalente.py) e TituloRanking (comparison/ranking.py)
    são views derivadas, convertidas exclusivamente via de_titulo(). O prazo
    de análise não vive aqui — é da análise, não do produto.
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
        """Categoria fora da lista fechada ⇒ ValueError em pt-BR."""
        if v is not None and v not in CATEGORIAS:
            raise ValueError(f"Categoria desconhecida: {v!r}. Use uma de: {', '.join(CATEGORIAS)}.")
        return v

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
    return tipo == "Debênture" and categoria == "debênture-incentivada"


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
