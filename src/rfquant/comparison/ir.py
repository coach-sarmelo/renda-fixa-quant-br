"""Cálculo de Imposto de Renda sobre renda fixa (tabela regressiva).

Regras vigentes (2026) para pessoa física:
    - Renda fixa tributada: CDB, Tesouro Direto, debêntures comuns, fundos DI
    - Renda fixa isenta: LCI, LCA, CRI, CRA, debêntures incentivadas (Lei 12.431)
    - Tabela regressiva (prazo em dias corridos):
        Até 180 dias ......... 22,5%
        181 a 360 dias ....... 20,0%
        361 a 720 dias ....... 17,5%
        Acima de 720 dias .... 15,0%
    - IOF regressivo apenas para resgates com prazo < 30 dias
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date

# ----------------------------------------------------------------------
# Tabela regressiva de IR
# ----------------------------------------------------------------------
FAIXAS_IR: list[tuple[int, float]] = [
    (180, 0.225),
    (360, 0.200),
    (720, 0.175),
    (10**9, 0.150),
]


def aliquota(prazo_dias: int) -> float:
    """Retorna a alíquota de IR (fração) para um prazo em dias corridos.

    Args:
        prazo_dias: Número de dias corridos entre aplicação e resgate.

    Returns:
        Alíquota de IR como fração (ex: 0.175 = 17,5%).
    """
    if prazo_dias <= 0:
        raise ValueError("Prazo deve ser positivo.")
    for limite, aliq in FAIXAS_IR:
        if prazo_dias <= limite:
            return aliq
    return FAIXAS_IR[-1][1]


def ir_devido(rendimento: float, prazo_dias: int, isento: bool = False) -> float:
    """Calcula o IR devido sobre o rendimento.

    Args:
        rendimento: Rendimento bruto em reais (já descontado o principal).
        prazo_dias: Dias corridos entre aplicação e resgate.
        isento: Se True, retorna 0 (LCI, LCA, CRI, CRA, incentivadas).

    Returns:
        Valor do IR devido em reais.
    """
    if rendimento <= 0:
        return 0.0
    if isento:
        return 0.0
    return rendimento * aliquota(prazo_dias)


def rendimento_liquido(
    rendimento: float,
    prazo_dias: int,
    isento: bool = False,
) -> float:
    """Retorna o rendimento líquido após IR."""
    return rendimento - ir_devido(rendimento, prazo_dias, isento)


# ----------------------------------------------------------------------
# IOF regressivo (resgates < 30 dias)
# ----------------------------------------------------------------------
IOF_TABELA: dict[int, float] = {
    1: 0.96,
    2: 0.93,
    3: 0.90,
    4: 0.86,
    5: 0.83,
    6: 0.80,
    7: 0.76,
    8: 0.73,
    9: 0.70,
    10: 0.66,
    11: 0.63,
    12: 0.60,
    13: 0.56,
    14: 0.53,
    15: 0.50,
    16: 0.46,
    17: 0.43,
    18: 0.40,
    19: 0.36,
    20: 0.33,
    21: 0.30,
    22: 0.26,
    23: 0.23,
    24: 0.20,
    25: 0.16,
    26: 0.13,
    27: 0.10,
    28: 0.06,
    29: 0.03,
}


def iof(rendimento: float, prazo_dias: int) -> float:
    """Calcula o IOF regressivo para prazos < 30 dias.

    Para prazos >= 30 dias, IOF é zero.
    """
    if prazo_dias < 1:
        return 0.0
    if prazo_dias >= 30:
        return 0.0
    return rendimento * IOF_TABELA.get(prazo_dias, 0.0)


# ----------------------------------------------------------------------
# API de alto nível
# ----------------------------------------------------------------------
@dataclass
class ResultadoLiquido:
    """Resultado completo de tributação de um produto."""

    rendimento_bruto: float
    iof: float
    ir: float
    rendimento_liquido: float
    aliquota_ir: float
    prazo_dias: int
    isento: bool

    @property
    def rentabilidade_liquida_pct(self) -> float:
        """Rendimento líquido / rendimento bruto (0..1)."""
        if self.rendimento_bruto <= 0:
            return 0.0
        return self.rendimento_liquido / self.rendimento_bruto


def calcular(
    rendimento_bruto: float,
    prazo_dias: int,
    isento: bool = False,
) -> ResultadoLiquido:
    """Calcula IOF, IR e rendimento líquido de forma encadeada.

    Ordem de tributação:
        1. IOF (se prazo < 30 dias)
        2. IR sobre o rendimento restante
    """
    iof_devido = iof(rendimento_bruto, prazo_dias)
    base_ir = rendimento_bruto - iof_devido
    ir_dev = ir_devido(base_ir, prazo_dias, isento=isento)
    liq = rendimento_bruto - iof_devido - ir_dev

    return ResultadoLiquido(
        rendimento_bruto=rendimento_bruto,
        iof=iof_devido,
        ir=ir_dev,
        rendimento_liquido=liq,
        aliquota_ir=aliquota(prazo_dias) if not isento else 0.0,
        prazo_dias=prazo_dias,
        isento=isento,
    )


def prazo_entre_datas(inicio: date, fim: date) -> int:
    """Dias corridos entre duas datas (equivalente ao prazo da RF)."""
    if fim < inicio:
        raise ValueError("Data final deve ser >= inicial.")
    return (fim - inicio).days


def aliquota_por_datas(inicio: date, fim: date, isento: bool = False) -> float:
    """Alíquota de IR dadas as datas de aplicação e resgate."""
    if isento:
        return 0.0
    return aliquota(prazo_entre_datas(inicio, fim))
