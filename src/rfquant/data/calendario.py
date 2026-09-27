"""Calendário de dias úteis do mercado brasileiro.

Fonte: ``pandas_market_calendars``,
calendário ``'B3'`` — feriados versionados no pacote, consulta offline.

Adaptação documentada (não silenciosa) sobre a fonte: o pacote marca os dias
de fim de ano 24/12 e 31/12 como feriado total (e fecha a sexta deslocada
quando 31/12 cai em sábado/domingo — regras ``AnoNovoSabado``/``AnoNovoDomingo``
do calendário BMF), mas na B3 real esses dias têm pregão de meio período e,
para o SFN — calendário usado no desconto dos títulos públicos —, são dias
úteis plenos. A regra de meio período vive em ``_dias_de_meio_periodo`` e é
validada a ±0 pela bateria de 10 casos oficiais de
``tests/test_data_calendario.py`` (DU publicados e DU derivados dos PUs
oficiais do Tesouro registrados em ``docs/dados.md``).
"""

from __future__ import annotations

from datetime import date

import pandas_market_calendars as mcal

_CALENDARIO = mcal.get_calendar("B3")


def _dias_de_meio_periodo(inicio: date, fim: date) -> set[date]:
    """Dias de fim de ano que o pacote fecha, mas que são dias úteis reais.

    24/12 e 31/12 (pregão de meio período na B3; dia útil pleno no SFN) e,
    quando 31/12 cai em sábado/domingo, a sexta anterior (30/12 ou 29/12) —
    o pacote a fecha, a B3 real mantém pregão pleno. Só devolve dias de
    semana no intervalo aberto ``(inicio, fim]``.
    """
    candidatos: list[date] = []
    for ano in range(inicio.year, fim.year + 1):
        candidatos += [date(ano, 12, 24), date(ano, 12, 31)]
        dia31 = date(ano, 12, 31).weekday()
        if dia31 == 5:  # 31/12 sábado: o pacote fecharia a sexta 30/12
            candidatos.append(date(ano, 12, 30))
        elif dia31 == 6:  # 31/12 domingo: o pacote fecharia a sexta 29/12
            candidatos.append(date(ano, 12, 29))
    return {d for d in candidatos if d.weekday() < 5 and inicio < d <= fim}


def dias_uteis(inicio: date, fim: date) -> int:
    """Conta os dias úteis reais (calendário B3/SFN) no intervalo ``(inicio, fim]``.

    Convenção do mercado: o dia inicial não conta; o final conta se for dia
    útil. Feriados do calendário ``'B3'`` do ``pandas_market_calendars``
    (offline), com os meio-períodos de fim de ano contados como úteis — ver
    docstring do módulo.

    Args:
        inicio: data inicial (exclusiva na contagem).
        fim: data final (inclusiva se for dia útil).

    Returns:
        Número de dias úteis entre ``inicio`` e ``fim``; 0 se ``fim <= inicio``.

    Examples:
        >>> dias_uteis(date(2026, 6, 30), date(2027, 1, 1))
        127
    """
    if fim <= inicio:
        return 0
    uteis = {ts.date() for ts in _CALENDARIO.valid_days(inicio, fim)}
    meios = _dias_de_meio_periodo(inicio, fim) - uteis
    return sum(1 for d in uteis if inicio < d <= fim) + len(meios)
