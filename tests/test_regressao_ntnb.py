"""Teste de regressão de NTN-B por RAZÃO DE PUs contra valores OFICIAIS do Tesouro Direto.

A fixture (tests/fixtures/tesouro_regressao_ntnb.csv) é um excerto byte a
byte do CSV oficial (CKAN/Tesouro Transparente), capturado em 2026-10-06:
16 linhas — 12 da NTN-B ('Tesouro IPCA+ com Juros Semestrais') e 4 da NTN-B
Principal ('Tesouro IPCA+') — em 8 datas-base de 2024 a 2026, uma dupla por
data-base, com prazos de 46 dias corridos (B 15/08/2026 na base 30/06/2026)
a 12.942 (B 15/08/2060 na base 10/03/2025). É o primeiro título IPCA+
confrontado com a verdade externa.

Por que a RAZÃO e não o PU absoluto: o CSV NÃO publica o VNA da NTN-B — a
coluna 'PU Base Manha' é IGUAL a 'PU Venda Manha' em todas as linhas (16/16
da fixture; 10.128/10.128 do escopo 2024-2026 medido sobre o CSV completo),
ou seja, é o PU do lado da venda, não um valor nominal atualizado. Sem o
VNA, PU_teorico = ntnb.calcular(..., vna='PU Base Manha') NÃO replica o
oficial: erro medido de 8,9e-3 a 8,2e-1 nas 16 linhas (mediana 1,148e-1 e
0 de 691 datas-base a <= 1e-3 no escopo) — controle negativo
test_pu_base_como_vna_nao_bate_com_o_pu_compra. O que a fixture permite
calibrar com verdade externa é a RAZÃO entre os dois lados do spread:
|PU_Compra/PU_Venda - cot_compra/cot_venda| / (PU_Compra/PU_Venda), com as
cotações teóricas sobre base 100 (cupom COMPOSTO STN de 6% a.a. → 2,956301
por semestre por 100 de VNA; Principal sem cupom), desconto real
(1+r)^(du/252) com du do calendário REAL de dias úteis e a regra de
liquidação D+1 (pu.fluxos_liquidados) SÓ no numerador: cot_compra com o
filtro, cot_venda SEM. Em dia normal o filtro não morde e os dois lados
coincidem; nas 4 datas-base de véspera útil de cupom (14/08 de 2024 e 2025,
13/02/2026 e 14/05/2026) o oficial publica PU Compra SEM o cupom da janela
D+1 e PU Venda COM ele — visível nos próprios dados (PU Venda > PU Compra
apesar da taxa de venda MAIOR; ex. 13/02/2026 B 15/08/2026: PU Compra
4.518,23 < PU Venda 4.646,84). Com o filtro também no denominador, ou sem
ele nos dois lados, a razão dessas datas daria 2,9e-2 a 3,3e-2 — controle
negativo test_contrafactuais_de_filtro_na_janela_d1_nao_batem.

Erros medidos com o composto + calendário real + D+1 só no numerador:
3,447e-4 a 1,082e-3 nas 16 linhas (15 de 16 a <= 1e-3; a exceção é a sexta
13/02/2026, cupom pagando na segunda útil — o dia do viés de sexta). A
tolerância é 5e-3, ~4,6× o pior caso, e não 1e-4 nem 1e-3: o resíduo da
validação integral do escopo 2024-2026 (10.078 linhas sem cupom na janela
D+1: mediana 4,165e-4, p95 8,343e-4, máximo 2,595e-3) tem viés
multiplicativo de +4,2e-4 de mediana (99,7% das linhas positivas; +6,3e-4
nas sextas) consistente com o PU Venda do oficial referenciado à data de
LIQUIDAÇÃO — descontar o lado da venda do próximo dia útil reduziria o
viés a +1,3e-4. O viés é do oficial, não do núcleo: absorvido na
tolerância, não corrigido na fórmula.

Sobre o cupom LINEAR (6%/2 = 3,0 por semestre por 100 de VNA): na NTN-F ele
discrimina o PU absoluto (1,14e-3 a 2,22e-3 contra a tolerância 5e-4); na
RAZÃO de PUs NÃO discrimina — medido 3,467e-4 a 1,501e-3 nas 16 linhas,
dentro da tolerância de 5e-3. A razão é quase invariante a um shift
multiplicativo no cupom: numerador e denominador sobem juntos; o efeito
visível (+4,2e-4 na linha mais sensível, a D+1 curta de 13/02/2026) vem só
do cupom que o filtro D+1 exclui do numerador. Por isso os controles
negativos desta regressão são os que a razão de fato discrimina: a janela
D+1 (2,9e-2 a 3,3e-2, > 5× a tolerância) e o PU Base como VNA (8,9e-3 a
8,2e-1 nas 16/16 linhas).

Cotação, duration e DV01 em nível absoluto (PU = VNA × cotação/100)
permanecem na consistência interna (cobertos por test_pricing_ntnb.py) — a
verdade externa de PU oficial não lhes é exigida sem o VNA do dia.
"""

from __future__ import annotations

import re
from datetime import date, datetime
from pathlib import Path

import pandas as pd
import pytest

from rfquant.data.calendario import proximo_dia_util
from rfquant.data.tesouro_oficial import TesouroOficialProvider
from rfquant.pricing import ntnb, pu
from rfquant.pricing.fluxo_caixa import gerar_fluxos

CAMINHO_FIXTURE_REGRESSAO_NTNB = Path(__file__).parent / "fixtures" / "tesouro_regressao_ntnb.csv"

# Os dois tipos IPCA+ do CSV oficial (a fixture traz 12 linhas do primeiro
# e 4 do segundo — verificado no teste de escopo).
TIPO_NTNB = "Tesouro IPCA+ com Juros Semestrais"
TIPO_NTNB_PRINCIPAL = "Tesouro IPCA+"

# Datas-base parametrizadas (em ordem cronológica; a fixture as carrega na
# ordem original do CSV, data-base desc). Erros medidos com o composto +
# calendário real + D+1 só no numerador: 3,447e-4 a 1,082e-3 — 15 de 16
# linhas a <= 1e-3, a exceção é a sexta 13/02/2026 (1,082e-3, cupom pagando
# na segunda útil).
DATAS_BASE_REGRESSAO = (
    "15/02/2024",
    "14/08/2024",
    "10/03/2025",
    "14/08/2025",
    "13/02/2026",
    "14/05/2026",
    "30/06/2026",
    "05/10/2026",
)

# Datas-base de véspera ÚTIL de cupom — 14/08 de 2024 e 2025 (cupom no dia
# seguinte), 13/02/2026 (cupom de domingo 15/02, pagamento na segunda
# 16/02) e 14/05/2026. Nas 4 o filtro D+1 morde em exatamente 1 linha (a
# NTN-B da dupla com cupom na janela; a Principal não tem cupom).
DATAS_BASE_VESPERA_CUPOM = ("14/08/2024", "14/08/2025", "13/02/2026", "14/05/2026")

# Tolerância relativa da razão contra o oficial: 5e-3 ~ 4,6× o pior caso
# medido na fixture (1,082e-3). Não é 1e-4 nem 1e-3 porque o resíduo do
# escopo integral tem viés multiplicativo de +4,2e-4 de mediana (o PU Venda
# do oficial é referenciado à liquidação) e máximo 2,595e-3 — o viés é do
# oficial, absorvido na tolerância, não corrigido na fórmula (ver docstring
# do módulo).
TOLERANCIA_RAZAO = 5e-3


def _fixture_regressao() -> str:
    """Conteúdo CSV da fixture de regressão, sem as linhas de cabeçalho `#`."""
    linhas = CAMINHO_FIXTURE_REGRESSAO_NTNB.read_text(encoding="utf-8").splitlines()
    return "\n".join(linha for linha in linhas if not linha.startswith("#"))


def _datas_base_do_cabecalho() -> list[date]:
    """Datas-base registradas no cabeçalho de auditoria (linha `# data-base: dd/mm/aaaa, ...`)."""
    padrao = re.compile(r"^# data-base:\s*(\d{2}/\d{2}/\d{4}(?:, \d{2}/\d{2}/\d{4})*)")
    for linha in CAMINHO_FIXTURE_REGRESSAO_NTNB.read_text(encoding="utf-8").splitlines():
        achou = padrao.match(linha)
        if achou:
            return [datetime.strptime(d, "%d/%m/%Y").date() for d in achou.group(1).split(", ")]
    raise AssertionError("cabeçalho de auditoria da fixture não registra as datas-base")


def _linhas_da_data_base(data_base: str) -> pd.DataFrame:
    """Linhas da fixture com a data-base pedida (dd/mm/aaaa) — 2 por data:
    a dupla eleita (NTN-B + NTN-B Principal, ou duas NTN-B)."""
    df = TesouroOficialProvider._parsear(_fixture_regressao())
    base = pd.Timestamp(datetime.strptime(data_base, "%d/%m/%Y"))
    sel = df[df["Data Base"] == base]
    assert len(sel) == 2, f"fixture deve ter exatamente 2 linhas para a data-base {data_base}"
    return sel


def _taxa_cupom_do_tipo(tipo: str) -> float:
    """Cupom real anual do tipo no CSV: 6% na NTN-B, zero na Principal."""
    return 0.06 if tipo == TIPO_NTNB else 0.0


def _cotacao_sem_filtro(
    data_base: date,
    data_vencimento: date,
    taxa_real: float,
    taxa_cupom_anual: float,
) -> float:
    """Cotação sobre base 100 descontando TODOS os fluxos — sem a regra de
    liquidação D+1 (é o denominador da razão; usa só API pública, como o
    contrafactual do cupom linear da NTN-F)."""
    fluxos = gerar_fluxos(
        data_compra=data_base,
        data_vencimento=data_vencimento,
        valor_nominal=100.0,
        taxa_cupom_anual=taxa_cupom_anual,
        frequencia_cupom=2,
    )
    return sum(
        f.valor / (1 + taxa_real) ** (pu.dias_uteis(data_base, f.data) / 252) for f in fluxos
    )


def _erro_relativo_da_razao(linha: pd.Series, razao_teorica: float) -> float:
    """Erro relativo da razão teórica contra a razão de PUs oficial da linha."""
    razao_oficial = float(linha["PU Compra Manha"]) / float(linha["PU Venda Manha"])
    return abs(razao_oficial - razao_teorica) / razao_oficial


def _tem_cupom_na_janela_d1(linha: pd.Series) -> bool:
    """Há CUPOM vencendo dentro de (data-base, próximo dia ÚTIL]?

    É o caso em que a regra de liquidação D+1 morde (a NTN-B Principal não
    tem cupom: a janela nunca morde para ela). Espelha o contrato de
    pu.fluxos_liquidados na forma de pergunta.
    """
    if str(linha["Tipo Titulo"]) == TIPO_NTNB_PRINCIPAL:
        return False
    data_base = linha["Data Base"].date()
    limite = proximo_dia_util(data_base)
    fluxos = gerar_fluxos(
        data_compra=data_base,
        data_vencimento=linha["Data Vencimento"].date(),
        valor_nominal=100.0,
        taxa_cupom_anual=0.06,
        frequencia_cupom=2,
    )
    return any(f.tipo == "cupom" and data_base < f.data <= limite for f in fluxos)


# ----------------------------------------------------------------------
# Cabeçalho de auditoria (padrão de test_regressao_ntnf.py)
# ----------------------------------------------------------------------
def test_fixture_regressao_ntnb_tem_cabecalho_de_auditoria() -> None:
    """Cabeçalho de auditoria: path, datas-base, data de captura e versão no próprio arquivo."""
    linhas = CAMINHO_FIXTURE_REGRESSAO_NTNB.read_text(encoding="utf-8").splitlines()
    cabecalho = [linha for linha in linhas if linha.startswith("#")]
    assert any("path: https://www.tesourotransparente.gov.br" in c for c in cabecalho)
    # 8 datas-base de 2024-2026 listadas no cabeçalho (verificação de
    # conteúdo completa em test_linhas_da_fixture_sao_do_escopo_registrado).
    assert any("data-base: 15/02/2024, 14/08/2024, 10/03/2025, 14/08/2025" in c for c in cabecalho)
    assert any("data de captura: 2026-10-06" in c for c in cabecalho)
    assert any("versão" in c for c in cabecalho)


def test_linhas_da_fixture_sao_do_escopo_registrado_no_cabecalho() -> None:
    """Honestidade da excisão: 16 linhas IPCA+ nas datas-base do cabeçalho —
    12 da NTN-B e 4 da Principal ("16 de 62.964", conforme o cabeçalho),
    uma dupla por data-base, prazos de 46 a 12.942 dias corridos e 4
    datas-base de véspera de cupom (1 linha B cada com o filtro D+1
    mordendo)."""
    df = TesouroOficialProvider._parsear(_fixture_regressao())
    assert len(df) == 16
    assert set(df["Tipo Titulo"]) == {TIPO_NTNB, TIPO_NTNB_PRINCIPAL}
    assert (df["Tipo Titulo"] == TIPO_NTNB).sum() == 12
    assert (df["Tipo Titulo"] == TIPO_NTNB_PRINCIPAL).sum() == 4
    assert set(df["Data Base"]) == {pd.Timestamp(d) for d in _datas_base_do_cabecalho()}
    # 8 datas-base, 2024/2025/2026 representados, uma dupla em cada.
    assert len(_datas_base_do_cabecalho()) == 8
    assert (df["Data Base"].dt.year >= 2024).all()
    assert (df["Data Base"].dt.year <= 2026).all()
    assert (df["Data Base"].value_counts() == 2).all()
    # Vencimentos nas datas-base da NTN-B: dia 15, meses 02/05/08/11.
    assert (df["Data Vencimento"].dt.day == 15).all()
    assert set(df["Data Vencimento"].dt.month) <= {2, 5, 8, 11}
    # Cobertura de prazo: 46 dias corridos (30/06/2026 → 15/08/2026) a
    # 12.942 (10/03/2025 → 15/08/2060).
    prazo_dias = (df["Data Vencimento"] - df["Data Base"]).dt.days
    assert prazo_dias.min() == 46
    assert prazo_dias.max() == 12_942
    # As 4 datas-base de véspera de cupom — só a linha NTN-B de cada dupla
    # tem cupom na janela D+1 (a Principal nunca tem).
    linhas_vespera = [linha for _, linha in df.iterrows() if _tem_cupom_na_janela_d1(linha)]
    assert len(linhas_vespera) == 4
    assert {lin["Data Base"].strftime("%d/%m/%Y") for lin in linhas_vespera} == set(
        DATAS_BASE_VESPERA_CUPOM
    )
    assert all(str(lin["Tipo Titulo"]) == TIPO_NTNB for lin in linhas_vespera)


# ----------------------------------------------------------------------
# Razão de PUs do núcleo vs razão oficial publicada (verdade externa)
#
# Cotações sobre base 100: cupom COMPOSTO STN de 6% a.a. → 2,956301 por
# semestre por 100 de VNA; Principal sem cupom. du = dias úteis REAIS do
# calendário B3/SFN (rfquant.data.calendario, validado a ±0 pela bateria em
# tests/test_data_calendario.py). Erros medidos por data-base (razão híbrida,
# D+1 só no numerador):
#   15/02/2024: 4,747e-4 (B 15/08/2026, 912 dias) e 4,758e-4 (B 15/08/2050, 9.678)
#   14/08/2024: 3,447e-4 (B 15/08/2032 — véspera de cupom) e 3,467e-4 (Pr 15/05/2035)
#   10/03/2025: 7,748e-4 (B 15/08/2026) e 7,387e-4 (B 15/08/2060, 12.942 dias)
#   14/08/2025: 3,735e-4 (B 15/08/2030 — véspera de cupom) e 3,501e-4 (Pr 15/08/2050)
#   13/02/2026: 1,082e-3 (B 15/08/2026 — véspera de cupom pagando na segunda
#               útil) e 9,668e-4 (B 15/05/2055)
#   14/05/2026: 5,063e-4 (B 15/05/2037 — véspera de cupom) e 5,227e-4 (Pr 15/05/2029)
#   30/06/2026: 5,384e-4 (B 15/08/2026, 46 dias) e 3,999e-4 (B 15/08/2060)
#   05/10/2026: 5,094e-4 (B 15/08/2030) e 5,040e-4 (Pr 15/05/2035)
# ----------------------------------------------------------------------
@pytest.mark.parametrize("data_base", DATAS_BASE_REGRESSAO)
def test_razao_de_pus_do_nucleo_bate_com_o_oficial(data_base: str) -> None:
    """ntnb.cotacao(taxa de compra) com a regra D+1 sobre a cotação à taxa de
    venda SEM filtro vs PU_Compra/PU_Venda oficiais, rel <= 5e-3.

    A taxa anual do núcleo é a fração decimal (o CSV traz % a.a. reais:
    7,06 → 0,0706). O numerador é a cotação do módulo (cupom composto +
    calendário real + liquidação D+1); o denominador desconta todos os
    fluxos — em dia normal os dois lados coincidem e nas vésperas de cupom
    a assimetria replica a do oficial (ver docstring do módulo).
    """
    for _, linha in _linhas_da_data_base(data_base).iterrows():
        data_compra = linha["Data Base"].date()
        taxa_cupom = _taxa_cupom_do_tipo(str(linha["Tipo Titulo"]))
        cot_compra = ntnb.cotacao(
            data_compra=data_compra,
            data_vencimento=linha["Data Vencimento"].date(),
            taxa_real=float(linha["Taxa Compra Manha"]) / 100.0,
            taxa_cupom_anual=taxa_cupom,
        )
        cot_venda = _cotacao_sem_filtro(
            data_base=data_compra,
            data_vencimento=linha["Data Vencimento"].date(),
            taxa_real=float(linha["Taxa Venda Manha"]) / 100.0,
            taxa_cupom_anual=taxa_cupom,
        )
        assert _erro_relativo_da_razao(linha, cot_compra / cot_venda) <= TOLERANCIA_RAZAO


def test_todas_as_linhas_batem_com_a_razao_oficial_a_5e_3() -> None:
    """As 16 linhas da fixture batem com a razão oficial a 5e-3.

    Espelho do contrato das regressões LTN e NTN-F (contagem impede o
    parametrizado de ficar vacuamente verde): a medição fechou com TODAS as
    16 na tolerância — as 12 normais e as 4 de véspera de cupom (com o D+1
    só no numerador) —, então a contagem exige 16. Mesma defesa contra
    linhas removidas da fixture.
    """
    df = TesouroOficialProvider._parsear(_fixture_regressao())
    dentro = 0
    for _, linha in df.iterrows():
        data_compra = linha["Data Base"].date()
        taxa_cupom = _taxa_cupom_do_tipo(str(linha["Tipo Titulo"]))
        cot_compra = ntnb.cotacao(
            data_compra=data_compra,
            data_vencimento=linha["Data Vencimento"].date(),
            taxa_real=float(linha["Taxa Compra Manha"]) / 100.0,
            taxa_cupom_anual=taxa_cupom,
        )
        cot_venda = _cotacao_sem_filtro(
            data_base=data_compra,
            data_vencimento=linha["Data Vencimento"].date(),
            taxa_real=float(linha["Taxa Venda Manha"]) / 100.0,
            taxa_cupom_anual=taxa_cupom,
        )
        if _erro_relativo_da_razao(linha, cot_compra / cot_venda) <= TOLERANCIA_RAZAO:
            dentro += 1
    assert dentro == len(df) == 16


# ----------------------------------------------------------------------
# Controle negativo 1: o PU Base NÃO é VNA — a estratégia do PU absoluto
# com vna='PU Base Manha' está rejeitada POR MEDIDA, não por preferência
# ----------------------------------------------------------------------
def test_pu_base_como_vna_nao_bate_com_o_pu_compra() -> None:
    """Com vna='PU Base Manha' o PU NÃO bate a 5e-3 — e por isso a regressão
    compara razões, não PUs absolutos.

    Medido: erro de 8,9e-3 (B 15/08/2026 na base 15/02/2024) a 8,2e-1 (Pr
    15/08/2050 na base 14/08/2025) — as 16/16 linhas fora da tolerância com
    folga (> 1,7x). O motivo está na própria fixture: 'PU Base Manha' ==
    'PU Venda Manha' em todas as linhas (a prova abaixo), então o
    multiplicador é o PU do lado da venda, não um valor nominal atualizado —
    e o erro cresce com |cotação/100 - 1| da Principal longa (cotação ~18:
    8,2e-1). Se um dia isto falhar, ou a fixture mudou (regravar com o
    mesmo padrão de cabeçalho) ou o Tesouro passou a publicar o VNA no CSV.
    """
    df = TesouroOficialProvider._parsear(_fixture_regressao())
    # A coluna 'PU Base Manha' é o PU do lado da venda — nunca um VNA.
    assert (df["PU Base Manha"] == df["PU Venda Manha"]).all()
    fora = 0
    for _, linha in df.iterrows():
        pu_oficial = float(linha["PU Compra Manha"])
        pu_teorico = ntnb.calcular(
            data_compra=linha["Data Base"].date(),
            data_vencimento=linha["Data Vencimento"].date(),
            taxa_real=float(linha["Taxa Compra Manha"]) / 100.0,
            vna=float(linha["PU Base Manha"]),
            taxa_cupom_anual=_taxa_cupom_do_tipo(str(linha["Tipo Titulo"])),
        )
        if abs(pu_teorico - pu_oficial) / pu_oficial > TOLERANCIA_RAZAO:
            fora += 1
    assert fora == len(df) == 16


# ----------------------------------------------------------------------
# Controle negativo 2: nas vésperas de cupom, a assimetria compra/venda é
# o que fecha — filtro nos DOIS lados ou em NENHUM não fecha
# ----------------------------------------------------------------------
@pytest.mark.parametrize("data_base", DATAS_BASE_VESPERA_CUPOM)
def test_contrafactuais_de_filtro_na_janela_d1_nao_batem(data_base: str) -> None:
    """Nas vésperas de cupom, PU_Compra/PU_Venda oficial NÃO bate nem com a
    razão com o filtro nos DOIS lados nem com a razão SEM filtro em ambos.

    Medido (2026-10-06, sobre as 4 linhas): 2,9e-2 a 3,3e-2 com o
    filtro em ambos e 2,9e-2 a 3,2e-2 sem filtro em nenhum — ~6 a 7x a
    tolerância de 5e-3, contra 3,4e-4 a 1,1e-3 da razão híbrida (com o
    filtro só no numerador) nas mesmas linhas. É a prova de que o oficial
    mistura convenções: PU Compra EXCLUI o cupom da janela D+1 e PU Venda o
    INCLUI (a réplica na NTN-B do mecanismo medido na fixture NTN-F de
    30/06/2026). Se um dia isto falhar, ou a fixture mudou (regravar) ou a
    regra de liquidação do oficial mudou — aí a híbrida acima também
    deixaria de fechar.
    """
    linhas_com_cupom_na_janela = 0
    for _, linha in _linhas_da_data_base(data_base).iterrows():
        if not _tem_cupom_na_janela_d1(linha):
            continue
        linhas_com_cupom_na_janela += 1
        data_compra = linha["Data Base"].date()
        data_vencimento = linha["Data Vencimento"].date()
        taxa_cupom = _taxa_cupom_do_tipo(str(linha["Tipo Titulo"]))
        taxa_compra = float(linha["Taxa Compra Manha"]) / 100.0
        taxa_venda = float(linha["Taxa Venda Manha"]) / 100.0

        # Contrafactual (i): filtro nos DOIS lados — o oficial não faz isso.
        cot_compra_f = ntnb.cotacao(
            data_compra=data_compra,
            data_vencimento=data_vencimento,
            taxa_real=taxa_compra,
            taxa_cupom_anual=taxa_cupom,
        )
        cot_venda_f = ntnb.cotacao(
            data_compra=data_compra,
            data_vencimento=data_vencimento,
            taxa_real=taxa_venda,
            taxa_cupom_anual=taxa_cupom,
        )
        assert _erro_relativo_da_razao(linha, cot_compra_f / cot_venda_f) > TOLERANCIA_RAZAO

        # Contrafactual (ii): SEM filtro em ambos — idem.
        cot_compra_sf = _cotacao_sem_filtro(
            data_base=data_compra,
            data_vencimento=data_vencimento,
            taxa_real=taxa_compra,
            taxa_cupom_anual=taxa_cupom,
        )
        cot_venda_sf = _cotacao_sem_filtro(
            data_base=data_compra,
            data_vencimento=data_vencimento,
            taxa_real=taxa_venda,
            taxa_cupom_anual=taxa_cupom,
        )
        assert _erro_relativo_da_razao(linha, cot_compra_sf / cot_venda_sf) > TOLERANCIA_RAZAO

    # A data-base de véspera precisa ter a linha B com cupom na janela —
    # sem ela o teste acima não provaria nada.
    assert linhas_com_cupom_na_janela == 1
