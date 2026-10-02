"""Cálculo de duration (Macaulay e modificada)."""

from __future__ import annotations

from datetime import date

from rfquant.pricing.fluxo_caixa import gerar_fluxos
from rfquant.pricing.pu import DU_ANO, _pu_de_fluxos, dias_uteis, fluxos_liquidados


def macaulay(
    data_compra: date,
    data_vencimento: date,
    taxa_anual: float,
    valor_nominal: float = 1000.0,
    taxa_cupom_anual: float = 0.0,
    frequencia_cupom: int = 2,
) -> float:
    """Duration de Macaulay em anos.

    Fórmula:
        D_mac = Σ [ t_i · FC_i / (1+y)^t_i ] / PU
    """
    fluxos = gerar_fluxos(
        data_compra=data_compra,
        data_vencimento=data_vencimento,
        valor_nominal=valor_nominal,
        taxa_cupom_anual=taxa_cupom_anual,
        frequencia_cupom=frequencia_cupom,
    )
    # Numerador e PU sobre o MESMO conjunto liquidado: um cupom pago na
    # janela D+1 sairia de um lado e ficaria no outro, com duration
    # inconsistente com o próprio PU.
    fluxos = fluxos_liquidados(fluxos, data_compra)
    pu = _pu_de_fluxos(fluxos, data_compra, taxa_anual)
    if pu <= 0:
        raise ValueError("PU inválido para cálculo de duration.")

    soma_ponderada = 0.0
    for f in fluxos:
        du = dias_uteis(data_compra, f.data)
        t_anos = du / DU_ANO
        vp = f.valor / (1 + taxa_anual) ** t_anos
        soma_ponderada += t_anos * vp

    return soma_ponderada / pu


def modificada(
    data_compra: date,
    data_vencimento: date,
    taxa_anual: float,
    valor_nominal: float = 1000.0,
    taxa_cupom_anual: float = 0.0,
    frequencia_cupom: int = 2,
) -> float:
    """Duration modificada.

    Fórmula:
        D_mod = D_mac / (1 + y)
    """
    d_mac = macaulay(
        data_compra=data_compra,
        data_vencimento=data_vencimento,
        taxa_anual=taxa_anual,
        valor_nominal=valor_nominal,
        taxa_cupom_anual=taxa_cupom_anual,
        frequencia_cupom=frequencia_cupom,
    )
    return d_mac / (1 + taxa_anual)
