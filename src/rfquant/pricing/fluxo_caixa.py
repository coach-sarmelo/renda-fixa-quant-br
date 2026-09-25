"""Geração de fluxos de caixa de títulos de renda fixa."""

from __future__ import annotations

import calendar
from dataclasses import dataclass
from datetime import date


@dataclass(frozen=True)
class Fluxo:
    """Um fluxo de caixa futuro."""

    data: date
    valor: float
    tipo: str  # "cupom" | "principal"


def gerar_fluxos(
    data_compra: date,
    data_vencimento: date,
    valor_nominal: float = 1000.0,
    taxa_cupom_anual: float = 0.0,
    frequencia_cupom: int = 2,
) -> list[Fluxo]:
    """Gera a lista de fluxos de caixa de um título.

    Args:
        data_compra: Data de referência (hoje).
        data_vencimento: Data de vencimento do título.
        valor_nominal: Valor de face (padrão: 1000).
        taxa_cupom_anual: Cupom anual (ex: 0.06 = 6%). Zero = zero-cupom.
        frequencia_cupom: Número de cupons por ano — 1, 2, 3, 4, 6 ou 12
            (padrão: 2 = semestral).

    Returns:
        Lista de Fluxo em ordem cronológica, com o principal no último.

    Raises:
        ValueError: Se o vencimento não é posterior à compra, se a taxa é
            negativa ou se a frequência de cupom é inválida.
    """
    if data_vencimento <= data_compra:
        raise ValueError("Data de vencimento deve ser posterior à data de compra.")
    if taxa_cupom_anual < 0:
        raise ValueError("Taxa de cupom não pode ser negativa.")
    if frequencia_cupom not in (1, 2, 3, 4, 6, 12):
        raise ValueError("Frequência de cupom deve ser 1, 2, 3, 4, 6 ou 12.")

    fluxos: list[Fluxo] = []

    if taxa_cupom_anual == 0.0:
        fluxos.append(Fluxo(data=data_vencimento, valor=valor_nominal, tipo="principal"))
        return fluxos

    cupom_valor = valor_nominal * taxa_cupom_anual / frequencia_cupom
    meses_por_cupom = 12 // frequencia_cupom

    # Cupons ancorados no vencimento: mês alvo = mês do vencimento - k×meses,
    # dia = min(dia do vencimento, último dia do mês alvo). O dia do
    # vencimento nunca é substituído pelo dia de um clamp anterior.
    datas_cupom: list[date] = []
    k = 0
    while True:
        mes = data_vencimento.month - k * meses_por_cupom
        ano = data_vencimento.year + (mes - 1) // 12
        mes = (mes - 1) % 12 + 1
        dia = min(data_vencimento.day, calendar.monthrange(ano, mes)[1])
        data_cupom = date(ano, mes, dia)
        if data_cupom <= data_compra:
            break
        datas_cupom.append(data_cupom)
        k += 1

    datas_cupom = sorted(set(datas_cupom))

    for d in datas_cupom:
        if d == data_vencimento:
            fluxos.append(Fluxo(data=d, valor=cupom_valor + valor_nominal, tipo="principal"))
        else:
            fluxos.append(Fluxo(data=d, valor=cupom_valor, tipo="cupom"))

    return fluxos
