"""Testes do calendário de dias úteis real (10 casos oficiais).

Árbitro: evidência oficial publicada em ``docs/dados.md`` (excerto byte a byte
do CSV CKAN do Tesouro Transparente, capturado em 2026-09-20):

- 5 casos da data-base 30/06/2026 com ``du oficial*`` publicado
  (``docs/dados.md:72-78`` — coluna derivada da inversão do PU oficial);
- 5 casos da data-base 15/07/2024 (``docs/dados.md:50-56``) cujo DU **não** é
  publicado (só PU e taxa) — derivado no teste por
  ``du = 252·ln(1000/PU)/ln(1+y)`` (``docs/dados.md:80-81``).

Comparação a ±0 (nenhuma tolerância). Teste offline — nenhum fetch: os
números de referência são os já registrados em ``docs/dados.md``.
"""

from __future__ import annotations

import math
from datetime import date

import pytest

from rfquant.data import calendario
from rfquant.pricing import pu

# Data-bases dos 10 casos de evidência (docs/dados.md:50-56 e :72-78)
DATA_BASE_PUBLICADO = date(2026, 6, 30)
DATA_BASE_DERIVADO = date(2024, 7, 15)


# ----------------------------------------------------------------------
# 5 casos com DU oficial publicado (data-base 30/06/2026)
# ----------------------------------------------------------------------
@pytest.mark.parametrize(
    ("vencimento", "du_publicado"),
    [
        (date(2027, 1, 1), 127),
        (date(2028, 1, 1), 378),
        (date(2029, 1, 1), 626),
        (date(2031, 1, 1), 1127),
        (date(2032, 1, 1), 1379),
    ],
)
def test_du_publicado_bate_a_zero(vencimento: date, du_publicado: int) -> None:
    """DU oficial publicado (docs/dados.md:72-78) == calendário real, ±0."""
    assert calendario.dias_uteis(DATA_BASE_PUBLICADO, vencimento) == du_publicado


# ----------------------------------------------------------------------
# 5 casos da data-base 15/07/2024 com DU derivado do PU oficial
# ----------------------------------------------------------------------
@pytest.mark.parametrize(
    ("vencimento", "pu_oficial", "taxa_anual"),
    [
        (date(2025, 1, 1), 954.32, 0.1050),
        (date(2026, 1, 1), 856.68, 0.1111),
        (date(2027, 1, 1), 767.23, 0.1139),
        (date(2029, 1, 1), 611.11, 0.1174),
        (date(2031, 1, 1), 485.60, 0.1190),
    ],
)
def test_du_derivado_do_pu_oficial_bate_a_zero(
    vencimento: date, pu_oficial: float, taxa_anual: float
) -> None:
    """DU derivado do PU oficial == calendário real, ±0.

    Derivação (docs/dados.md:58-61 e :80-81): inverter
    PU = 1000/(1+y)^(du/252) dá du = 252·ln(1000/PU)/ln(1+y). Valores brutos
    medidos nesta fórmula — arredondam para o inteiro vizinho a ≤ 0,04 (o
    resíduo vem do PU oficial arredondado a 2 decimais):
    118,0082; 370,0228; 619,0204; 1118,0129; 1619,0382.
    """
    du_esperado = round(252 * math.log(1000 / pu_oficial) / math.log(1 + taxa_anual))
    assert calendario.dias_uteis(DATA_BASE_DERIVADO, vencimento) == du_esperado


# ----------------------------------------------------------------------
# Guardas de convenção (nada de volta à aproximação dias corridos × 252/365)
# ----------------------------------------------------------------------
def test_nao_e_mais_a_aproximacao_252_sobre_365() -> None:
    """Guarda anti-regressão: o DU real difere da aproximação dias corridos
    × 252/365.

    Caso 30/06/2026 → 01/01/2032: a aproximação daria round(2011 × 252/365)
    = 1388; o du real publicado é 1379 (docs/dados.md:72-78) — eram os 9 DU
    de desvio que a aproximação deixava passar. Se isto falhar, o núcleo
    voltou à aproximação.
    """
    du_aproximado = round((date(2032, 1, 1) - DATA_BASE_PUBLICADO).days * 252 / 365)
    assert calendario.dias_uteis(DATA_BASE_PUBLICADO, date(2032, 1, 1)) == 1379
    assert du_aproximado == 1388


def test_pu_dias_uteis_delega_no_calendario_real() -> None:
    """Assinatura pública de ``pu.dias_uteis`` preservada e delegando no
    calendário real (a aproximação dias corridos × 252/365 não é mais usada
    no núcleo)."""
    assert pu.dias_uteis(DATA_BASE_PUBLICADO, date(2032, 1, 1)) == 1379
    assert pu.dias_uteis(DATA_BASE_PUBLICADO, date(2032, 1, 1)) == calendario.dias_uteis(
        DATA_BASE_PUBLICADO, date(2032, 1, 1)
    )


def test_intervalo_vazio_ou_invertido_devolve_zero() -> None:
    """``fim <= inicio`` ⇒ 0 (comportamento público preservado da aproximação
    dias corridos × 252/365)."""
    d = date(2026, 6, 30)
    assert calendario.dias_uteis(d, d) == 0
    assert calendario.dias_uteis(date(2027, 1, 1), d) == 0


def test_meio_periodo_de_fim_de_ano_conta_como_dia_util() -> None:
    """24/12 e 31/12 (pregão de meio período) contam como dias úteis — a
    adaptação documentada sobre o pacote (docstring do módulo).

    (23/12/2026, 28/12/2026]: 24 (útil), 25 (Natal), 26-27 (fim de semana),
    28 (útil) ⇒ 2.
    """
    assert calendario.dias_uteis(date(2026, 12, 23), date(2026, 12, 28)) == 2


def test_sexta_deslocada_quando_31_12_e_domingo_conta_como_dia_util() -> None:
    """29/12/2028 (sexta antes do 31/12 em domingo) é dia útil pleno — o
    pacote fecharia (regra AnoNovoDomingo); a B3 real não (o caso publicado
    01/01/2029 = 626 DU valida a regra a ±0)."""
    assert calendario.dias_uteis(date(2028, 12, 28), date(2028, 12, 29)) == 1


def test_natal_e_confraternizacao_sao_feriado() -> None:
    """Feriados reais continuam fechados: 25/12 e 01/01 não contam.

    (24/12/2026, 29/12/2026]: 25/12 (Natal, feriado), 26-27 (fim de semana),
    28 (útil), 29 (útil) ⇒ 2.
    (30/12/2026, 04/01/2027]: 31/12 (útil), 01/01 (feriado), 02-03 (fim de
    semana), 04/01 (útil) ⇒ 2.
    """
    assert calendario.dias_uteis(date(2026, 12, 24), date(2026, 12, 29)) == 2
    assert calendario.dias_uteis(date(2026, 12, 30), date(2027, 1, 4)) == 2
