"""Bateria de contrato do CVMFundosProvider — fixture ZIP reconstruída, sem rede.

Contrato de série PRÓPRIO: o provider NÃO herda
a ABC ``DataProvider`` — ``titulos_disponiveis``/``historico_taxas`` descrevem
títulos, não informes de fundos. Mesma disciplina da bateria de títulos:
``schema`` (colunas pt-BR exatas), ``ordenação`` (cnpj_fundo, data_competencia
crescentes) e ``tipos`` (data, float, int) — e prova de não-vacuidade no fim.

Cache por comportamento: 1 hit dentro do TTL,
2 hits após expiração — ``cache_isolado`` (nunca o cache real do usuário) +
``relogio`` (patch de ``time.time`` — nunca ``sleep``), fetch instrumentado
contando chamadas HTTP.

CABEÇALHO DE AUDITORIA DA FIXTURE (ZIP é binário — não admite o cabeçalho `#`
das fixtures texto; a auditoria vive AQUI e no sidecar
``tests/fixtures/cvm_informe_sample.README.md``):

    path original:      https://dados.cvm.gov.br/dados/FI/DOC/INF_DIARIO/DADOS/inf_diario_fi_202608.zip
    data de captura:    2026-09-23 (download ÚNICO, fora dos testes; ZIP real
                        tem 11.517.461 B — NUNCA é commitado)
    data-base:          informe de agosto/2026 (mês FECHADO e imune a revisão
                        intramês), competências 2026-08-03 a 2026-08-05 — os 3
                        primeiros dias de competência do mês (01-02/08 caem no
                        fim de semana)
    critério da excisão: os 3 PRIMEIROS CNPJ distintos na ordem do arquivo
                        original (00.017.024/0001-53, 00.068.305/0001-35,
                        00.071.477/0001-68) × 3 dias = 9 linhas + cabeçalho;
                        as linhas mantidas são BYTE A BYTE do original e a
                        ordem é preservada (1.052 B de CSV — os 53,9 MB do CSV
                        integral ficam fora do repo)
    reconstrução:       re-zip DETERMINÍSTICO — ZIP não é excisável byte a byte
                        (corromperia o container), então o CSV excisado é
                        re-zipado com timestamps FIXOS em (2026, 9, 23, 0, 0, 0);
                        receita completa no sidecar README. Fixture: 552 B,
                        sha256 5d5b5a5332265ef7d06de58ab4339165e60eaed4de70fe8583193bde78625ce3
    cadência:           informe diário (D+1); o ZIP mensal inf_diario_fi_YYYYMM.zip
                        é atualizado a cada dia útil intramês e congela no
                        fechamento do mês
"""

from __future__ import annotations

import pickle
import zipfile
from datetime import date

import pandas as pd
import pytest
import requests
from conftest import FIXTURE_ZIP, RespostaErro, RespostaZip, repetir_se_rede_instavel

from rfquant.data import cache
from rfquant.data.cvm_fundos import (
    CVM_BASE_URL,
    TTL_CVM,
    USER_AGENT,
    CVMFundosProvider,
    InformeNaoDisponivel,
    RedeIndisponivel,
    percentual_cdi,
    rentabilidade_anualizada,
    rentabilidade_periodo,
)
from rfquant.data.sgs_bcb import SGSProvider

ANO, MES = 2026, 8
CNPJ_F1 = "00.017.024/0001-53"
CNPJ_F2 = "00.068.305/0001-35"
CNPJ_F3 = "00.071.477/0001-68"
TIMESTAMPS_FIXOS = (2026, 9, 23, 0, 0, 0)

COLUNAS_CONTRATO = [
    "tipo_fundo",
    "cnpj_fundo",
    "id_subclasse",
    "data_competencia",
    "valor_total",
    "valor_cota",
    "patrimonio_liquido",
    "captacao_dia",
    "resgate_dia",
    "numero_cotistas",
]


def validar_contrato_informe(df: pd.DataFrame) -> None:
    """Invariáveis de contrato do informe (toda a bateria passa por aqui).

    Levanta ``AssertionError`` na primeira violação — schema, tipos e valores
    de ``data_competencia``.
    """
    assert isinstance(df, pd.DataFrame), f"saída é {type(df).__name__}, não DataFrame"
    assert list(df.columns) == COLUNAS_CONTRATO, f"colunas: {list(df.columns)}"
    for _, linha in df.iterrows():
        assert isinstance(linha["data_competencia"], date), (
            f"data_competencia: {linha['data_competencia']!r}"
        )
        assert isinstance(linha["cnpj_fundo"], str) and len(linha["cnpj_fundo"]) == 18, (
            f"cnpj_fundo fora da máscara XX.XXX.XXX/XXXX-XX: {linha['cnpj_fundo']!r}"
        )
        for campo in ("valor_cota", "patrimonio_liquido"):
            assert isinstance(linha[campo], float), f"{campo}: {linha[campo]!r}"
        assert pd.api.types.is_integer_dtype(df["numero_cotistas"]), "numero_cotistas não é inteiro"


class _FetchCVM:
    """``requests.get`` instrumentado: conta chamadas, registra as URLs e a
    User-Agent (padrão ``_FetchContado`` do conftest, com UA).

    ``cenario`` decide o que cada chamada devolve: o ZIP da fixture ("ok") ou
    uma resposta 404 ("mes_ausente"); com ``rede_cai`` a chamada levanta
    ``ConnectionError`` direto (falha de rede antes da resposta).
    """

    def __init__(self, conteudo_zip: bytes, cenario: str = "ok") -> None:
        self._conteudo = conteudo_zip
        self._cenario = cenario
        self.chamadas = 0
        self.urls: list[str] = []
        self.user_agent: str | None = None

    def __call__(self, url: str, params=None, timeout=None, headers=None, **kwargs):
        self.chamadas += 1
        self.urls.append(url)
        self.user_agent = (headers or {}).get("User-Agent")
        if self._cenario == "rede_cai":
            raise requests.ConnectionError("falha de conexão simulada")
        if self._cenario == "mes_ausente":
            return RespostaErro()
        return RespostaZip(self._conteudo)


@pytest.fixture
def fetch_cvm(monkeypatch, cache_isolado) -> _FetchCVM:
    """Troca ``requests.get`` pelo fetch que serve o ZIP da fixture (sem rede).

    Depende de ``cache_isolado``: o provider grava o ZIP baixado no
    ``rfquant.data.cache`` — nunca no cache real do usuário.
    """
    fetch = _FetchCVM(FIXTURE_ZIP.read_bytes())
    monkeypatch.setattr(requests, "get", fetch)
    return fetch


@pytest.fixture
def provider_cvm(cache_isolado) -> CVMFundosProvider:
    """Provider com cache HTTP isolado em ``tmp_path`` (nunca ~/.rfquant)."""
    return CVMFundosProvider()


# ----------------------------------------------------------------------
# Fixture: determinismo e tamanho (KBs, nunca os 11 MB)
# ----------------------------------------------------------------------
def test_fixture_zip_reconstruida_com_timestamps_fixos() -> None:
    """A fixture é o re-zip determinístico: entrada única, timestamp fixo, KBs."""
    assert FIXTURE_ZIP.stat().st_size < 100 * 1024, "fixture saiu do porte de KBs"
    with zipfile.ZipFile(FIXTURE_ZIP) as zf:
        entradas = zf.infolist()
        assert len(entradas) == 1, f"esperado 1 CSV no ZIP, veio {len(entradas)}"
        assert entradas[0].filename == "inf_diario_fi_202608.csv"
        assert entradas[0].date_time == TIMESTAMPS_FIXOS, (
            f"timestamp do ZIP não é o fixo da auditoria: {entradas[0].date_time}"
        )
        csv = zf.read(entradas[0].filename)
    assert len(csv.splitlines()) == 10  # cabeçalho + 3 fundos × 3 dias


# ----------------------------------------------------------------------
# Bateria de contrato da série (schema, ordenação, tipos)
# ----------------------------------------------------------------------
def test_informe_diario_schema_e_tipos(
    provider_cvm: CVMFundosProvider, fetch_cvm: _FetchCVM
) -> None:
    """Informe completo: 9 linhas, colunas pt-BR exatas, tipos do contrato."""
    df = provider_cvm.informe_diario(ANO, MES)
    validar_contrato_informe(df)
    assert len(df) == 9
    # id_subclasse vazio na fonte vira NaN sem quebrar o contrato
    assert df["id_subclasse"].isna().all()
    # contrato de endpoint: a URL segue o padrão oficial do dataset
    assert fetch_cvm.urls == [f"{CVM_BASE_URL}/inf_diario_fi_{ANO}{MES:02d}.zip"]


def test_informe_diario_ordenacao_crescente(
    provider_cvm: CVMFundosProvider, fetch_cvm: _FetchCVM
) -> None:
    """Ordenação é garantia do provider: (cnpj_fundo, data_competencia) crescentes."""
    df = provider_cvm.informe_diario(ANO, MES)
    reordenado = df.sort_values(["cnpj_fundo", "data_competencia"]).reset_index(drop=True)
    assert df.equals(reordenado)
    serie_f1 = df[df["cnpj_fundo"] == CNPJ_F1]
    assert list(serie_f1["data_competencia"]) == [
        date(2026, 8, 3),
        date(2026, 8, 4),
        date(2026, 8, 5),
    ]


def test_informe_diario_valores_fixados_da_captura(
    provider_cvm: CVMFundosProvider, fetch_cvm: _FetchCVM
) -> None:
    """Valores byte a byte do CSV real capturado (linha 1 da fixture, 03/08/2026)."""
    df = provider_cvm.informe_diario(ANO, MES, cnpj=CNPJ_F1)
    primeiro = df.iloc[0]
    assert primeiro["data_competencia"] == date(2026, 8, 3)
    assert primeiro["valor_cota"] == pytest.approx(44.275588)
    assert primeiro["patrimonio_liquido"] == pytest.approx(1207786.03)
    assert primeiro["resgate_dia"] == pytest.approx(0.0)
    assert primeiro["numero_cotistas"] == 1
    # fechamento da mesma série na última competência mantida (05/08/2026)
    ultimo = df.iloc[-1]
    assert ultimo["valor_cota"] == pytest.approx(44.3136127)
    assert ultimo["data_competencia"] == date(2026, 8, 5)


# ----------------------------------------------------------------------
# CNPJ por igualdade normalizada (fim do str.contains)
# ----------------------------------------------------------------------
def test_cnpj_igualdade_normalizada_formatado_e_digitos(
    provider_cvm: CVMFundosProvider, fetch_cvm: _FetchCVM
) -> None:
    """Máscara é indiferente: "00.017.024/0001-53" == "00017024000153".

    Prova de não-vacuidade: sob o ``str.contains`` antigo, a consulta só com
    dígitos voltava VAZIA (a fonte guarda o CNPJ mascarado) — o assert de
    3 linhas abaixo falharia.
    """
    mascarado = provider_cvm.informe_diario(ANO, MES, cnpj=CNPJ_F1)
    digitos = provider_cvm.informe_diario(ANO, MES, cnpj="00017024000153")
    validar_contrato_informe(mascarado)
    assert len(mascarado) == 3
    assert mascarado.equals(digitos)
    assert set(mascarado["cnpj_fundo"]) == {CNPJ_F1}


def test_cnpj_digito_diferente_ou_parcial_nao_casa(
    provider_cvm: CVMFundosProvider, fetch_cvm: _FetchCVM
) -> None:
    """Igualdade, não substring: raiz parcial e dígito verificador diverso não casam.

    O caso do AC: ``12.345.678/0001-90`` NÃO casa ``…/0001-91`` — e nenhuma
    fração do CNPJ ("00.017.024", raiz do fundo 1) casa por conter parte da
    máscara, como o ``str.contains`` antigo casaria.
    """
    assert provider_cvm.informe_diario(ANO, MES, cnpj="12.345.678/0001-90").empty
    assert provider_cvm.informe_diario(ANO, MES, cnpj="00.017.024").empty
    assert provider_cvm.informe_diario(ANO, MES, cnpj="00017024000190").empty


# ----------------------------------------------------------------------
# Erros explícitos (fim do `except Exception: pass`)
# ----------------------------------------------------------------------
def test_mes_ausente_erro_explicito_ptbr(monkeypatch, cache_isolado) -> None:
    """Mês sem arquivo publicado (HTTP 404) ⇒ InformeNaoDisponivel pt-BR com
    a causa encadeada — erro de domínio distinto de rede."""
    fetch = _FetchCVM(FIXTURE_ZIP.read_bytes(), cenario="mes_ausente")
    monkeypatch.setattr(requests, "get", fetch)
    provider = CVMFundosProvider()
    with pytest.raises(InformeNaoDisponivel, match="não está disponível na fonte") as exc:
        provider.informe_diario(2026, 9)
    assert isinstance(exc.value.__cause__, requests.HTTPError)
    assert isinstance(exc.value, RuntimeError)  # compat: subclasse de RuntimeError
    assert fetch.urls[-1].endswith("inf_diario_fi_202609.zip")
    with pytest.raises(InformeNaoDisponivel, match="ainda não ter sido publicado"):
        provider.informe_diario(2099, 1)


def test_falha_de_rede_erro_explicito_ptbr(monkeypatch, cache_isolado) -> None:
    """ConnectionError na origem ⇒ RedeIndisponivel pt-BR com a causa encadeada."""
    fetch = _FetchCVM(FIXTURE_ZIP.read_bytes(), cenario="rede_cai")
    monkeypatch.setattr(requests, "get", fetch)
    provider = CVMFundosProvider()
    with pytest.raises(RedeIndisponivel, match="Falha ao obter o informe diário da CVM") as exc:
        provider.informe_diario(ANO, MES)
    assert isinstance(exc.value.__cause__, requests.ConnectionError), (
        "erro original deve vir encadeado (`from`), não engolido"
    )


def test_historico_fundo_propaga_erro_de_mes_ausente(monkeypatch, cache_isolado) -> None:
    """historico_fundo NÃO engole mês sem arquivo (era o `except: pass`).

    Sob o código antigo, o intervalo abaixo devolvia DataFrame vazio em
    silêncio; no contrato novo o erro explode — buraco de série nunca vira
    número errado a jusante.
    """
    fetch = _FetchCVM(FIXTURE_ZIP.read_bytes(), cenario="mes_ausente")
    monkeypatch.setattr(requests, "get", fetch)
    provider = CVMFundosProvider()
    with pytest.raises(InformeNaoDisponivel, match="não está disponível na fonte"):
        provider.historico_fundo(CNPJ_F1, inicio=date(2026, 7, 1), fim=date(2026, 8, 31))


# ----------------------------------------------------------------------
# histórico e listagem sobre a fixture
# ----------------------------------------------------------------------
def test_historico_fundo_serie_ordenada_na_janela(
    provider_cvm: CVMFundosProvider, fetch_cvm: _FetchCVM
) -> None:
    """Série do fundo 3 na janela 04-05/08: 2 linhas, ordenadas, valores reais."""
    serie = provider_cvm.historico_fundo(CNPJ_F3, inicio=date(2026, 8, 4), fim=date(2026, 8, 5))
    validar_contrato_informe(serie)
    assert list(serie["data_competencia"]) == [date(2026, 8, 4), date(2026, 8, 5)]
    assert set(serie["cnpj_fundo"]) == {CNPJ_F3}
    # cotas da captura real (linhas 7-8 da fixture)
    assert list(serie["valor_cota"]) == pytest.approx([16.550748888, 16.558375524])


def test_listar_fundos_ultimo_dia_ordenado_por_pl(
    provider_cvm: CVMFundosProvider, fetch_cvm: _FetchCVM
) -> None:
    """Listagem usa só a última competência e ordena por PL decrescente."""
    df = provider_cvm.listar_fundos(ANO, MES)
    assert list(df["cnpj_fundo"]) == [CNPJ_F3, CNPJ_F2, CNPJ_F1]
    # PL de 05/08/2026 (última competência da fixture), a partir da captura real
    assert list(df["patrimonio_liquido"]) == pytest.approx([705146212.04, 41131682.26, 1208823.30])


def test_mes_invalido_e_janela_invalida(
    provider_cvm: CVMFundosProvider, fetch_cvm: _FetchCVM
) -> None:
    """Validação de entrada mantida: mês 1-12 e janela início ≤ fim."""
    with pytest.raises(ValueError, match="Mês deve estar entre 1 e 12"):
        provider_cvm.informe_diario(2026, 13)
    with pytest.raises(ValueError, match="Data inicial deve ser anterior à final"):
        provider_cvm.historico_fundo(CNPJ_F1, inicio=date(2026, 8, 5), fim=date(2026, 8, 4))


# ----------------------------------------------------------------------
# Cache com TTL explícito (cache_isolado + relogio — fim do cache de
# arquivo sem expiração)
# ----------------------------------------------------------------------
def test_ttl_um_hit_dentro_do_ttl(
    provider_cvm: CVMFundosProvider, fetch_cvm: _FetchCVM, cache_isolado, relogio
) -> None:
    """Chamadas dentro do TTL → um único fetch HTTP (as demais são hit)."""
    provider_cvm.informe_diario(ANO, MES)
    provider_cvm.informe_diario(ANO, MES)
    assert fetch_cvm.chamadas == 1

    relogio.avancar(TTL_CVM - 1)  # 1 s antes de expirar
    provider_cvm.informe_diario(ANO, MES)
    assert fetch_cvm.chamadas == 1  # ainda hit


def test_ttl_dois_hits_apos_expiracao(
    provider_cvm: CVMFundosProvider, fetch_cvm: _FetchCVM, cache_isolado, relogio
) -> None:
    """Relógio avança além do TTL → cache expira → segundo fetch real.

    Sob o cache de arquivo antigo (sem expiração), o segundo fetch nunca
    acontecia — a entrada só saía com limpeza manual do diretório.
    """
    provider_cvm.informe_diario(ANO, MES)
    assert fetch_cvm.chamadas == 1

    relogio.avancar(TTL_CVM + 1)
    provider_cvm.informe_diario(ANO, MES)
    assert fetch_cvm.chamadas == 2


def test_cache_chave_inclui_mes(provider_cvm: CVMFundosProvider, fetch_cvm: _FetchCVM) -> None:
    """Meses distintos não colidem no cache (2 fetches); repetir o mês é hit
    (continua 2) — a chave do cache é a URL do ZIP mensal."""
    provider_cvm.informe_diario(2026, 8)
    provider_cvm.informe_diario(2026, 9)
    assert fetch_cvm.chamadas == 2
    provider_cvm.informe_diario(2026, 8)
    assert fetch_cvm.chamadas == 2


def test_usar_cache_false_forca_redownload(
    provider_cvm: CVMFundosProvider, fetch_cvm: _FetchCVM, cache_isolado, relogio
) -> None:
    """usar_cache=False pula a leitura do cache mesmo dentro do TTL e atualiza
    a entrada: a chamada seguinte (com cache) volta a ser hit."""
    provider_cvm.informe_diario(ANO, MES)
    provider_cvm.informe_diario(ANO, MES, usar_cache=False)
    assert fetch_cvm.chamadas == 2
    provider_cvm.informe_diario(ANO, MES)
    assert fetch_cvm.chamadas == 2


def test_frame_parseado_cacheado_alem_do_zip(
    provider_cvm: CVMFundosProvider, fetch_cvm: _FetchCVM, monkeypatch
) -> None:
    """Cache de frame além do ZIP: a 2ª chamada do MESMO mês não re-parseia o
    informe (read_csv roda 1×) nem re-baixa (HTTP 1×) — e o frame hit devolve
    o mesmo contrato da 1ª."""
    parses = {"n": 0}
    read_csv_original = pd.read_csv

    def read_csv_contado(*args, **kwargs):
        parses["n"] += 1
        return read_csv_original(*args, **kwargs)

    monkeypatch.setattr(pd, "read_csv", read_csv_contado)
    df1 = provider_cvm.informe_diario(ANO, MES)
    df2 = provider_cvm.informe_diario(ANO, MES)
    assert fetch_cvm.chamadas == 1
    assert parses["n"] == 1
    validar_contrato_informe(df2)
    assert df1.equals(df2)


def test_payload_do_frame_cacheado_e_portavel_ao_pickle(
    provider_cvm: CVMFundosProvider,
) -> None:
    """O payload do frame no cache é portável ao pickle: nenhum ambiente
    precisa do pyarrow para ler o que outro gravou.

    O pandas 3.x com pyarrow faz TODA coluna de string de um DataFrame
    virar ArrowStringArray — o pickle do FRAME referencia o pyarrow e
    quebra a leitura em ambiente sem o pacote (o pacote público lendo o
    cache do desenvolvimento, por exemplo). O provider grava um dict de
    arrays numpy (portável por construção) e o leitor reconstrói o frame
    com os dtypes nativos do ambiente.
    """
    df1 = provider_cvm.informe_diario(ANO, MES)
    payload = cache.get(provider_cvm._url_mes(ANO, MES) + "::df")
    assert not isinstance(payload, pd.DataFrame)
    assert b"pyarrow" not in pickle.dumps(payload)
    reconstruido = cache.frame_do_cache(payload)
    assert reconstruido is not None
    assert reconstruido.equals(df1)


def test_frame_cache_nao_vaza_entre_meses(
    provider_cvm: CVMFundosProvider, fetch_cvm: _FetchCVM
) -> None:
    """A chave do frame deriva da URL do mês: meses distintos parseiam cada
    um o seu (2 HTTP), e repetir o mês é hit de frame (segue 2)."""
    provider_cvm.informe_diario(2026, 8)
    provider_cvm.informe_diario(2026, 9)
    assert fetch_cvm.chamadas == 2
    provider_cvm.informe_diario(2026, 8)
    assert fetch_cvm.chamadas == 2


def test_user_agent_explicito_no_fetch(
    provider_cvm: CVMFundosProvider, fetch_cvm: _FetchCVM
) -> None:
    """O fetch manda User-Agent explícita do rfquant — nunca a
    default de biblioteca (``python-requests/...``)."""
    provider_cvm.informe_diario(ANO, MES)
    assert fetch_cvm.user_agent == USER_AGENT
    assert fetch_cvm.user_agent is not None
    assert "rfquant" in fetch_cvm.user_agent


# ----------------------------------------------------------------------
# Prova de não-vacuidade da bateria
# ----------------------------------------------------------------------
def test_bateria_nao_e_vacua_schema_antigo_da_fonte() -> None:
    """Prova de não-vacuidade: o layout ANTIGO da fonte (pré-RCVM 175) é rejeitado.

    O provider renomeava ``TP_FUNDO``/``CNPJ_FUNDO`` — colunas que não existem
    mais no arquivo real. A bateria falha para uma saída assim; é exatamente o
    rompimento de contrato que a migração de schema corrigiu.
    """
    df_antigo = pd.DataFrame(
        [
            {
                "TP_FUNDO": "FI",
                "CNPJ_FUNDO": CNPJ_F1,
                "DT_COMPTC": date(2026, 8, 3),
                "VL_QUOTA": 44.275588,
                "VL_PATRIM_LIQ": 1207786.03,
                "numero_cotistas": 1,
            }
        ]
    )
    with pytest.raises(AssertionError, match="colunas"):
        validar_contrato_informe(df_antigo)


# ----------------------------------------------------------------------
# Métricas de fundo: acumulada, anualizada (DU real) e %CDI
# ----------------------------------------------------------------------
class _ProviderSGSMockado(SGSProvider):
    """Provider SGS/BCB mockado: série flat fixa, sem rede nem cache.

    Espelha o padrão do mock de ``tests/test_comparison_taxa_equivalente.py``:
    colunas ``data``/``valor`` na unidade oficial do SGS (% ao dia) e as
    janelas pedidas registradas — prova de que o CDI do %CDI entra pelo
    provider de dados na janela exata do fundo.
    """

    def __init__(self, valor_dia: float, datas: list[date]) -> None:
        super().__init__()
        self._valor_dia = valor_dia
        self._datas = datas
        self.janelas: list[tuple[date, date]] = []

    def serie_diaria(self, inicio: date, fim: date) -> pd.DataFrame:
        self.janelas.append((inicio, fim))
        presentes = [d for d in self._datas if inicio <= d <= fim]
        return pd.DataFrame({"data": presentes, "valor": [self._valor_dia] * len(presentes)})


def test_rentabilidade_periodo_fixada_na_fixture(
    provider_cvm: CVMFundosProvider, fetch_cvm: _FetchCVM
) -> None:
    """(i) Acumulada por valor_cota — conta à mão com as cotas da captura:

    44.3136127 / 44.275588 - 1 = 0,0008588186338711612 (0,08588% no período).
    """
    serie = provider_cvm.informe_diario(ANO, MES, cnpj=CNPJ_F1)
    assert rentabilidade_periodo(serie) == pytest.approx(0.0008588186338711612, rel=1e-12)


def test_rentabilidade_anualizada_du_do_calendario_real(
    provider_cvm: CVMFundosProvider, fetch_cvm: _FetchCVM
) -> None:
    """(ii) Anualizada base 252 com DU do calendário real — conta à mão:

    acumulada = 44.3136127 / 44.275588 - 1 = 0,0008588186338711612;
    janela 03→05/08/2026: 03/08 é segunda (exclusiva na convenção
    (inicio, fim]) e 04-05/08 são terça/quarta, dias úteis ⇒ DU = 2;
    anualizada = (1,0008588186338711612)^(252/2) - 1 = 0,114231252606674.
    """
    serie = provider_cvm.informe_diario(ANO, MES, cnpj=CNPJ_F1)
    assert rentabilidade_anualizada(serie) == pytest.approx(0.114231252606674, rel=1e-12)


def test_rentabilidade_anualizada_du_real_nao_e_contagem_de_linhas() -> None:
    """Prova do calendário real: DU do calendário ≠ nº de linhas - 1.

    Série qui 06/08 → seg 10/08/2026 (2 linhas): contagem de linhas daria
    1 DU; o calendário real conta 07/08 (sex) e 10/08 (seg) — 08-09/08 caem
    no fim de semana ⇒ DU = 2. Conta à mão: acumulada 1% (cota 100 → 101);
    anualizada = (1,01)^(252/2) - 1 = 2,5034271933694074.
    """
    df = pd.DataFrame(
        {
            "data_competencia": [date(2026, 8, 6), date(2026, 8, 10)],
            "valor_cota": [100.0, 101.0],
        }
    )
    assert rentabilidade_anualizada(df) == pytest.approx(2.5034271933694074, rel=1e-12)


def test_percentual_cdi_com_provider_mockado(
    provider_cvm: CVMFundosProvider, fetch_cvm: _FetchCVM
) -> None:
    """(iii) % do CDI pela composição taxa_anual_para_cdi — conta à mão:

    anualizada do fundo = 0,114231252606674 (conta do teste (ii) acima);
    provider mockado: série flat a 0,05 %/dia nas 3 competências 03-05/08/2026
    (janela inclusiva do CDI) — acumulado = (1,0005)^3 - 1 = 0,001500750125;
    cdi_anual = (1,001500750125)^(252/3) - 1 = (1,0005)^252 - 1 =
    0,13424645086256137; %CDI = 0,114231252606674 / 0,13424645086256137 =
    0,8509070584191569 (~85,09% do CDI).
    """
    serie = provider_cvm.informe_diario(ANO, MES, cnpj=CNPJ_F1)
    provider = _ProviderSGSMockado(
        valor_dia=0.05,
        datas=[date(2026, 8, 3), date(2026, 8, 4), date(2026, 8, 5)],
    )
    assert percentual_cdi(serie, provider) == pytest.approx(0.8509070584191569, rel=1e-12)
    # o CDI entra pelo provider de dados na janela exata do fundo (início a fim)
    assert provider.janelas == [(date(2026, 8, 3), date(2026, 8, 5))]


def test_metricas_degeneradas_devolvem_zero() -> None:
    """Contrato 0.0 das entradas degeneradas (padrão de rentabilidade_periodo):
    df vazio, sem data_competencia ou DU 0 ⇒ 0.0 na anualizada e no %CDI —
    e o caminho vazio não consulta o provider (janelas fica vazio)."""
    provider = _ProviderSGSMockado(valor_dia=0.05, datas=[])
    vazio = pd.DataFrame()
    assert rentabilidade_anualizada(vazio) == 0.0
    assert percentual_cdi(vazio, provider) == 0.0
    sem_coluna = pd.DataFrame({"valor_cota": [100.0, 101.0]})
    assert rentabilidade_anualizada(sem_coluna) == 0.0
    assert percentual_cdi(sem_coluna, provider) == 0.0
    du_zero = pd.DataFrame({"data_competencia": [date(2026, 8, 6)], "valor_cota": [100.0]})
    assert rentabilidade_anualizada(du_zero) == 0.0
    assert provider.janelas == []


# ----------------------------------------------------------------------
# Teste de rede (job de CI semanal; deselecionado na suíte padrão
# pelos addopts `-m 'not network'` do pyproject — marker registrado, strict).
# Nasce SEM xfail e SEM skip: o endpoint já foi confirmado na captura da
# fixture, então falha de endpoint no job semanal é regressão, não expectativa.
# ----------------------------------------------------------------------
@pytest.mark.network
@repetir_se_rede_instavel()
def test_cvm_endpoint_responde_rede_real(provider_cvm: CVMFundosProvider) -> None:
    """Endpoint vivo da CVM serve o mês FECHADO da fixture, no contrato.

    Mês fixo ``ANO``/``MES`` (agosto/2026) — o MESMO data-base do sidecar
    ``cvm_informe_sample.README.md`` — porque mês fechado congela na fonte: o
    ZIP intramês é republicado a cada dia útil e mês corrente no início do mês
    pode nem ter arquivo, o que tornaria o teste intermitente. Custo consciente:
    ~11 MB de download por execução (medição da captura: 11.514.595 B), rodando só
    no gatilho ``schedule`` do ci.yml — nunca no CI de PR. ``provider_cvm``
    traz ``cache_isolado``: o ZIP real NUNCA gravará no cache do usuário.
    """
    df = provider_cvm.informe_diario(ANO, MES)
    # colunas do contrato no payload integral; tipos validados na fatia real
    # do fundo 1 (bateria completa offline já cobre o resto — e iterrows no
    # arquivo inteiro, ~1 linha por fundo/dia, custaria minutos no job)
    assert list(df.columns) == COLUNAS_CONTRATO
    assert pd.api.types.is_integer_dtype(df["numero_cotistas"])
    amostra = df[df["cnpj_fundo"] == CNPJ_F1]
    validar_contrato_informe(amostra)
    assert not amostra.empty
    # linhagem fixture ↔ fonte: os 3 CNPJ do sidecar saíram DESTE ZIP, que
    # fica congelado após o fechamento do mês — continuam no arquivo real
    assert {CNPJ_F1, CNPJ_F2, CNPJ_F3} <= set(df["cnpj_fundo"])
    # e o payload é de fato o mês pedido (não um ZIP trocado pela fonte)
    assert df["data_competencia"].min() >= date(ANO, MES, 1)
    assert df["data_competencia"].max() <= date(ANO, MES, 31)
