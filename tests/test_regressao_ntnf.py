"""Teste de regressão de PU de NTN-F contra valores OFICIAIS do Tesouro Direto.

A fixture (tests/fixtures/tesouro_regressao_ntnf.csv) é um excerto byte a
byte do CSV oficial (CKAN/Tesouro Transparente), capturado em 2026-10-01:
8 linhas da NTN-F 01/01/2027 — no CSV, 'Tesouro Prefixado com Juros
Semestrais' — em 8 datas-base de 2026, prazo curto (vencimento a 93 a 305
dias da data-base). É o primeiro título COM cupom confrontado com a verdade
externa: com o cupom COMPOSTO da convenção STN/ANBIMA (10% a.a. capitalizado
semestralmente) e o calendário real de dias úteis, TODAS as 8 batem a
<= 1,84e-5 de pu.calcular vs 'PU Compra Manha' (erros medidos 8,8e-8 a
1,84e-5). Com cupom LINEAR (10%/2 = 5% do nominal por semestre), as 8 dão
erro 1,14e-3 a 2,22e-3 — fora da tolerância: a regressão só fecha com a
convenção composta (controle negativo em
test_cupom_linear_nao_bate_com_o_oficial).

Limitação conhecida, medida e fora do escopo: na data-base 30/06/2026 (dia
útil imediatamente anterior ao cupom de 01/07/2026) o PU oficial EXCLUI o
cupom que vence no dia útil seguinte à data-base (regra D+1 da STN — o
comprador não o recebe) e o núcleo o inclui (erro medido 4,97e-2); essa
linha NÃO está na fixture.

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
# ordem original do CSV, data-base desc). Todas medidas com erro <= 1,84e-5.
DATAS_BASE_NO_AC = (
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


def _linha_da_data_base(data_base: str) -> pd.Series:
    """Única linha da fixture com a data-base pedida (dd/mm/aaaa)."""
    df = TesouroOficialProvider._parsear(_fixture_regressao())
    base = pd.Timestamp(datetime.strptime(data_base, "%d/%m/%Y"))
    sel = df[df["Data Base"] == base]
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
    # 8 datas-base de 2026 listadas no cabeçalho (verificação de conteúdo
    # completa em test_linhas_da_fixture_sao_do_escopo_registrado_no_cabecalho).
    assert any("data-base: 02/03/2026, 04/05/2026, 01/06/2026, 01/07/2026" in c for c in cabecalho)
    assert any("data de captura: 2026-10-01" in c for c in cabecalho)
    assert any("versão" in c for c in cabecalho)


def test_linhas_da_fixture_sao_do_escopo_registrado_no_cabecalho() -> None:
    """Honestidade da excisão: 8 linhas NTN-F, nas datas-base do cabeçalho, de prazo curto."""
    df = TesouroOficialProvider._parsear(_fixture_regressao())
    assert len(df) == 8  # "8 de 27.313", conforme o cabeçalho
    assert set(df["Tipo Titulo"]) == {"Tesouro Prefixado com Juros Semestrais"}
    assert set(df["Data Base"]) == {pd.Timestamp(d) for d in _datas_base_do_cabecalho()}
    # Uma só NTN-F em cena: 01/01/2027 (a única com prazo curto em 2026).
    assert set(df["Data Vencimento"]) == {pd.Timestamp("2027-01-01")}
    # Escopo: prazo curto — vencimento a <= ~2 anos (730 dias) da data-base
    # (medido: 93 a 305 dias).
    prazo_dias = (df["Data Vencimento"] - df["Data Base"]).dt.days
    assert (prazo_dias <= 730).all()


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
# ----------------------------------------------------------------------
@pytest.mark.parametrize("data_base", DATAS_BASE_NO_AC)
def test_pu_do_nucleo_bate_com_o_oficial(data_base: str) -> None:
    """pu.calcular vs 'PU Compra Manha' oficial, rel <= 1e-3.

    A taxa anual do núcleo é a fração decimal (o CSV traz % a.a.: 13,24 ->
    0,1324). O cupom é o composto de 10% a.a. com frequência 2 — a
    convenção STN/ANBIMA que o núcleo adotou; com a linear o PU NÃO bate
    (ver test_cupom_linear_nao_bate_com_o_oficial).
    """
    linha = _linha_da_data_base(data_base)
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


def test_todas_as_8_linhas_batem_com_o_pu_oficial_a_1e_3() -> None:
    """As 8 linhas da fixture batem com o oficial a 1e-3.

    Espelho do contrato da regressão LTN (">= 3 títulos"): lá a contagem
    impedia o trio parametrizado de ficar vacuamente verde; aqui a medição
    fechou com TODAS as 8 na tolerância (erros <= 1,84e-5), então a
    contagem exige 8 — mesma defesa contra linhas removidas da fixture.
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
    assert dentro == len(df) == 8


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
