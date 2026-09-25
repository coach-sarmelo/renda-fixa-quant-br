"""Cálculo de marcação a mercado de títulos de renda fixa."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date

from rfquant.pricing import duration, pu


@dataclass(frozen=True)
class ResultadoMarcacao:
    """Resultado da marcação a mercado de um título.

    Attributes:
        pu_curva: PU re-precificado na data de hoje pela taxa de compra
            (fluxo remanescente descontado a `taxa_compra`). Não é carrego
            acumulado.
        variacao_absoluta: pu_mercado - pu_curva.
        variacao_percentual: variacao_absoluta / pu_curva.
    """

    pu_compra: float
    pu_mercado: float
    pu_curva: float
    taxa_compra: float
    taxa_mercado: float
    duration_modificada: float
    variacao_absoluta: float
    variacao_percentual: float
    dias_uteis_decorridos: int


def aproximada(
    pu_compra: float,
    taxa_compra: float,
    taxa_mercado: float,
    duration_mod: float,
) -> float:
    """Marcação a mercado via aproximação linear usando duration modificada.

    Fórmula:
        PU_mercado ≈ PU_compra × [1 - D_mod × (y_mercado - y_compra)]

    Válida para variações pequenas de taxa (< 1 p.p.).

    Atenção: a aproximação parte de `pu_compra` e ignora o carrego entre a
    compra e a data atual — portanto só representa o efeito de Δy no
    instante da compra. Para uma posição em carteira numa data `t`
    posterior à compra, use `exata`, que re-precifica o fluxo remanescente
    na data de referência.

    Args:
        pu_compra: PU na data da compra.
        taxa_compra: Taxa contratada na compra.
        taxa_mercado: Taxa atual de mercado.
        duration_mod: Duration modificada do título.

    Returns:
        PU estimado na data atual (aproximado).
    """
    delta_y = taxa_mercado - taxa_compra
    return pu_compra * (1 - duration_mod * delta_y)


def exata(
    data_compra: date,
    data_hoje: date,
    data_vencimento: date,
    pu_compra: float,
    taxa_compra: float,
    taxa_mercado: float,
    valor_nominal: float = 1000.0,
    taxa_cupom_anual: float = 0.0,
    frequencia_cupom: int = 2,
) -> ResultadoMarcacao:
    """Marcação a mercado exata, recalculando o PU com a taxa de mercado.

    Passos:
        1. Recalcula o PU teórico hoje usando a taxa de mercado (curva atual).
        2. Recalcula o PU na curva pela taxa de compra (pu_curva).
        3. Calcula a variação absoluta e percentual.

    Args:
        data_compra: Data em que o título foi adquirido.
        data_hoje: Data de referência para a marcação.
        data_vencimento: Data de vencimento do título.
        pu_compra: PU pago na compra.
        taxa_compra: Taxa contratada na compra.
        taxa_mercado: Taxa atual de mercado para o mesmo vencimento.
        valor_nominal: Valor de face.
        taxa_cupom_anual: Cupom anual do título.
        frequencia_cupom: Número de cupons por ano.

    Returns:
        ResultadoMarcacao com PU de compra, PU de mercado e variações.
    """
    if data_hoje < data_compra:
        raise ValueError("Data de hoje não pode ser anterior à data de compra.")
    if data_hoje >= data_vencimento:
        raise ValueError("Título já vencido ou vencendo hoje.")

    # PU "na curva": re-precificado hoje pela taxa de compra (não é
    # carrego acumulado; é o PU do fluxo remanescente descontado a taxa_compra)
    pu_curva = pu.calcular(
        data_compra=data_hoje,
        data_vencimento=data_vencimento,
        taxa_anual=taxa_compra,
        valor_nominal=valor_nominal,
        taxa_cupom_anual=taxa_cupom_anual,
        frequencia_cupom=frequencia_cupom,
    )

    # PU a mercado (descontado pela taxa de mercado hoje)
    pu_mercado = pu.calcular(
        data_compra=data_hoje,
        data_vencimento=data_vencimento,
        taxa_anual=taxa_mercado,
        valor_nominal=valor_nominal,
        taxa_cupom_anual=taxa_cupom_anual,
        frequencia_cupom=frequencia_cupom,
    )

    d_mod = duration.modificada(
        data_compra=data_hoje,
        data_vencimento=data_vencimento,
        taxa_anual=taxa_mercado,
        valor_nominal=valor_nominal,
        taxa_cupom_anual=taxa_cupom_anual,
        frequencia_cupom=frequencia_cupom,
    )

    variacao_abs = pu_mercado - pu_curva
    variacao_pct = variacao_abs / pu_curva if pu_curva > 0 else 0.0
    du_decorridos = pu.dias_uteis(data_compra, data_hoje)

    return ResultadoMarcacao(
        pu_compra=pu_compra,
        pu_mercado=pu_mercado,
        pu_curva=pu_curva,
        taxa_compra=taxa_compra,
        taxa_mercado=taxa_mercado,
        duration_modificada=d_mod,
        variacao_absoluta=variacao_abs,
        variacao_percentual=variacao_pct,
        dias_uteis_decorridos=du_decorridos,
    )


def curva(
    data_hoje: date,
    titulos: list[dict],
) -> list[ResultadoMarcacao]:
    """Aplica marcação a mercado a uma lista de títulos.

    Cada título em `titulos` deve ser um dict com as chaves:
        data_compra, data_vencimento, pu_compra, taxa_compra, taxa_mercado,
        valor_nominal (opcional), taxa_cupom_anual (opcional),
        frequencia_cupom (opcional).

    Returns:
        Lista de ResultadoMarcacao na mesma ordem.
    """
    resultados: list[ResultadoMarcacao] = []
    for t in titulos:
        resultados.append(
            exata(
                data_compra=t["data_compra"],
                data_hoje=data_hoje,
                data_vencimento=t["data_vencimento"],
                pu_compra=float(t["pu_compra"]),
                taxa_compra=float(t["taxa_compra"]),
                taxa_mercado=float(t["taxa_mercado"]),
                valor_nominal=float(t.get("valor_nominal", 1000.0)),
                taxa_cupom_anual=float(t.get("taxa_cupom_anual", 0.0)),
                frequencia_cupom=int(t.get("frequencia_cupom", 2)),
            )
        )
    return resultados
