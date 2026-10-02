"""Teste de regressão de PU de NTN-F contra valores OFICIAIS do Tesouro Direto.

A fixture (tests/fixtures/tesouro_regressao_ntnf.csv) é um excerto byte a
byte do CSV oficial (CKAN/Tesouro Transparente), capturado em 2026-10-01:
8 linhas da NTN-F 01/01/2027 — no CSV, 'Tesouro Prefixado com Juros
Semestrais' — em 9 datas-base de 2026, prazo curto (vencimento a 93 a 305
dias da data-base). É o primeiro título COM cupom confrontado com a verdade
externa: com o cupom COMPOSTO da convenção STN/ANBIMA (10% a.a. capitalizado
semestralmente), o calendário real de dias úteis e a liquidação D+1
(pu.fluxos_liquidados), TODAS batem a <= 1e-3 de pu.calcular vs 'PU Compra
Manha' (as 8 de prazo curto: erros 8,8e-8 a 1,84e-5). Com cupom LINEAR
(10%/2 = 5% do nominal por semestre), as de prazo curto dão erro 1,14e-3 a
2,22e-3 — fora da tolerância: a regressão só fecha com a convenção composta
(controle negativo em test_cupom_linear_nao_bate_com_o_oficial).

As linhas de 30/06/2026 cobrem a regra de liquidação D+1: o oficial EXCLUI o
cupom pago no dia útil seguinte à data-base (01/07/2026) e MANTÉM o fluxo de
vencimento — sem o filtro o erro era 4,97e-2 (venc 2037); com
pu.fluxos_liquidados ambas as linhas fecham. Validação integral (27.275
linhas NTN-F do CSV oficial, 2004-2026): com a regra, os 162 casos em que
ela morde melhoram ~10× (p.ex. 6,54e-3 vs 6,87e-2) e os 64 casos de
data-base na sexta com cupom na segunda provam que a regra é D+1 ÚTIL, não
corrida.

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
from rfquant.pricing.fluxo_caixa import gerar_fluxos

CAMINHO_FIXTURE_REGRESSAO_NTNF = Path(__file__).parent / "fixtures" / "tesouro_regressao_ntnf.csv"

# Datas-base parametrizadas (em ordem crescente; a fixture as carrega na
# ordem original do CSV, data-base desc). Medidas com o composto + calendário
# real + liquidação D+1: as 8 de prazo curto a <= 1,84e-5; as 2 de 30/06/2026
# (caso D+1) a 3,24e-6 (venc 2027) e 9,39e-5 (venc 2037).
DATAS_BASE_NO_AC = (
    "30/06/2026",
    "02/03/2026",
    "04/05/2026",
    "01/06/2026",
    "01/07/2026",
    "03/08/2026",
    "24/09/2026",
    "28/09/2026",
    "30/09/2026",
)

# Datas-base do controle negativo do cupom linear: uma com dois fluxos
# (02/03/2026 — cupom de 01/07/2026 ainda a pagar) e uma com um só
# (30/09/2026 — só principal+cupom no vencimento).
DATAS_BASE_CONTRAFACTUAL_LINEAR = ("02/03/2026", "30/09/2026")

# Tolerância relativa do PU contra o oficial.
TOLERANCIA_PU = 1e-3


def _fixture_regressao() -> str:
    """Conteúdo CSV da fixture de regressão, sem as linhas de cabeçalho `#`."""
    linhas = CAMINHO_FIXTURE_REGRESSAO_NTNF.read_text(encoding="utf-8").splitlines()
    return "\n".join(linha for linha in linhas if not linha.startswith("#"))


def _datas_base_do_cabecalho() -> list[date]:
    """Datas-base registradas no cabeçalho de auditoria (linha `# data-base: dd/mm/aaaa, ...`)."""
    padrao = re.compile(r"^# data-base:\s*(\d{2}/\d{2}/\d{4}(?:, \d{2}/\d{2}/\d{4})*)")
    for linha in CAMINHO_FIXTURE_REGRESSAO_NTNF.read_text(encoding="utf-8").splitlines():
        achou = padrao.match(linha)
        if achou:
            return [datetime.strptime(d, "%d/%m/%Y").date() for d in achou.group(1).split(", ")]
    raise AssertionError("cabeçalho de auditoria da fixture não registra as datas-base")


def _linhas_da_data_base(data_base: str) -> pd.DataFrame:
    """Linhas da fixture com a data-base pedida (dd/mm/aaaa) — 1 nas datas
    de prazo curto; 2 em 30/06/2026 (caso de liquidação D+1, um por venc)."""
    df = TesouroOficialProvider._parsear(_fixture_regressao())
    base = pd.Timestamp(datetime.strptime(data_base, "%d/%m/%Y"))
    sel = df[df["Data Base"] == base]
    assert len(sel) >= 1, f"fixture não tem linhas para a data-base {data_base}"
    return sel


def _linha_da_data_base(data_base: str) -> pd.Series:
    """Única linha da fixture com a data-base pedida (dd/mm/aaaa)."""
    sel = _linhas_da_data_base(data_base)
    assert len(sel) == 1, f"fixture deve ter exatamente 1 linha para a data-base {data_base}"
    return sel.iloc[0]


# ----------------------------------------------------------------------
# Cabeçalho de auditoria (padrão de test_regressao_oficial.py)
# ----------------------------------------------------------------------
def test_fixture_regressao_ntnf_tem_cabecalho_de_auditoria() -> None:
    """Cabeçalho de auditoria: path, datas-base, data de captura e versão no próprio arquivo."""
    linhas = CAMINHO_FIXTURE_REGRESSAO_NTNF.read_text(encoding="utf-8").splitlines()
    cabecalho = [linha for linha in linhas if linha.startswith("#")]
    assert any("path: https://www.tesourotransparente.gov.br" in c for c in cabecalho)
    # 9 datas-base de 2026 listadas no cabeçalho (verificação de conteúdo
    # completa em test_linhas_da_fixture_sao_do_escopo_registrado_no_cabecalho).
    assert any("data-base: 30/06/2026, 02/03/2026, 04/05/2026, 01/06/2026" in c for c in cabecalho)
    assert any("data de captura: 2026-10-01" in c for c in cabecalho)
    assert any("versão" in c for c in cabecalho)


def test_linhas_da_fixture_sao_do_escopo_registrado_no_cabecalho() -> None:
    """Honestidade da excisão: 10 linhas NTN-F nas datas-base do cabeçalho —
    9 da 01/01/2027 (8 de prazo curto + 1 do caso D+1) e 1 da 01/01/2037
    (caso D+1); as 2 de 30/06/2026 cobrem a liquidação D+1."""
    df = TesouroOficialProvider._parsear(_fixture_regressao())
    assert len(df) == 10  # "10 de 27.313", conforme o cabeçalho
    assert set(df["Tipo Titulo"]) == {"Tesouro Prefixado com Juros Semestrais"}
    assert set(df["Data Base"]) == {pd.Timestamp(d) for d in _datas_base_do_cabecalho()}
    # Duas NTN-Fs em cena: 01/01/2027 (prazo curto) e 01/01/2037 (caso D+1).
    assert set(df["Data Vencimento"]) == {pd.Timestamp("2027-01-01"), pd.Timestamp("2037-01-01")}
    # Prazo curto: as 9 linhas da 2027 com vencimento a <= ~2 anos (730
    # dias) da data-base (medido: 93 a 305 dias nas 8 originais; 185 na do
    # caso D+1).
    curtas = df[df["Data Vencimento"] == pd.Timestamp("2027-01-01")]
    assert len(curtas) == 9
    prazo_dias = (curtas["Data Vencimento"] - curtas["Data Base"]).dt.days
    assert (prazo_dias <= 730).all()
    # Caso D+1: as 2 linhas de 30/06/2026 (cupom de 01/07 na janela de
    # liquidação — uma por vencimento).
    d1 = df[df["Data Base"] == pd.Timestamp("2026-06-30")]
    assert len(d1) == 2
    assert set(d1["Data Vencimento"]) == {pd.Timestamp("2027-01-01"), pd.Timestamp("2037-01-01")}


# ----------------------------------------------------------------------
# PU do núcleo vs PU oficial publicado (verdade externa)
#
# A NTN-F paga cupom composto: 1000 × ((1,10)^(1/2) - 1) = 48,808848 por
# semestre (convenção STN/ANBIMA). O oficial 'PU Compra Manha' é por 1000
# de face; du = dias úteis REAIS do calendário B3/SFN
# (rfquant.data.calendario, validado a ±0 pela bateria em
# tests/test_data_calendario.py). Erros medidos por data-base (compostos):
#   02/03/2026: 1,57e-5 (dois fluxos: cupom 01/07/2026 + principal 01/01/2027)
#   04/05/2026: 1,70e-5 | 01/06/2026: 1,84e-5 | 01/07/2026: 2,77e-6
#   03/08/2026: 6,82e-7 | 24/09/2026: 6,62e-6 | 28/09/2026: 8,81e-8
#   30/09/2026: 9,57e-8
#   30/06/2026: 3,24e-6 (venc 2027) e 9,39e-5 (venc 2037) — liquidação D+1:
#   o cupom de 01/07/2026 sai do PU (sem o filtro: 4,97e-1 no 2037)
# ----------------------------------------------------------------------
@pytest.mark.parametrize("data_base", DATAS_BASE_NO_AC)
def test_pu_do_nucleo_bate_com_o_oficial(data_base: str) -> None:
    """pu.calcular vs 'PU Compra Manha' oficial, rel <= 1e-3.

    A taxa anual do núcleo é a fração decimal (o CSV traz % a.a.: 13,24 ->
    0,1324). O cupom é o composto de 10% a.a. com frequência 2 — a
    convenção STN/ANBIMA que o núcleo adotou; com a linear o PU NÃO bate
    (ver test_cupom_linear_nao_bate_com_o_oficial).
    """
    for _, linha in _linhas_da_data_base(data_base).iterrows():
        pu_oficial = float(linha["PU Compra Manha"])
        taxa_anual = float(linha["Taxa Compra Manha"]) / 100.0
        pu_teorico = pu.calcular(
            data_compra=datetime.strptime(data_base, "%d/%m/%Y").date(),
            data_vencimento=linha["Data Vencimento"].date(),
            taxa_anual=taxa_anual,
            valor_nominal=1000.0,
            taxa_cupom_anual=0.10,
            frequencia_cupom=2,
        )
        assert pu_teorico == pytest.approx(pu_oficial, rel=TOLERANCIA_PU)


def test_todas_as_linhas_batem_com_o_pu_oficial_a_1e_3() -> None:
    """As 10 linhas da fixture batem com o oficial a 1e-3.

    Espelho do contrato da regressão LTN (">= 3 títulos"): lá a contagem
    impedia o trio parametrizado de ficar vacuamente verde; aqui a medição
    fechou com TODAS as 10 na tolerância (as 8 de prazo curto a <= 1,84e-5;
    as 2 de 30/06/2026, com a liquidação D+1, a 3,24e-6 e 9,39e-5), então a
    contagem exige 10 — mesma defesa contra linhas removidas da fixture.
    """
    df = TesouroOficialProvider._parsear(_fixture_regressao())
    dentro = 0
    for _, linha in df.iterrows():
        pu_oficial = float(linha["PU Compra Manha"])
        pu_teorico = pu.calcular(
            data_compra=linha["Data Base"].date(),
            data_vencimento=linha["Data Vencimento"].date(),
            taxa_anual=float(linha["Taxa Compra Manha"]) / 100.0,
            valor_nominal=1000.0,
            taxa_cupom_anual=0.10,
            frequencia_cupom=2,
        )
        if abs(pu_teorico - pu_oficial) / pu_oficial <= TOLERANCIA_PU:
            dentro += 1
    assert dentro == len(df) == 10


# ----------------------------------------------------------------------
# Controle negativo: a fixture discrimina as duas convenções de cupom
# ----------------------------------------------------------------------
def _pu_de_cupom_linear(data_base: date, data_vencimento: date, taxa_anual: float) -> float:
    """PU com cupom LINEAR de 10% a.a. (1000 × 0,10/2 = 50,00 por semestre),
    nas MESMAS datas de fluxo do núcleo — o contrafactual da convenção
    composta. Usa apenas funções públicas do núcleo (gerar_fluxos para as
    datas, pu.dias_uteis para o du) com o valor do cupom trocado."""
    fluxos = gerar_fluxos(
        data_compra=data_base,
        data_vencimento=data_vencimento,
        valor_nominal=1000.0,
        taxa_cupom_anual=0.10,
        frequencia_cupom=2,
    )
    cupom_linear = 1000.0 * 0.10 / 2
    pu_total = 0.0
    for f in fluxos:
        du = pu.dias_uteis(data_base, f.data)
        valor = (1000.0 + cupom_linear) if f.tipo == "principal" else cupom_linear
        pu_total += valor / (1 + taxa_anual) ** (du / 252)
    return pu_total


@pytest.mark.parametrize("data_base", DATAS_BASE_CONTRAFACTUAL_LINEAR)
def test_cupom_linear_nao_bate_com_o_oficial(data_base: str) -> None:
    """Com cupom LINEAR o PU NÃO bate a 1e-3 — e por isso a fixture acima só
    fecha com o cupom COMPOSTO da convenção STN/ANBIMA.

    Medido: 2,22e-3 (02/03/2026, dois fluxos) e 1,14e-3 (30/09/2026, um
    fluxo) — ambos fora da tolerância, contra <= 1,84e-5 do composto nas
    mesmas linhas. Se um dia isto falhar, ou a fixture mudou (regravar com
    o mesmo padrão de cabeçalho) ou a fórmula de PU voltou atrás.
    """
    linha = _linha_da_data_base(data_base)
    pu_oficial = float(linha["PU Compra Manha"])
    pu_linear = _pu_de_cupom_linear(
        data_base=datetime.strptime(data_base, "%d/%m/%Y").date(),
        data_vencimento=linha["Data Vencimento"].date(),
        taxa_anual=float(linha["Taxa Compra Manha"]) / 100.0,
    )
    assert abs(pu_linear - pu_oficial) / pu_oficial > TOLERANCIA_PU
