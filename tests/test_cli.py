"""Testes de CLI com CliRunner.

`listar --fonte=oficial` roda sem rede: o HTTP do stub é mockado com a
fixture REAL capturada do endpoint oficial (`tesouro_oficial_sample.csv`), cache
isolado em tmp. `precificar` é matemática pura; `comparar` também, exceto o
`--cdi-auto`, e `fundos resumo` inteiro: os providers que eles consultam
(SGS/BCB e CVM) são servidos por fixtures REAIS, cache isolado em tmp.

Comportamento existente — estes testes o fixam como contrato
(caracterização): primeira execução verde é o esperado.
"""

from __future__ import annotations

import io
import zipfile
from datetime import date

import pytest
import requests
from conftest import FIXTURE_ZIP, RespostaErro, RespostaFake, RespostaZip, fixture_payload
from test_data_tesouro_oficial import _fixture_real
from typer.testing import CliRunner

from rfquant.cli import app
from rfquant.comparison import ir, taxa_equivalente
from rfquant.config import settings
from rfquant.data import SGSProvider
from rfquant.data.cvm_fundos import (
    CVMFundosProvider,
    percentual_cdi,
    rentabilidade_anualizada,
    rentabilidade_periodo,
)

runner = CliRunner()


@pytest.fixture
def http_fixture_real(monkeypatch, cache_isolado) -> None:
    """GET do stub oficial responde com a fixture real; cache em tmp."""
    monkeypatch.setattr(
        requests, "get", lambda *args, **kwargs: RespostaFake({}, texto=_fixture_real())
    )
    return None


@pytest.fixture
def http_fixture_sgs(monkeypatch, cache_isolado) -> None:
    """GET do provider SGS/BCB responde com a fixture real (setembro/2026
    excisada); cache em tmp — `comparar --cdi-auto` sem rede."""
    monkeypatch.setattr(requests, "get", lambda *args, **kwargs: RespostaFake(fixture_payload()))
    return None


@pytest.fixture
def http_fixture_fundos(monkeypatch, cache_isolado) -> None:
    """GET duplo sem rede: a URL da CVM serve o ZIP da fixture real
    (reconstruído) e a do SGS/BCB o JSON da série 12 — `fundos resumo`
    usa os dois providers (informe do mês + CDI da janela)."""

    def get_fake(url, *args, **kwargs):
        if "dados.cvm.gov.br" in str(url):
            return RespostaZip(FIXTURE_ZIP.read_bytes())
        return RespostaFake(fixture_payload())

    monkeypatch.setattr(requests, "get", get_fake)
    return None


# ----------------------------------------------------------------------
# rfq tesouro listar
# ----------------------------------------------------------------------
def test_listar_fonte_oficial_renderiza_tabela_com_titulos(http_fixture_real) -> None:
    """--fonte=oficial sem rede: tabela com títulos reais da fixture.

    --limite 200 porque a data-base real tem ~58 títulos: com o default 50,
    o corte pós-ordenação (tipo, vencimento) deixaria Selic (último grupo
    alfabético) sempre de fora.
    """
    resultado = runner.invoke(app, ["tesouro", "listar", "--fonte=oficial", "--limite", "200"])
    assert resultado.exit_code == 0
    saida = resultado.stdout
    assert "fonte: oficial" in saida  # a saída anuncia a fonte usada
    assert "Tesouro Direto" in saida  # título da tabela
    assert "Nome" in saida and "Taxa compra" in saida and "PU compra" in saida
    assert "Tesouro Selic" in saida  # nome real da fixture (18/09/2026)


def test_listar_com_tipo_filtra_a_tabela(http_fixture_real) -> None:
    """--tipo Selic deixa só Selic: IPCA+/Prefixado não aparecem."""
    resultado = runner.invoke(app, ["tesouro", "listar", "--fonte=oficial", "--tipo", "Selic"])
    assert resultado.exit_code == 0
    saida = resultado.stdout
    assert "Tesouro Selic" in saida
    assert "IPCA+" not in saida
    assert "Prefixado" not in saida


def test_listar_fonte_brapi_sem_token_falha_com_mensagem(monkeypatch) -> None:
    """--fonte=brapi sem BRAPI_TOKEN: exit 1 + mensagem explícita."""
    monkeypatch.setattr(settings, "brapi_token", None)
    resultado = runner.invoke(app, ["tesouro", "listar", "--fonte=brapi"])
    assert resultado.exit_code == 1
    assert "BRAPI_TOKEN ausente" in resultado.stdout
    assert "--fonte=oficial" in resultado.stdout  # a dica acompanha o erro


def test_falha_de_rede_brapi_nao_expoe_o_token(monkeypatch, cache_isolado) -> None:
    """Falha de rede na fonte brapi: a mensagem da exceção do requests embute
    a URL completa da requisição — e o token viaja na query. O tratador
    imprime o detalhe da falha SEM expor o token."""

    def get_fake(*args, **kwargs):
        raise requests.HTTPError(
            "401 Client Error: Unauthorized for url: "
            "https://brapi.dev/api/treasury?token=token-secreto-do-usuario"
        )

    monkeypatch.setattr(settings, "brapi_token", "token-secreto-do-usuario")
    monkeypatch.setattr(requests, "get", get_fake)
    resultado = runner.invoke(app, ["tesouro", "listar", "--fonte=brapi"])
    assert resultado.exit_code == 1
    # saída normalizada: o rich quebra linhas longas a qualquer espaço
    saida_plana = " ".join(resultado.stdout.split())
    assert "Falha de rede ao obter os títulos do Tesouro" in saida_plana
    assert "token-secreto-do-usuario" not in saida_plana
    assert "token=***" in saida_plana


def test_listar_sem_fonte_usa_auto_e_anuncia_a_fonte(http_fixture_real) -> None:
    """Sem --fonte, o default é auto: o mapa declarado de rfquant.data
    resolve títulos → oficial, e a saída anuncia a fonte usada."""
    resultado = runner.invoke(app, ["tesouro", "listar", "--limite", "200"])
    assert resultado.exit_code == 0
    saida = resultado.stdout
    assert "fonte: oficial" in saida
    assert "Tesouro Selic" in saida


def test_listar_auto_e_deterministico_com_token_no_ambiente(http_fixture_real, monkeypatch) -> None:
    """Determinismo do auto: com BRAPI_TOKEN no ambiente, o default continua
    resolvendo títulos → oficial — brapi só entra por pino explícito."""
    monkeypatch.setattr(settings, "brapi_token", "token-ficticio")
    resultado = runner.invoke(app, ["tesouro", "listar"])
    assert resultado.exit_code == 0
    saida = resultado.stdout
    assert "fonte: oficial" in saida
    assert "fonte: brapi" not in saida


def test_listar_fonte_desconhecida_erro_ptbr() -> None:
    """Fonte fora do conjunto auto|oficial|brapi ⇒ erro pt-BR + exit 1,
    com a lista de opções válidas na mensagem."""
    resultado = runner.invoke(app, ["tesouro", "listar", "--fonte=xpto"])
    assert resultado.exit_code == 1
    assert "Fonte 'xpto' desconhecida" in resultado.stdout
    assert "--fonte=auto" in resultado.stdout


def test_hoje_funciona_sem_token(http_fixture_real) -> None:
    """`rfq hoje` continua funcionando sem BRAPI_TOKEN (fonte oficial)."""
    resultado = runner.invoke(app, ["hoje"])
    assert resultado.exit_code == 0
    saida = resultado.stdout
    assert "fonte: oficial" in saida
    assert "Tesouro Direto" in saida


# ----------------------------------------------------------------------
# rfq tesouro precificar
# ----------------------------------------------------------------------
def test_precificar_imprime_pu_durations_e_cy_com_cupom() -> None:
    """Com cupom: PU, as duas durations e Current Yield."""
    resultado = runner.invoke(
        app,
        [
            "tesouro",
            "precificar",
            "--vencimento",
            "2035-05-15",
            "--taxa",
            "0.062",
            "--cupom",
            "0.06",
        ],
    )
    assert resultado.exit_code == 0
    saida = resultado.stdout
    assert "PU:" in saida
    assert "Duration Mac:" in saida
    assert "Duration Mod:" in saida
    assert "DV01:" in saida
    assert "Convexidade:" in saida
    assert "Current Yield:" in saida


def test_precificar_zero_cupom_nao_mostra_current_yield() -> None:
    """Sem cupom: PU e durations apenas — CY é exclusivo de cupom > 0."""
    resultado = runner.invoke(
        app,
        ["tesouro", "precificar", "--vencimento", "2029-01-01", "--taxa", "0.118"],
    )
    assert resultado.exit_code == 0
    saida = resultado.stdout
    assert "PU:" in saida
    assert "Duration Mac:" in saida
    assert "Current Yield" not in saida


def test_precificar_data_invalida_erro_ptbr() -> None:
    """Data fora do ISO (15/05/2035 — formato dia/mês/ano que um
    brasileiro digitaria) ⇒ erro pt-BR + exit 1, sem traceback cru; a
    mensagem repete o valor digitado e sugere o formato YYYY-MM-DD."""
    resultado = runner.invoke(
        app,
        [
            "tesouro",
            "precificar",
            "--vencimento",
            "15/05/2035",
            "--taxa",
            "0.062",
            "--cupom",
            "0.06",
        ],
    )
    assert resultado.exit_code == 1
    # saída controlada (typer.Exit vira SystemExit no runner), não a
    # ValueError crua que motivou este teste
    assert isinstance(resultado.exception, SystemExit)
    saida = resultado.stdout
    assert "Data inválida" in saida
    assert "15/05/2035" in saida
    assert "YYYY-MM-DD" in saida


def test_precificar_taxa_percentual_emite_aviso_e_prossegue() -> None:
    """--taxa 6.2 (cara de percentual) ⇒ aviso amarelo de magnitude, sem
    bloquear: exit 0, "decimal" na saída e PU renderizado normalmente."""
    resultado = runner.invoke(
        app,
        ["tesouro", "precificar", "--vencimento", "2035-05-15", "--taxa", "6.2"],
    )
    assert resultado.exit_code == 0
    saida = resultado.stdout
    assert "Aviso" in saida
    assert "decimal" in saida
    assert "PU:" in saida


def test_precificar_vna_com_cupom_imprime_cotacao_pu_metricas_e_cy() -> None:
    """Modo IPCA+ (--vna com --cupom 0.06 = NTN-B): PU pela taxa real,
    linha extra de cotação em % do VNA, durations, DV01, convexidade e
    Current Yield com o cupom em R$ sobre o VNA informado."""
    resultado = runner.invoke(
        app,
        [
            "tesouro",
            "precificar",
            "--vencimento",
            "2035-05-15",
            "--taxa",
            "0.062",
            "--cupom",
            "0.06",
            "--vna",
            "4500.00",
        ],
    )
    assert resultado.exit_code == 0
    saida = resultado.stdout
    assert "PU:" in saida
    assert "Cotação:" in saida
    assert "% do VNA" in saida
    assert "Duration Mac:" in saida
    assert "Duration Mod:" in saida
    assert "DV01:" in saida
    assert "Convexidade:" in saida
    assert "Current Yield:" in saida


def test_precificar_vna_sem_cupom_e_ntnb_principal() -> None:
    """--vna sem --cupom = NTN-B Principal: cotação e PU sem Current Yield
    (CY é exclusivo de cupom > 0, como no caminho sem --vna)."""
    resultado = runner.invoke(
        app,
        [
            "tesouro",
            "precificar",
            "--vencimento",
            "2035-05-15",
            "--taxa",
            "0.062",
            "--vna",
            "4500.00",
        ],
    )
    assert resultado.exit_code == 0
    saida = resultado.stdout
    assert "Cotação:" in saida
    assert "PU:" in saida
    assert "Current Yield" not in saida


def test_precificar_sem_vna_nao_menciona_cotacao_nem_vna() -> None:
    """Sem --vna o caminho é o de sempre (título genérico por valor de
    face): nada de cotação ou VNA na saída — o modo IPCA+ é opt-in."""
    resultado = runner.invoke(
        app,
        [
            "tesouro",
            "precificar",
            "--vencimento",
            "2035-05-15",
            "--taxa",
            "0.062",
            "--cupom",
            "0.06",
        ],
    )
    assert resultado.exit_code == 0
    saida = resultado.stdout
    assert "PU:" in saida
    assert "Cotação:" not in saida
    assert "% do VNA" not in saida


def test_precificar_vna_ignora_valor_nominal_com_aviso() -> None:
    """--vna junto de --valor-nominal: o valor de face não se aplica no
    modo IPCA+ — aviso amarelo, ignorado e exit 0 (não é erro)."""
    resultado = runner.invoke(
        app,
        [
            "tesouro",
            "precificar",
            "--vencimento",
            "2035-05-15",
            "--taxa",
            "0.062",
            "--cupom",
            "0.06",
            "--vna",
            "4500.00",
            "--valor-nominal",
            "100.0",
        ],
    )
    assert resultado.exit_code == 0
    saida = resultado.stdout
    assert "Aviso" in saida
    assert "--valor-nominal" in saida
    assert "Cotação:" in saida  # o modo IPCA+ roda normalmente apesar do aviso


# ----------------------------------------------------------------------
# rfq comparar
# ----------------------------------------------------------------------
def test_comparar_imprime_tabela_liquida_ordenada() -> None:
    """Tabela líquida com os 3 produtos, ordenada pelo líquido desc.

    LCI 10,5% isenta (líquido 10,5%) > CDB 12% e Tesouro 11,8% brutos com
    desconto de IR — a isenta lidera a tabela.
    """
    resultado = runner.invoke(
        app,
        [
            "comparar",
            "--cdb",
            "12.0",
            "--lci",
            "10.5",
            "--tesouro",
            "11.8",
            "--prazo",
            "720",
        ],
    )
    assert resultado.exit_code == 0
    saida = resultado.stdout
    for coluna in ("Taxa bruta", "Taxa líquida", "Equivalente CDB", "Isento"):
        assert coluna in saida
    for produto in ("CDB", "LCI/LCA", "Tesouro"):
        assert produto in saida
    # título traz a alíquota do prazo (720 dias) — fonte única é ir.aliquota
    assert f"IR {ir.aliquota(720):.1%}" in saida
    # disclaimer educacional (Resolução CVM 20/2021) fecha a saída
    assert "não constitui oferta" in saida
    assert "CVM 20/2021" in saida
    # ordenação avaliada nas LINHAS DE DADOS ("CDB" também ocorre no cabeçalho
    # "Equivalente CDB"): primeira linha = LCI/LCA (isenta lidera), depois CDB
    # e Tesouro
    linhas_dados = [
        linha for linha in saida.splitlines() if linha.startswith("│") and "Produto" not in linha
    ]
    assert len(linhas_dados) == 3
    assert "LCI/LCA" in linhas_dados[0]
    assert "CDB" in linhas_dados[1]
    assert "Tesouro" in linhas_dados[2]


def test_comparar_taxa_decimal_emite_aviso_e_prossegue() -> None:
    """Taxa em decimal (0.12 onde se espera 12.0) ⇒ aviso amarelo de
    magnitude, sem bloquear: exit 0, "percentual" na saída e a tabela
    renderiza ("Taxa bruta" presente)."""
    resultado = runner.invoke(
        app,
        ["comparar", "--cdb", "0.12", "--lci", "0.105", "--prazo", "720"],
    )
    assert resultado.exit_code == 0
    saida = resultado.stdout
    assert "Aviso" in saida
    assert "percentual" in saida
    assert "Taxa bruta" in saida


def test_comparar_valores_normais_nao_emitem_aviso() -> None:
    """Valores na convenção esperada (percentual) ⇒ nenhum aviso."""
    resultado = runner.invoke(
        app,
        ["comparar", "--cdb", "12.0", "--lci", "10.5", "--prazo", "720"],
    )
    assert resultado.exit_code == 0
    assert "Aviso" not in resultado.stdout


def test_comparar_cdb_cdi_sem_fonte_de_cdi_erro_ptbr() -> None:
    """--cdb-cdi sem --cdi-auto/--cdi: uso ambíguo rejeitado — erro pt-BR +
    exit 1 apontando as duas fontes possíveis, sem adivinhação."""
    resultado = runner.invoke(app, ["comparar", "--cdb-cdi", "110"])
    assert resultado.exit_code == 1
    saida = resultado.stdout
    assert "% do CDI" in saida
    assert "--cdi-auto" in saida
    assert "--cdi" in saida


def test_comparar_cdb_e_cdb_cdi_unidades_mutuamente_exclusivas() -> None:
    """--cdb e --cdb-cdi juntos: duas unidades para o mesmo produto ⇒
    erro pt-BR + exit 1 (uma unidade por produto)."""
    resultado = runner.invoke(
        app, ["comparar", "--cdb", "12.0", "--cdb-cdi", "110", "--cdi", "13.0"]
    )
    assert resultado.exit_code == 1
    assert "uma única unidade" in resultado.stdout


def test_comparar_fonte_de_cdi_unica() -> None:
    """--cdi-auto com --cdi: duas fontes para o mesmo valor ⇒ erro pt-BR
    + exit 1 (uma única fonte de CDI por execução)."""
    resultado = runner.invoke(app, ["comparar", "--cdb-cdi", "110", "--cdi-auto", "--cdi", "13.0"])
    assert resultado.exit_code == 1
    assert "uma única fonte" in resultado.stdout


def test_comparar_cdi_sem_cdb_cdi_erro_ptbr() -> None:
    """--cdi-auto sem --cdb-cdi: uso sem efeito ⇒ erro pt-BR + exit 1."""
    resultado = runner.invoke(app, ["comparar", "--cdb", "12.0", "--cdi-auto"])
    assert resultado.exit_code == 1
    assert "--cdb-cdi" in resultado.stdout


def test_comparar_incentivada_sem_debenture_erro_ptbr() -> None:
    """--incentivada sem --debenture: uso sem efeito ⇒ erro pt-BR + exit 1."""
    resultado = runner.invoke(app, ["comparar", "--incentivada"])
    assert resultado.exit_code == 1
    assert "--debenture" in resultado.stdout


def test_comparar_cdb_cdi_nao_positivo_erro_ptbr() -> None:
    """--cdb-cdi zero ou negativo: o ValueError do núcleo de conversão não
    escapa como traceback cru — a guarda de entrada rejeita em pt-BR com
    exit 1 antes de qualquer cálculo (SystemExit no runner)."""
    for valor in ("0", "-50"):
        resultado = runner.invoke(app, ["comparar", f"--cdb-cdi={valor}", "--cdi", "13.0"])
        assert resultado.exit_code == 1, valor
        saida = resultado.stdout
        assert "deve ser positivo" in saida
        assert "--cdb-cdi" in saida
        assert isinstance(resultado.exception, SystemExit)


def test_comparar_cdi_nao_positivo_erro_ptbr() -> None:
    """--cdi zero ou negativo: sem faixa mínima o comando prosseguia com um
    CDI sem sentido econômico — a guarda de entrada rejeita em pt-BR com
    exit 1 (SystemExit no runner)."""
    for valor in ("0", "-13.0"):
        resultado = runner.invoke(app, ["comparar", "--cdb-cdi", "110", f"--cdi={valor}"])
        assert resultado.exit_code == 1, valor
        saida = resultado.stdout
        assert "deve ser positivo" in saida
        assert "--cdi" in saida
        assert isinstance(resultado.exception, SystemExit)


@pytest.mark.parametrize("valor", ["0", "-10"])
def test_comparar_prazo_nao_positivo_erro_ptbr(valor: str) -> None:
    """--prazo zero ou negativo: o ValueError do núcleo de IR (ir.aliquota)
    não escapa como traceback cru — a guarda de entrada rejeita em pt-BR com
    exit 1 antes de qualquer cálculo (SystemExit no runner)."""
    resultado = runner.invoke(app, ["comparar", "--cdb", "12.0", f"--prazo={valor}"])
    assert resultado.exit_code == 1, valor
    saida = resultado.stdout
    assert "deve ser positivo" in saida
    assert "--prazo" in saida
    assert isinstance(resultado.exception, SystemExit)


def test_comparar_cdi_auto_sgs_sem_dados_erro_ptbr(monkeypatch, cache_isolado) -> None:
    """SGS sem dados responde 200 + {"erro": ...} — forma de erro real do
    BCB e o provider levanta ValueError: erro pt-BR + exit 1, sem traceback
    cru (espelho do except ValueError de fundos resumo; SystemExit no runner)."""
    monkeypatch.setattr(
        requests,
        "get",
        lambda *args, **kwargs: RespostaFake({"erro": {"statusCode": 404, "name": "Erro"}}),
    )
    resultado = runner.invoke(app, ["comparar", "--cdb-cdi", "110", "--cdi-auto"])
    assert resultado.exit_code == 1
    saida = resultado.stdout
    assert "Erro ao obter o CDI" in saida
    assert "SGS" in saida
    assert isinstance(resultado.exception, SystemExit)


def test_comparar_cdb_cdi_com_cdi_informado_converte_pela_regra_do_nucleo() -> None:
    """--cdb-cdi 110 com --cdi 13.0: anuncia a fonte do CDI e a taxa bruta
    sai da conversão do núcleo (110% × 13% = 14,3% a.a.), não da flag."""
    resultado = runner.invoke(app, ["comparar", "--cdb-cdi", "110", "--cdi", "13.0"])
    assert resultado.exit_code == 0
    saida = resultado.stdout
    assert "CDI (informado): 13.00%" in saida
    assert "14.3000%" in saida


def test_comparar_cdb_cdi_auto_busca_a_serie_sgs(http_fixture_sgs) -> None:
    """--cdi-auto: CDI anual derivado da série SGS/BCB (fixture real
    mockada), fonte anunciada na saída; a taxa do CDB sai de
    cdi_para_taxa_anual sobre o CDI derivado."""
    cdi_anual = taxa_equivalente.cdi_anual_do_provider(
        SGSProvider(), date(2026, 9, 1), date(2026, 9, 30)
    )
    taxa_esperada = taxa_equivalente.cdi_para_taxa_anual(1.10, cdi_anual)
    resultado = runner.invoke(app, ["comparar", "--cdb-cdi", "110", "--cdi-auto"])
    assert resultado.exit_code == 0
    saida = resultado.stdout
    # rótulo derivado do mapa declarado (fontes.py) — "sgs", como nos
    # anúncios "fonte: sgs"/"fonte: cvm" dos demais comandos
    assert "CDI (sgs)" in saida
    assert f"{taxa_esperada:.4%}" in saida


def test_comparar_debenture_incentivada_isenta_por_categoria() -> None:
    """Debênture incentivada: isenção derivada do modelo (tipo + categoria) —
    líquida == bruta, equivalente CDB pela regra do isento e tabela ordenada
    (a isenta lidera o CDB 11% tributado). O rich pode quebrar a célula do
    nome em 2 linhas físicas: a contagem de produtos usa a célula Isento
    (uma célula "sim"/"não" por produto)."""
    resultado = runner.invoke(
        app,
        ["comparar", "--debenture", "10.5", "--incentivada", "--cdb", "11.0", "--prazo", "720"],
    )
    assert resultado.exit_code == 0
    saida = resultado.stdout
    linhas_dados = [
        linha for linha in saida.splitlines() if linha.startswith("│") and "Produto" not in linha
    ]
    produtos = [linha for linha in linhas_dados if " sim " in linha or " não " in linha]
    assert len(produtos) == 2
    assert "Debênture" in produtos[0]
    assert "sim" in produtos[0]  # isenta por categoria (incentivada)
    assert "10.5000%" in produtos[0]  # líquida == bruta (isenta)
    # equivalente CDB do isento: 10.5% / (1 - alíquota do prazo)
    assert f"{0.105 / (1 - ir.aliquota(720)):.4%}" in produtos[0]
    assert "CDB" in produtos[1]


def test_comparar_debenture_comum_e_tributada() -> None:
    """Debênture comum (sem --incentivada): tributada pela régua do prazo —
    líquida = bruta × (1 - alíquota)."""
    resultado = runner.invoke(app, ["comparar", "--debenture", "12.0", "--prazo", "720"])
    assert resultado.exit_code == 0
    saida = resultado.stdout
    linhas_dados = [
        linha for linha in saida.splitlines() if linha.startswith("│") and "Produto" not in linha
    ]
    produtos = [linha for linha in linhas_dados if " sim " in linha or " não " in linha]
    assert len(produtos) == 1
    assert "Debênture" in produtos[0]
    assert "não" in produtos[0]
    assert "12.0000%" in produtos[0]  # bruta
    # líquida = bruta × (1 - alíquota do prazo)
    assert f"{0.12 * (1 - ir.aliquota(720)):.4%}" in produtos[0]


# ----------------------------------------------------------------------
# rfq fundos resumo — offline: informe da CVM por ZIP de fixture real e
# CDI da janela pela série SGS/BCB também de fixture real (sem rede).
# ----------------------------------------------------------------------
def test_fundos_resumo_mostra_os_tres_numeros_e_anuncia_a_fonte(
    http_fixture_fundos,
) -> None:
    """Resumo com os três números do contrato de métricas (acumulada,
    anualizada e % do CDI) e o CNPJ anunciado; a fonte anunciada sai do
    resolvedor (mapa declarado: fundos → CVM)."""
    provider = CVMFundosProvider()
    df = provider.informe_diario(2026, 8, cnpj="00.017.024/0001-53")
    resultado = runner.invoke(
        app, ["fundos", "resumo", "--cnpj", "00.017.024/0001-53", "--mes", "2026-08"]
    )
    assert resultado.exit_code == 0
    saida = resultado.stdout
    assert "fonte: cvm" in saida
    assert "00.017.024/0001-53" in saida
    assert f"{rentabilidade_periodo(df):.4%}" in saida
    assert f"{rentabilidade_anualizada(df):.4%}" in saida
    assert f"{percentual_cdi(df, SGSProvider()):.2%}" in saida
    # disclaimer educacional (Resolução CVM 20/2021) fecha a saída
    assert "não constitui oferta" in saida
    assert "CVM 20/2021" in saida


def test_fundos_resumo_aceita_cnpj_sem_pontuacao(http_fixture_fundos) -> None:
    """CNPJ sem pontuação casa o mesmo fundo (igualdade normalizada do
    provider) e o CNPJ anunciado é o digitado pelo usuário."""
    resultado = runner.invoke(
        app, ["fundos", "resumo", "--cnpj", "00017024000153", "--mes", "2026-08"]
    )
    assert resultado.exit_code == 0
    saida = resultado.stdout
    assert "fonte: cvm" in saida
    assert "00017024000153" in saida
    assert "Rentabilidade anualizada" in saida


def test_fundos_resumo_mes_nao_publicado_erro_ptbr(monkeypatch, cache_isolado) -> None:
    """Mês sem arquivo publicado (HTTP 404): erro de DOMÍNIO distinto de rede —
    mensagem específica do provider ("não está disponível... ainda não ter sido
    publicado") + exit 1, sem traceback cru e sem o achatamento "Falha de
    rede" (mês não publicado não é falha de conexão)."""
    monkeypatch.setattr(requests, "get", lambda *args, **kwargs: RespostaErro())
    resultado = runner.invoke(
        app, ["fundos", "resumo", "--cnpj", "00.017.024/0001-53", "--mes", "2099-08"]
    )
    assert resultado.exit_code == 1
    # saída normalizada: o rich quebra linhas longas a qualquer espaço
    saida_plana = " ".join(resultado.stdout.split())
    assert "não está disponível" in saida_plana
    assert "ainda não ter sido publicado" in saida_plana
    assert "Falha de rede" not in saida_plana
    assert isinstance(resultado.exception, SystemExit)


def test_fundos_resumo_zip_truncado_erro_ptbr(monkeypatch, cache_isolado) -> None:
    """Resposta 200 com corpo que não é ZIP (truncada/corrompida): o
    zipfile.BadZipFile não escapa cru — "Informe ilegível" + exit 1
    (SystemExit no runner)."""
    monkeypatch.setattr(requests, "get", lambda *args, **kwargs: RespostaZip(b"nao-e-um-zip"))
    resultado = runner.invoke(
        app, ["fundos", "resumo", "--cnpj", "00.017.024/0001-53", "--mes", "2026-08"]
    )
    assert resultado.exit_code == 1
    saida = resultado.stdout
    assert "Informe ilegível" in saida
    assert isinstance(resultado.exception, SystemExit)


def test_fundos_resumo_zip_sem_entradas_erro_ptbr(monkeypatch, cache_isolado) -> None:
    """ZIP 200 sem nenhuma entrada (o ValueError "ZIP vazio" do provider):
    erro explícito pt-BR + exit 1, sem traceback cru."""
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w"):
        pass  # ZIP válido com zero entradas
    monkeypatch.setattr(requests, "get", lambda *args, **kwargs: RespostaZip(buffer.getvalue()))
    resultado = runner.invoke(
        app, ["fundos", "resumo", "--cnpj", "00.017.024/0001-53", "--mes", "2026-08"]
    )
    assert resultado.exit_code == 1
    saida = resultado.stdout
    assert "Informe ilegível" in saida
    assert "ZIP vazio" in saida
    assert isinstance(resultado.exception, SystemExit)


def test_fundos_resumo_falha_de_rede_erro_ptbr(monkeypatch, cache_isolado) -> None:
    """Conexão derrubada antes da resposta: falha de rede tratada pt-BR +
    exit 1, com dica acionável e sem traceback cru."""

    def get_fake(*args, **kwargs):
        raise requests.ConnectionError("falha de conexão simulada")

    monkeypatch.setattr(requests, "get", get_fake)
    resultado = runner.invoke(
        app, ["fundos", "resumo", "--cnpj", "00.017.024/0001-53", "--mes", "2026-08"]
    )
    assert resultado.exit_code == 1
    # saída normalizada: o rich quebra linhas longas a qualquer espaço
    saida_plana = " ".join(resultado.stdout.split())
    assert "Falha de rede ao obter o informe da CVM" in saida_plana
    assert "Verifique sua conexão" in saida_plana
    assert isinstance(resultado.exception, SystemExit)


def test_fundos_resumo_mes_invalido_erro_ptbr() -> None:
    """--mes fora do formato AAAA-MM ⇒ erro pt-BR + exit 1, repetindo o
    valor digitado e o formato esperado (sem chegar a rede)."""
    resultado = runner.invoke(
        app, ["fundos", "resumo", "--cnpj", "00.017.024/0001-53", "--mes", "08/2026"]
    )
    assert resultado.exit_code == 1
    saida = resultado.stdout
    assert "Mês inválido" in saida
    assert "08/2026" in saida
    assert "AAAA-MM" in saida
    assert isinstance(resultado.exception, SystemExit)


@pytest.mark.parametrize(
    "cnpj",
    ["", "abc", "00.017.024", "00.017.024/0001-5X"],
    ids=["vazio", "lixo", "raiz_parcial", "digitos_verificadores_letra"],
)
def test_fundos_resumo_cnpj_sem_14_digitos_erro_ptbr(cnpj: str) -> None:
    """--cnpj sem os 14 dígitos (vazio, lixo, parcial, dígito trocado por
    letra): rejeitado na entrada com erro pt-BR + exit 1 — nunca chega ao
    provider, onde o valor falsy imprimiria as métricas do mercado inteiro
    como se fossem o resumo do fundo."""
    resultado = runner.invoke(app, ["fundos", "resumo", "--cnpj", cnpj, "--mes", "2026-08"])
    assert resultado.exit_code == 1, cnpj
    saida = resultado.stdout
    assert "CNPJ inválido" in saida
    assert "14 dígitos" in saida
    assert isinstance(resultado.exception, SystemExit)


def test_fundos_resumo_cnpj_sem_informe_erro_ptbr(http_fixture_fundos) -> None:
    """CNPJ sem linha no informe do mês ⇒ erro pt-BR + exit 1 (o filtro
    normalizado do provider não casa nada e o comando rejeita a série vazia)."""
    resultado = runner.invoke(
        app, ["fundos", "resumo", "--cnpj", "99.999.999/0001-99", "--mes", "2026-08"]
    )
    assert resultado.exit_code == 1
    saida = resultado.stdout
    assert "Nenhum informe" in saida
    assert "99.999.999/0001-99" in saida


# ----------------------------------------------------------------------
# Falha de rede em TODO comando que acessa rede: timeout, HTTP 5xx e DNS,
# injetados no requests.get — mensagem pt-BR + dica acionável + exit ≠ 0,
# sem traceback cru. O comando de lote local não participa: lê um arquivo
# do usuário e não consulta nenhuma fonte de rede.
# ----------------------------------------------------------------------
COMANDOS_COM_REDE: dict[str, list[str]] = {
    "listar": ["tesouro", "listar"],
    "comparar": ["comparar", "--cdb-cdi", "110", "--cdi-auto"],
    "fundos": ["fundos", "resumo", "--cnpj", "00.017.024/0001-53", "--mes", "2026-08"],
}


@pytest.mark.parametrize(
    ("nome_comando", "excecao"),
    [
        (comando, excecao)
        for comando in COMANDOS_COM_REDE
        for excecao in (
            requests.Timeout("Read timed out"),
            requests.HTTPError("500 Server Error: Internal Server Error"),
            requests.ConnectionError("Name or service not known"),
        )
    ],
    ids=[
        f"{comando}-{causa}"
        for comando in COMANDOS_COM_REDE
        for causa in ("timeout", "http_5xx", "dns")
    ],
)
def test_falha_de_rede_em_todo_comando_com_rede(
    monkeypatch, cache_isolado, nome_comando: str, excecao: Exception
) -> None:
    """Comando × (timeout, HTTP 5xx, DNS): exit ≠ 0, mensagem pt-BR com a
    dica acionável e nenhum traceback cru (a exceção vira SystemExit)."""

    def get_fake(*args, **kwargs):
        raise excecao

    monkeypatch.setattr(requests, "get", get_fake)
    resultado = runner.invoke(app, COMANDOS_COM_REDE[nome_comando])
    assert resultado.exit_code == 1
    # saída normalizada: o rich quebra linhas longas a qualquer espaço
    saida_plana = " ".join(resultado.stdout.split())
    assert "Falha de rede ao" in saida_plana
    assert "Verifique sua conexão" in saida_plana
    assert isinstance(resultado.exception, SystemExit)
