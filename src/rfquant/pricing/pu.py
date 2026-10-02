"""Cálculo do Preço Unitário (PU) de um título."""

from __future__ import annotations

from datetime import date

from rfquant.data.calendario import dias_uteis as _dias_uteis_calendario
from rfquant.data.calendario import proximo_dia_util as _proximo_dia_util_calendario
from rfquant.pricing.fluxo_caixa import Fluxo, gerar_fluxos

# Número de dias úteis por ano (convenção do mercado brasileiro)
DU_ANO = 252


def dias_uteis(inicio: date, fim: date) -> int:
    """Conta os dias úteis reais do calendário B3/SFN no intervalo ``(inicio, fim]``.

    Delega ao calendário real (:mod:`rfquant.data.calendario`, via
    ``pandas_market_calendars``).

    Histórico: antes era a aproximação ``dias corridos × 252/365``, com
    erro relativo de PU medido de 5,11e-4 a 4,80e-3 contra o oficial
    (ver ``docs/dados.md``).
    """
    return _dias_uteis_calendario(inicio, fim)


def fluxos_liquidados(fluxos: list[Fluxo], data_ref: date) -> list[Fluxo]:
    """Fluxos que compõem o PU na convenção de liquidação D+1 do oficial.

    O PU publicado pelo Tesouro pressupõe liquidação no próximo dia útil:
    CUPONS pagos dentro da janela D+1 pertencem ao vendedor e saem do
    preço — mas o fluxo FINAL (vencimento) permanece embutido mesmo na
    véspera. Evidências da regressão NTN-F contra o oficial:

        - 30/06/2026 (cupom em 01/07): sem o filtro o núcleo errava
          4,97e-2; com a exclusão do cupom, a própria data-base fecha a
          ≤ 1e-5 e entrou na fixture.
        - 64 data-bases de sexta com cupom na segunda: só a regra D+1
          ÚTIL (não corrida) fecha — erros de 9e-6 a 9,7e-5 contra
          4,9e-2 a 5,5e-2 sem o filtro.
        - 30/06/2010 (venc em 01/07): o oficial mantém o resgate no PU
          (erro sem filtro 3,75e-4; excluí-lo daria erro 1,0) — por isso
          o fluxo final fica.
    """
    limite = _proximo_dia_util_calendario(data_ref)
    vencimento = max(f.data for f in fluxos)
    return [f for f in fluxos if f.data > limite or f.data == vencimento]


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
    return _pu_de_fluxos(fluxos_liquidados(fluxos, data_compra), data_compra, taxa_anual)


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
