"""Precificação de NTN-B (IPCA+ com juros semestrais) e NTN-B Principal.

O Tesouro IPCA+ é negociado por uma cotação em % do VNA (Valor Nominal
Atualizado pelo IPCA); o PU pago na liquidação é reconstruído a partir do
VNA do dia. Este módulo separa as duas camadas:

    - ``cotacao``: preço teórico em % do VNA — fluxos gerados sobre a
      base 100 (cupom composto STN: 6% a.a. → 2,956301 por semestre por
      100 de VNA), liquidação D+1 e desconto à taxa REAL;
    - ``calcular``: PU em R$ = VNA × cotação / 100.

A NTN-B Principal (sem cupons) é o caso ``taxa_cupom_anual=0``: a cotação
reduz à fórmula exata da STN, ``100 / (1 + r)^(du/252)``.

Reuso do núcleo: fluxos de ``fluxo_caixa.gerar_fluxos``, liquidação D+1 de
``pu.fluxos_liquidados`` e desconto de ``pu._pu_de_fluxos`` — o mesmo
privado que duration.py/risco.py/ytm.py já importam para não expor uma
segunda API pública de desconto.
"""

from __future__ import annotations

from datetime import date

from rfquant.pricing.fluxo_caixa import gerar_fluxos
from rfquant.pricing.pu import _pu_de_fluxos, fluxos_liquidados

# Fluxos sobre 100 de VNA: o PU dessa base JÁ é a cotação em % do VNA.
_BASE_COTACAO = 100.0


def cotacao(
    data_compra: date,
    data_vencimento: date,
    taxa_real: float,
    taxa_cupom_anual: float = 0.06,
    frequencia_cupom: int = 2,
) -> float:
    """Cotação teórica da NTN-B em % do VNA.

    Fluxos sobre a base 100, com a convenção de liquidação D+1 do oficial
    e desconto pela taxa REAL na base 252:

        cotação = Σ FC_t / (1 + r)^(du_t / 252),  com FC sobre base 100

    NTN-B Principal: ``taxa_cupom_anual=0`` reduz à fórmula exata da STN,
    ``cotação = 100 / (1 + r)^(du/252)``.

    Args:
        data_compra: Data de referência (hoje).
        data_vencimento: Vencimento (datas-base 15/02, 15/05, 15/08, 15/11).
        taxa_real: Taxa real anual (ex.: 0.062 = IPCA+ 6,2% a.a.).
        taxa_cupom_anual: Cupom real anual (padrão: 0.06 da NTN-B;
            0 = NTN-B Principal).
        frequencia_cupom: Cupons por ano (padrão: 2 = semestral).

    Returns:
        Cotação em % do VNA (ex.: 104.35 = 104,35% do VNA).

    Raises:
        ValueError: Se o vencimento não é posterior à compra, se a taxa
            real é <= -100% ou se cupom/frequência são inválidos —
            validações do núcleo reutilizado.
    """
    fluxos = gerar_fluxos(
        data_compra=data_compra,
        data_vencimento=data_vencimento,
        valor_nominal=_BASE_COTACAO,
        taxa_cupom_anual=taxa_cupom_anual,
        frequencia_cupom=frequencia_cupom,
    )
    return _pu_de_fluxos(fluxos_liquidados(fluxos, data_compra), data_compra, taxa_real)


def calcular(
    data_compra: date,
    data_vencimento: date,
    taxa_real: float,
    vna: float,
    taxa_cupom_anual: float = 0.06,
    frequencia_cupom: int = 2,
) -> float:
    """PU da NTN-B em reais: ``PU = VNA × cotação / 100``.

    Args:
        data_compra: Data de referência (hoje).
        data_vencimento: Vencimento (datas-base 15/02, 15/05, 15/08, 15/11).
        taxa_real: Taxa real anual (ex.: 0.062 = IPCA+ 6,2% a.a.).
        vna: Valor Nominal Atualizado do dia (em R$; ex.: 4500.00).
        taxa_cupom_anual: Cupom real anual (padrão: 0.06; 0 = Principal).
        frequencia_cupom: Cupons por ano (padrão: 2 = semestral).

    Returns:
        PU em R$.

    Raises:
        ValueError: Se ``vna <= 0``; as demais validações (datas, taxa,
            cupom, frequência) vêm do núcleo reutilizado por ``cotacao``.
    """
    if vna <= 0:
        raise ValueError("VNA deve ser positivo.")
    return (
        vna
        * cotacao(
            data_compra=data_compra,
            data_vencimento=data_vencimento,
            taxa_real=taxa_real,
            taxa_cupom_anual=taxa_cupom_anual,
            frequencia_cupom=frequencia_cupom,
        )
        / _BASE_COTACAO
    )
