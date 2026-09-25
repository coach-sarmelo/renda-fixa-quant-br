"""Cálculo do Preço Unitário (PU) de um título."""

from __future__ import annotations

from datetime import date

from rfquant.pricing.fluxo_caixa import Fluxo, gerar_fluxos

# Número de dias úteis por ano (convenção do mercado brasileiro)
DU_ANO = 252


def dias_uteis(inicio: date, fim: date) -> int:
    """Estima dias úteis entre duas datas.

    Nota: Aproximação simples (dias corridos × 252/365).
    Para produção, usar feriados da B3 via biblioteca `businessdays`.
    """
    if fim <= inicio:
        return 0
    dias_corridos = (fim - inicio).days
    return max(round(dias_corridos * DU_ANO / 365), 1)


def calcular(
    data_compra: date,
    data_vencimento: date,
    taxa_anual: float,
    valor_nominal: float = 1000.0,
    taxa_cupom_anual: float = 0.0,
    frequencia_cupom: int = 2,
) -> float:
    """Calcula o PU de um título descontando os fluxos pela taxa anual.

    Fórmula:
        PU = Σ FC_t / (1 + y)^(du_t / 252)
    """
    fluxos: list[Fluxo] = gerar_fluxos(
        data_compra=data_compra,
        data_vencimento=data_vencimento,
        valor_nominal=valor_nominal,
        taxa_cupom_anual=taxa_cupom_anual,
        frequencia_cupom=frequencia_cupom,
    )
    return _pu_de_fluxos(fluxos, data_compra, taxa_anual)


def _pu_de_fluxos(fluxos: list[Fluxo], data_ref: date, taxa_anual: float) -> float:
    """Desconta os fluxos a ``taxa_anual`` — validação central de taxa.

    Raises:
        ValueError: se ``taxa_anual <= -100%`` (fator de desconto nulo ou
            negativo).
    """
    if taxa_anual <= -1:
        raise ValueError("Taxa anual deve ser maior que -100%.")
    pu_total = 0.0
    for f in fluxos:
        du = dias_uteis(data_ref, f.data)
        fator = (1 + taxa_anual) ** (du / DU_ANO)
        pu_total += f.valor / fator
    return pu_total
