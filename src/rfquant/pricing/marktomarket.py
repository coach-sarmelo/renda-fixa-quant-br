"""Cálculo de marcação a mercado de títulos de renda fixa."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date

from rfquant.data.calendario import dias_uteis
from rfquant.pricing import pu
from rfquant.pricing.curva_juros import ETTJ


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
    pu_compra: float | None = None,
    taxa_compra: float = 0.0,
    taxa_mercado: float | None = None,
    valor_nominal: float = 1000.0,
    taxa_cupom_anual: float = 0.0,
    frequencia_cupom: int = 2,
    *,
    ettj: ETTJ | None = None,
) -> ResultadoMarcacao:
    """Marcação a mercado exata, recalculando o PU com a taxa de mercado.

    Passos:
        1. Se `taxa_mercado` não for informada, interpola pela `ettj` no prazo
           útil remanescente (DU / 252).
        2. Se `pu_compra` não for informado, deriva-o em `data_compra` pela
           `taxa_compra`.
        3. Recalcula o PU teórico hoje e a duration modificada usando a taxa
           de mercado (`precificar`).
        4. Recalcula o PU na curva pela taxa de compra (`pu_curva`).
        5. Calcula a variação absoluta e percentual.

    Args:
        data_compra: Data em que o título foi adquirido.
        data_hoje: Data de referência para a marcação.
        data_vencimento: Data de vencimento do título.
        pu_compra: PU pago na compra (opcional; se None, derivado de `taxa_compra`).
        taxa_compra: Taxa contratada na compra.
        taxa_mercado: Taxa atual de mercado para o mesmo vencimento (opcional se `ettj` fornecida).
        valor_nominal: Valor de face.
        taxa_cupom_anual: Cupom anual do título.
        frequencia_cupom: Número de cupons por ano.
        ettj: Curva ETTJ opcional para interpolar `taxa_mercado` pelo prazo remanescente.

    Returns:
        ResultadoMarcacao com PU de compra, PU de mercado e variações.
    """
    if data_hoje < data_compra:
        raise ValueError("Data de hoje não pode ser anterior à data de compra.")
    if data_hoje >= data_vencimento:
        raise ValueError("Título já vencido ou vencendo hoje.")

    if taxa_mercado is not None and ettj is not None:
        raise ValueError("Informe apenas uma entre 'taxa_mercado' e 'ettj', não ambas.")
    if taxa_mercado is None:
        if ettj is None:
            raise ValueError("Informe `taxa_mercado` ou uma instância de `ettj` (ETTJ).")
        du_rem = dias_uteis(data_hoje, data_vencimento)
        taxa_mercado_efetiva = ettj.taxa(du_rem / pu.DU_ANO)
    else:
        taxa_mercado_efetiva = taxa_mercado

    pu_compra_efetivo = (
        pu_compra
        if pu_compra is not None
        else pu.calcular(
            data_compra=data_compra,
            data_vencimento=data_vencimento,
            taxa_anual=taxa_compra,
            valor_nominal=valor_nominal,
            taxa_cupom_anual=taxa_cupom_anual,
            frequencia_cupom=frequencia_cupom,
        )
    )

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

    # PU a mercado e métricas de risco em uma única passagem pelo cronograma
    avaliacao_mercado = pu.precificar(
        data_base=data_hoje,
        data_vencimento=data_vencimento,
        taxa_anual=taxa_mercado_efetiva,
        valor_nominal=valor_nominal,
        taxa_cupom_anual=taxa_cupom_anual,
        frequencia_cupom=frequencia_cupom,
    )
    pu_mercado = avaliacao_mercado.pu
    d_mod = avaliacao_mercado.duration_modificada

    variacao_abs = pu_mercado - pu_curva
    variacao_pct = variacao_abs / pu_curva if pu_curva > 0 else 0.0
    du_decorridos = dias_uteis(data_compra, data_hoje)

    return ResultadoMarcacao(
        pu_compra=pu_compra_efetivo,
        pu_mercado=pu_mercado,
        pu_curva=pu_curva,
        taxa_compra=taxa_compra,
        taxa_mercado=taxa_mercado_efetiva,
        duration_modificada=d_mod,
        variacao_absoluta=variacao_abs,
        variacao_percentual=variacao_pct,
        dias_uteis_decorridos=du_decorridos,
    )


def curva(
    data_hoje: date,
    titulos: list[dict],
    *,
    ettj: ETTJ | None = None,
) -> list[ResultadoMarcacao]:
    """Aplica marcação a mercado a uma lista de títulos.

    Cada título em `titulos` deve ser um dict com as chaves:
        data_compra, data_vencimento, taxa_compra, e opcionalmente
        pu_compra, taxa_mercado (se `ettj` for fornecida), valor_nominal,
        taxa_cupom_anual, frequencia_cupom.

    Returns:
        Lista de ResultadoMarcacao na mesma ordem.
    """
    resultados: list[ResultadoMarcacao] = []
    for t in titulos:
        pu_c = float(t["pu_compra"]) if "pu_compra" in t and t["pu_compra"] is not None else None
        taxa_m = (
            float(t["taxa_mercado"])
            if "taxa_mercado" in t and t["taxa_mercado"] is not None
            else None
        )
        resultados.append(
            exata(
                data_compra=t["data_compra"],
                data_hoje=data_hoje,
                data_vencimento=t["data_vencimento"],
                pu_compra=pu_c,
                taxa_compra=float(t["taxa_compra"]),
                taxa_mercado=taxa_m,
                valor_nominal=float(t.get("valor_nominal", 1000.0)),
                taxa_cupom_anual=float(t.get("taxa_cupom_anual", 0.0)),
                frequencia_cupom=int(t.get("frequencia_cupom", 2)),
                ettj=ettj,
            )
        )
    return resultados
