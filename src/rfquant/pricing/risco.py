"""Métricas de risco de taxa de juros — DV01 e Convexidade.

Complementa duration.py com as métricas de segunda ordem e de
sensibilidade absoluta usadas em mesas institucionais de renda fixa.

Convenções:
    - Base 252 dias úteis (padrão ANBIMA/B3)
    - Capitalização composta anual
    - DV01 em R$ por 1 bp (0,01%)
"""

from __future__ import annotations

from datetime import date

from rfquant.pricing.pu import precificar


def dv01(
    data_compra: date,
    data_vencimento: date,
    taxa_anual: float,
    valor_nominal: float = 1000.0,
    taxa_cupom_anual: float = 0.0,
    frequencia_cupom: int = 2,
) -> float:
    """DV01 — Dollar Value of a Basis Point (R$/0,01%).

    Variação absoluta do PU para um choque de +1 bp na taxa:
        DV01 = |PU(y) - PU(y + 0,0001)|

    Calculado por diferença finita (re-precificação), não pela
    aproximação D_mod × PU × 0,0001 — captura não-linearidade.

    Returns:
        DV01 em R$ (sempre positivo).
    """
    return precificar(
        data_base=data_compra,
        data_vencimento=data_vencimento,
        taxa_anual=taxa_anual,
        valor_nominal=valor_nominal,
        taxa_cupom_anual=taxa_cupom_anual,
        frequencia_cupom=frequencia_cupom,
    ).dv01


def dv01_rapido(pu_valor: float, duration_mod: float) -> float:
    """DV01 pela aproximação linear (Duration Modificada).

    DV01 ≈ D_mod × PU × 0,0001

    Útil quando o PU e a Duration Modificada já estão calculados.
    Menos preciso que a re-precificação para taxas altas ou prazos longos.
    """
    return duration_mod * pu_valor * 0.0001


def convexidade(
    data_compra: date,
    data_vencimento: date,
    taxa_anual: float,
    valor_nominal: float = 1000.0,
    taxa_cupom_anual: float = 0.0,
    frequencia_cupom: int = 2,
) -> float:
    """Convexidade do título (segunda derivada normalizada do PU pela taxa).

    Fórmula (forma fechada, convenção brasileira base 252):

        C = (1 / PU) × Σ [ t_i × (t_i + 1) × FC_i / (1+y)^(t_i + 2) ]

    onde t_i = du_i / 252 (prazo em anos).

    Uso com Duration Modificada para aproximação de segunda ordem:

        ΔPU/PU ≈ -D_mod × Δy + ½ × C × (Δy)²

    Returns:
        Convexidade em anos² (o `t` da fórmula é medido em anos; a
        normalização pelo PU não torna o resultado adimensional).
    """
    return precificar(
        data_base=data_compra,
        data_vencimento=data_vencimento,
        taxa_anual=taxa_anual,
        valor_nominal=valor_nominal,
        taxa_cupom_anual=taxa_cupom_anual,
        frequencia_cupom=frequencia_cupom,
    ).convexidade


def variacao_pu(
    duration_mod: float,
    convex: float,
    delta_y: float,
) -> float:
    """Variação percentual estimada do PU (aproximação de 2ª ordem).

    ΔPU/PU ≈ -D_mod × Δy + ½ × C × (Δy)²

    Args:
        duration_mod: Duration Modificada.
        convex: Convexidade.
        delta_y: Variação de taxa (ex: 0.01 = +100 bps).

    Returns:
        Variação percentual estimada (ex: -0.05 = queda de 5%).
    """
    return -duration_mod * delta_y + 0.5 * convex * delta_y**2
