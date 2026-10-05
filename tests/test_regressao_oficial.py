"""Teste de regressão de PU contra valores OFICIAIS do Tesouro Direto.

A fixture (tests/fixtures/tesouro_regressao_oficial.csv) é um excerto
byte a byte do CSV oficial (CKAN/Tesouro Transparente) na data-base 15/07/2024:
5 LTNs. Com o calendário real de dias úteis TODOS os 5
batem a <= 1e-4 de pu.calcular vs 'PU Compra Manha' (erros medidos <= 1,7e-5;
sob a aproximação ``dias corridos × 252/365`` batiam 3 de 5 — limitação
medida em docs/dados.md). Aqui o núcleo de pricing é confrontado com a VERDADE
EXTERNA (PU publicado), nunca com valores derivados do próprio código.

Duration/YTM permanecem na consistência interna (cobertos por testes
próprios) - verdade externa de PU oficial não lhes é exigida.
"""

from __future__ import annotations

import re
from datetime import date, datetime
from pathlib import Path

import pandas as pd
import pytest

from rfquant.data.tesouro_oficial import TesouroOficialProvider
from rfquant.pricing import pu

CAMINHO_FIXTURE_REGRESSAO = Path(__file__).parent / "fixtures" / "tesouro_regressao_oficial.csv"

# Trio parametrizado (sob a aproximação dc × 252/365 batiam a 4,0e-4 / 4,3e-4 /
# 8,5e-4; com o calendário real, a <= 1e-5). Os LTNs de 2029 e 2031, que excediam
# 1e-3 POR CONSTRUÇÃO na aproximação (3,51e-3 / 4,88e-3 - limitação medida em
# docs/dados.md), passam a bater com o calendário real - caracterizado em
# test_ltns_2029_2031_batem_1e_4_apos_calendario_real (não mais "fora do AC":
# hoje os 5 de 5 estão dentro da tolerância).
TITULOS_NO_AC = ("01/01/2025", "01/01/2026", "01/01/2027")

# Tolerância relativa do PU contra o oficial: apertada ao erro medido — o
# pior dos 5 LTNs fecha a 1,7e-5 (01/01/2031), margem de ~6× sobre o 1e-4.
TOLERANCIA_PU = 1e-4


def _fixture_regressao() -> str:
    """Conteúdo CSV da fixture de regressão, sem as linhas de cabeçalho `#`."""
    linhas = CAMINHO_FIXTURE_REGRESSAO.read_text(encoding="utf-8").splitlines()
    return "\n".join(linha for linha in linhas if not linha.startswith("#"))


def _data_base_do_cabecalho() -> date:
    """Data-base registrada no cabeçalho de auditoria (linha `# data-base: dd/mm/aaaa ...`)."""
    padrao = re.compile(r"^# data-base:\s*(\d{2}/\d{2}/\d{4})")
    for linha in CAMINHO_FIXTURE_REGRESSAO.read_text(encoding="utf-8").splitlines():
        achou = padrao.match(linha)
        if achou:
            return datetime.strptime(achou.group(1), "%d/%m/%Y").date()
    raise AssertionError("cabeçalho de auditoria da fixture não registra a data-base")


def _linha_do_vencimento(vencimento: str) -> pd.Series:
    """Única linha da fixture com o vencimento pedido (dd/mm/aaaa)."""
    df = TesouroOficialProvider._parsear(_fixture_regressao())
    venc = pd.Timestamp(datetime.strptime(vencimento, "%d/%m/%Y"))
    sel = df[df["Data Vencimento"] == venc]
    assert len(sel) == 1, f"fixture deve ter exatamente 1 linha para {vencimento}"
    return sel.iloc[0]


# ----------------------------------------------------------------------
# Cabeçalho de auditoria (padrão de test_data_tesouro_oficial.py)
# ----------------------------------------------------------------------
def test_fixture_regressao_tem_cabecalho_de_auditoria() -> None:
    """Cabeçalho de auditoria: path, data-base, data de captura e versão no próprio arquivo."""
    linhas = CAMINHO_FIXTURE_REGRESSAO.read_text(encoding="utf-8").splitlines()
    cabecalho = [linha for linha in linhas if linha.startswith("#")]
    assert any("path: https://www.tesourotransparente.gov.br" in c for c in cabecalho)
    # Data-base 15/07/2024: a mais recente com >= 3 LTNs na tolerância.
    assert any("data-base: 15/07/2024" in c for c in cabecalho)
    assert any("data de captura:" in c for c in cabecalho)
    assert any("versão" in c for c in cabecalho)


def test_linhas_da_fixture_sao_da_data_base_registrada_no_cabecalho() -> None:
    """Honestidade da excisão: 5 linhas 'Tesouro Prefixado', todas na data-base do cabeçalho."""
    df = TesouroOficialProvider._parsear(_fixture_regressao())
    assert len(df) == 5  # "5 de 176.390", conforme o cabeçalho
    assert set(df["Tipo Titulo"]) == {"Tesouro Prefixado"}
    base = pd.Timestamp(_data_base_do_cabecalho())
    assert (df["Data Base"] == base).all()


# ----------------------------------------------------------------------
# PU do núcleo vs PU oficial publicado (verdade externa)
#
# Conta à mão por título (zero-cupom, VN 1000, compra na data-base
# 15/07/2024; du = dias úteis REAIS do calendário B3/SFN
# (rfquant.data.calendario, validado a ±0 pela bateria de calendário em
# tests/test_data_calendario.py):
#   01/01/2025: dc = 170; du real = 118;
#     PU = 1000/1,1050^(118/252) = 954,3231
#     vs oficial 954,32 -> erro 3,3e-6.
#   01/01/2026: dc = 535; du real = 370;
#     PU = 1000/1,1111^(370/252) = 856,6881
#     vs oficial 856,68 -> erro 9,5e-6.
#   01/01/2027: dc = 900; du real = 619;
#     PU = 1000/1,1139^(619/252) = 767,2367
#     vs oficial 767,23 -> erro 8,7e-6.
# (dc contado no calendário: 15/07/2024 -> 01/01/2025 = 170, +365 = 535,
# +365 = 900. Histórico da aproximação: du = round(dc × 252/365) dava
# 117/369/621 e erros 4,0e-4 / 4,3e-4 / 8,5e-4.)
# ----------------------------------------------------------------------
@pytest.mark.parametrize("vencimento", TITULOS_NO_AC)
def test_pu_do_nucleo_bate_com_o_oficial(vencimento: str) -> None:
    """pu.calcular vs 'PU Compra Manha' oficial, rel <= 1e-4.

    A taxa anual do núcleo é a fração decimal (o CSV traz % a.a.: 10,50 ->
    0,1050). O parser hoje devolve float64 (verificado; a conversão float()
    permanece - inócuo com float, robusto se o parsing voltar
    a Decimal).
    """
    linha = _linha_do_vencimento(vencimento)
    pu_oficial = float(linha["PU Compra Manha"])
    taxa_anual = float(linha["Taxa Compra Manha"]) / 100.0
    pu_teorico = pu.calcular(
        data_compra=_data_base_do_cabecalho(),
        data_vencimento=datetime.strptime(vencimento, "%d/%m/%Y").date(),
        taxa_anual=taxa_anual,
    )
    assert pu_teorico == pytest.approx(pu_oficial, rel=TOLERANCIA_PU)


def test_pelo_menos_3_ltns_batem_com_o_pu_oficial_a_1e_4() -> None:
    """>= 3 títulos da data-base batem com o oficial a 1e-4.

    Contrato (">= 3 títulos com PU oficial"): a data-base
    15/07/2024 foi escolhida por ter 3 de 5 LTNs na tolerância (critério
    original, sob a aproximação dc × 252/365; com o calendário real, os 5
    batem). A contagem impede que o trio parametrizado fique vacuamente
    verde (ex.: linhas removidas da fixture).
    """
    df = TesouroOficialProvider._parsear(_fixture_regressao())
    base = _data_base_do_cabecalho()
    dentro = 0
    for _, linha in df.iterrows():
        pu_oficial = float(linha["PU Compra Manha"])
        pu_teorico = pu.calcular(
            data_compra=base,
            data_vencimento=linha["Data Vencimento"].date(),
            taxa_anual=float(linha["Taxa Compra Manha"]) / 100.0,
        )
        if abs(pu_teorico - pu_oficial) / pu_oficial <= TOLERANCIA_PU:
            dentro += 1
    assert dentro >= 3


def test_ltns_2029_2031_batem_1e_4_apos_calendario_real() -> None:
    """Os LTNs que excediam 1e-3 na aproximação dc × 252/365 (3,51e-3 e
    4,88e-3 - o descolamento do du aproximado crescia com o prazo,
    docs/dados.md) batem com o oficial a <= 1e-4 com o calendário real.

    A queda do erro é o ganho esperado do calendário real - a raiz do
    desvio era o du aproximado. Medidos com o calendário real: 5,70e-6
    (01/01/2029, du real 1118) e 1,70e-5 (01/01/2031, du real 1619) - o
    pior caso da fixture, que define a tolerância (1e-4, ~6× de margem).
    Se isto falhar um dia, a fórmula de PU mudou de novo: regravar a fixture
    (mesmo padrão de cabeçalho).
    """
    base = _data_base_do_cabecalho()
    for vencimento in ("01/01/2029", "01/01/2031"):
        linha = _linha_do_vencimento(vencimento)
        pu_oficial = float(linha["PU Compra Manha"])
        pu_teorico = pu.calcular(
            data_compra=base,
            data_vencimento=datetime.strptime(vencimento, "%d/%m/%Y").date(),
            taxa_anual=float(linha["Taxa Compra Manha"]) / 100.0,
        )
        assert abs(pu_teorico - pu_oficial) / pu_oficial <= TOLERANCIA_PU, vencimento
