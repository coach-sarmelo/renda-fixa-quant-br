"""Testes de CLI com CliRunner.

`listar --fonte=oficial` roda sem rede: o HTTP do stub é mockado com a
fixture REAL capturada do endpoint oficial (`tesouro_oficial_sample.csv`), cache
isolado em tmp. `precificar` e `comparar` são matemática pura.

Comportamento existente — estes testes o fixam como contrato
(caracterização): primeira execução verde é o esperado.
"""

from __future__ import annotations

import pytest
import requests
from conftest import RespostaFake
from test_data_tesouro_oficial import _fixture_real
from typer.testing import CliRunner

from rfquant.cli import app
from rfquant.comparison import ir
from rfquant.config import settings

runner = CliRunner()


@pytest.fixture
def http_fixture_real(monkeypatch, cache_isolado) -> None:
    """GET do stub oficial responde com a fixture real; cache em tmp."""
    monkeypatch.setattr(
        requests, "get", lambda *args, **kwargs: RespostaFake({}, texto=_fixture_real())
    )
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
    resultado = runner.invoke(
        app, ["tesouro", "listar", "--fonte=oficial", "--limite", "200"]
    )
    assert resultado.exit_code == 0
    saida = resultado.stdout
    assert "Tesouro Direto" in saida  # título da tabela
    assert "Nome" in saida and "Taxa compra" in saida and "PU compra" in saida
    assert "Tesouro Selic" in saida  # nome real da fixture (18/09/2026)


def test_listar_com_tipo_filtra_a_tabela(http_fixture_real) -> None:
    """--tipo Selic deixa só Selic: IPCA+/Prefixado não aparecem."""
    resultado = runner.invoke(
        app, ["tesouro", "listar", "--fonte=oficial", "--tipo", "Selic"]
    )
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
    # ordenação avaliada nas LINHAS DE DADOS ("CDB" também ocorre no cabeçalho
    # "Equivalente CDB"): primeira linha = LCI/LCA (isenta lidera), depois CDB
    # e Tesouro
    linhas_dados = [
        linha
        for linha in saida.splitlines()
        if linha.startswith("│") and "Produto" not in linha
    ]
    assert len(linhas_dados) == 3
    assert "LCI/LCA" in linhas_dados[0]
    assert "CDB" in linhas_dados[1]
    assert "Tesouro" in linhas_dados[2]


