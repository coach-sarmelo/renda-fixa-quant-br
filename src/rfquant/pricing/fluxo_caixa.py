"""Geração de fluxos de caixa de títulos de renda fixa."""

from __future__ import annotations

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
        frequencia_cupom: Número de cupons por ano (padrão: 2 = semestral).

    Returns:
        Lista de Fluxo em ordem cronológica, com o principal no último.
    """
    if data_vencimento <= data_compra:
        raise ValueError("Data de vencimento deve ser posterior à data de compra.")
    if taxa_cupom_anual < 0:
        raise ValueError("Taxa de cupom não pode ser negativa.")

    fluxos: list[Fluxo] = []

    if taxa_cupom_anual == 0.0:
        fluxos.append(Fluxo(data=data_vencimento, valor=valor_nominal, tipo="principal"))
        return fluxos

    cupom_valor = valor_nominal * taxa_cupom_anual / frequencia_cupom
    meses_por_cupom = 12 // frequencia_cupom

    atual = data_vencimento
    datas_cupom: list[date] = []
    while atual > data_compra:
        datas_cupom.append(atual)
        ano = atual.year
        mes = atual.month - meses_por_cupom
        while mes <= 0:
            mes += 12
            ano -= 1
        try:
            atual = atual.replace(year=ano, month=mes)
        except ValueError:
            atual = atual.replace(year=ano, month=mes, day=28)

    datas_cupom = sorted(set(datas_cupom))

    for d in datas_cupom:
        if d == data_vencimento:
            fluxos.append(Fluxo(data=d, valor=cupom_valor + valor_nominal, tipo="principal"))
        else:
            fluxos.append(Fluxo(data=d, valor=cupom_valor, tipo="cupom"))

    return fluxos
