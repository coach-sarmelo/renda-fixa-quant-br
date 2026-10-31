"""Testes de reprodução e regressão para bugs identificados (TDD).

Cobre:
    - BUG-001: Graceful error handling in rfq tesouro precificar (no raw tracebacks).
    - BUG-002: IOF on non-positive rendimento returns 0.0.
    - BUG-003: ETTJ validation of non-positive and duplicate (non-strictly increasing) prazos.
    - BUG-004: Fisher relation and rate conversions validation of extreme/negative rates.
    - BUG-005: Validation of CDI > 0 in cdi_para_taxa_anual.
    - BUG-006: Validation of valor_nominal > 0 in fluxo_caixa.
    - BUG-007: Safe handling of empty fluxos in fluxos_liquidados.
    - BUG-008: Clear Portuguese error diagnostic when YTM root bracketing fails.
    - BUG-009: User-Agent header in Tesouro providers.
    - BUG-010: Date range validation (inicio <= fim) in SGS and Tesouro providers.
    - BUG-011: Relatorio _tabela handles heterogeneous dicts and serializes Decimal.
    - BUG-012: Resilience and validation in current_yield (negative coupon).
    - BUG-013: typer.Exit preservation in rfq hoje.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest
import requests
import typer
from conftest import RespostaFake
from typer.testing import CliRunner

from rfquant import cli, relatorio
from rfquant.cli import app
from rfquant.comparison import ir, taxa_equivalente
from rfquant.data import SGSProvider, TesouroOficialProvider
from rfquant.pricing import current_yield, curva_juros, fluxo_caixa, pu, ytm

runner = CliRunner()


# ----------------------------------------------------------------------
# BUG-001: rfq tesouro precificar graceful error handling
# ----------------------------------------------------------------------
def test_cli_precificar_data_passada_sem_traceback() -> None:
    """Precificar com vencimento anterior ou igual a hoje deve sair com exit 1 e sem traceback."""
    resultado = runner.invoke(
        app, ["tesouro", "precificar", "--vencimento", "2020-01-01", "--taxa", "0.06"]
    )
    assert resultado.exit_code == 1
    assert "Erro ao precificar:" in resultado.stdout
    assert "Traceback" not in resultado.stdout


def test_cli_precificar_taxa_invalida_sem_traceback() -> None:
    """Taxa <= -100% deve emitir mensagem tratada em pt-BR e exit 1."""
    resultado = runner.invoke(
        app, ["tesouro", "precificar", "--vencimento", "2035-05-15", "--taxa", "-1.5"]
    )
    assert resultado.exit_code == 1
    assert "Erro ao precificar:" in resultado.stdout
    assert "Traceback" not in resultado.stdout


def test_cli_precificar_cupom_negativo_sem_traceback() -> None:
    """Cupom negativo deve ser tratado sem traceback."""
    resultado = runner.invoke(
        app,
        [
            "tesouro",
            "precificar",
            "--vencimento",
            "2035-05-15",
            "--taxa",
            "0.06",
            "--cupom",
            "-0.02",
        ],
    )
    assert resultado.exit_code == 1
    assert "Erro ao precificar:" in resultado.stdout
    assert "Traceback" not in resultado.stdout


def test_cli_precificar_vna_invalido_sem_traceback() -> None:
    """VNA <= 0 deve ser tratado com mensagem limpa."""
    resultado = runner.invoke(
        app,
        [
            "tesouro",
            "precificar",
            "--vencimento",
            "2035-05-15",
            "--taxa",
            "0.06",
            "--vna",
            "-100.0",
        ],
    )
    assert resultado.exit_code == 1
    assert "Erro ao precificar:" in resultado.stdout
    assert "Traceback" not in resultado.stdout


# ----------------------------------------------------------------------
# BUG-002: IOF em rendimento não-positivo
# ----------------------------------------------------------------------
def test_iof_rendimento_negativo_ou_zero() -> None:
    """IOF sobre rendimento <= 0 deve ser 0.0 (nunca negativo)."""
    assert ir.iof(0.0, 5) == 0.0
    assert ir.iof(-100.0, 5) == 0.0
    resultado = ir.calcular(-50.0, 10)
    assert resultado.iof == 0.0
    assert resultado.ir == 0.0
    assert resultado.rendimento_liquido == -50.0


# ----------------------------------------------------------------------
# BUG-003: ETTJ validação de prazos estritamente positivos e crescentes
# ----------------------------------------------------------------------
def test_ettj_rejeita_prazos_duplicados() -> None:
    """Vértices com prazos iguais causariam divisão por zero no flat-forward."""
    with pytest.raises(ValueError, match="estritamente crescentes"):
        curva_juros.ETTJ([(1.0, 0.10), (1.0, 0.12)])


def test_ettj_rejeita_prazos_nao_positivos() -> None:
    """Prazos <= 0 são inválidos em ETTJ."""
    with pytest.raises(ValueError, match="Prazos devem ser positivos"):
        curva_juros.ETTJ([(0.0, 0.10), (1.0, 0.12)])
    with pytest.raises(ValueError, match="Prazos devem ser positivos"):
        curva_juros.ETTJ([(-0.5, 0.10), (1.0, 0.12)])


# ----------------------------------------------------------------------
# BUG-004: Fisher e conversões com taxas extremas / negativas
# ----------------------------------------------------------------------
def test_fisher_rejeita_ipca_esperado_menor_ou_igual_menos_cem() -> None:
    """IPCA esperado <= -100% causa divisão por zero ou nonsense econômico."""
    with pytest.raises(ValueError, match="maior que -100%"):
        taxa_equivalente.pre_para_ipca_mais(0.10, -1.0)
    with pytest.raises(ValueError, match="maior que -100%"):
        taxa_equivalente.pre_para_ipca_mais(0.10, -1.2)
    with pytest.raises(ValueError, match="maior que -100%"):
        curva_juros.taxa_pre_para_pos(0.10, -1.0)
    with pytest.raises(ValueError, match="maior que -100%"):
        curva_juros.taxa_pos_para_pre(0.10, -1.0)


def test_taxa_efetiva_para_nominal_rejeita_menor_que_menos_cem() -> None:
    """Taxa efetiva <= -100% levantaria erro de exponenciação fracionária."""
    with pytest.raises(ValueError, match="maior que -100%"):
        curva_juros.taxa_efetiva_para_nominal(-1.5, 2)


# ----------------------------------------------------------------------
# BUG-005: cdi_para_taxa_anual valida cdi_anual > 0
# ----------------------------------------------------------------------
def test_cdi_para_taxa_anual_valida_cdi_positivo() -> None:
    """cdi_para_taxa_anual deve exigir CDI positivo assim como taxa_anual_para_cdi."""
    with pytest.raises(ValueError, match="CDI deve ser positivo"):
        taxa_equivalente.cdi_para_taxa_anual(1.10, 0.0)
    with pytest.raises(ValueError, match="CDI deve ser positivo"):
        taxa_equivalente.cdi_para_taxa_anual(1.10, -0.05)


# ----------------------------------------------------------------------
# BUG-006: fluxo_caixa valida valor_nominal > 0
# ----------------------------------------------------------------------
def test_gerar_fluxos_valida_valor_nominal_positivo() -> None:
    """Valor nominal deve ser positivo."""
    with pytest.raises(ValueError, match="Valor nominal deve ser positivo"):
        fluxo_caixa.gerar_fluxos(date(2026, 1, 1), date(2027, 1, 1), valor_nominal=0.0)
    with pytest.raises(ValueError, match="Valor nominal deve ser positivo"):
        fluxo_caixa.gerar_fluxos(date(2026, 1, 1), date(2027, 1, 1), valor_nominal=-1000.0)


def test_cupom_periodo_valida_valor_nominal_positivo() -> None:
    """cupom_periodo deve exigir valor_nominal > 0."""
    with pytest.raises(ValueError, match="Valor nominal deve ser positivo"):
        fluxo_caixa.cupom_periodo(0.0, 0.06, 2)


# ----------------------------------------------------------------------
# BUG-007: fluxos_liquidados seguro com lista vazia
# ----------------------------------------------------------------------
def test_fluxos_liquidados_com_lista_vazia() -> None:
    """Lista vazia de fluxos deve retornar lista vazia sem estourar max()."""
    assert pu.fluxos_liquidados([], date(2026, 1, 1)) == []


# ----------------------------------------------------------------------
# BUG-008: ytm mensagem amigável em pt-BR quando bracket falha
# ----------------------------------------------------------------------
def test_ytm_bracket_invalido_mensagem_amigavel() -> None:
    """Quando o PU de mercado não pode ser casado com os fluxos, levanta ValueError amigável."""
    with pytest.raises(ValueError, match="Não foi possível encontrar a YTM"):
        ytm.calcular(
            pu_mercado=999999999.0,
            data_compra=date(2026, 1, 1),
            data_vencimento=date(2027, 1, 1),
            valor_nominal=100.0,
        )


# ----------------------------------------------------------------------
# BUG-009: User-Agent explícito nos providers de Tesouro
# ----------------------------------------------------------------------
def test_tesouro_oficial_usa_user_agent(monkeypatch, cache_isolado) -> None:
    """TesouroOficialProvider deve enviar User-Agent explícito do rfquant nas requisições HTTP."""
    cabecalhos_capturados = {}

    def fake_get(url, **kwargs):
        cabecalhos_capturados.update(kwargs.get("headers", {}))
        return RespostaFake(
            {},
            texto=(
                "Tipo Titulo;Data Vencimento;Data Base;Taxa Compra Manha;Taxa Venda Manha;"
                "PU Compra Manha;PU Venda Manha;PU Base Manha\n"
                "Tesouro Selic;01/03/2029;18/09/2026;0,07;0,08;14520,35;14510,10;14510,10\n"
            ),
        )

    monkeypatch.setattr(requests, "get", fake_get)
    provider = TesouroOficialProvider(csv_url="http://fake-tesouro.gov.br/csv")
    provider.titulos_disponiveis()
    assert "User-Agent" in cabecalhos_capturados
    assert "rfquant" in cabecalhos_capturados["User-Agent"]


# ----------------------------------------------------------------------
# BUG-010: Validação de datas inicio <= fim nos providers
# ----------------------------------------------------------------------
def test_sgs_valida_inicio_anterior_ou_igual_fim() -> None:
    """SGSProvider.serie_diaria deve validar inicio <= fim."""
    provider = SGSProvider()
    with pytest.raises(ValueError, match="Data inicial deve ser anterior ou igual à data final"):
        provider.serie_diaria(date(2026, 12, 31), date(2026, 1, 1))


def test_tesouro_oficial_historico_valida_inicio_fim() -> None:
    """TesouroOficialProvider.historico_taxas deve validar inicio <= fim."""
    provider = TesouroOficialProvider()
    with pytest.raises(ValueError, match="Data inicial deve ser anterior ou igual à data final"):
        provider.historico_taxas("Tesouro Prefixado 2026", date(2026, 12, 31), date(2026, 1, 1))


# ----------------------------------------------------------------------
# BUG-011: Relatório suporta dicts heterogêneos e Decimal
# ----------------------------------------------------------------------
def test_relatorio_tabela_chaves_heterogeneas() -> None:
    """A tabela Markdown deve incluir chaves presentes mesmo que não estejam no primeiro item."""
    linhas = relatorio._tabela([{"a": 1}, {"a": 2, "b": 3}])
    assert "b" in linhas[0]


def test_relatorio_serializar_decimal() -> None:
    """Decimal deve ser serializado para float para exibição limpa."""
    serializado = relatorio._serializar({"taxa": Decimal("0.125")})
    assert isinstance(serializado["taxa"], float)
    assert serializado["taxa"] == 0.125


# ----------------------------------------------------------------------
# BUG-012: Current yield valida cupom não-negativo
# ----------------------------------------------------------------------
def test_current_yield_valida_cupom_nao_negativo() -> None:
    """Cupom anual não pode ser negativo."""
    with pytest.raises(ValueError, match="Cupom anual não pode ser negativo"):
        current_yield.calcular(-50.0, 1000.0)


# ----------------------------------------------------------------------
# BUG-013: CLI resumo_hoje não engole typer.Exit
# ----------------------------------------------------------------------
def test_cli_resumo_hoje_repropaga_typer_exit(monkeypatch) -> None:
    """Se a listagem falha com exit 1, 'rfq hoje' deve preservar exit code 1."""

    def falhar_listar(*args, **kwargs):
        raise typer.Exit(code=1)

    monkeypatch.setattr(cli, "tesouro_listar", falhar_listar)
    resultado = runner.invoke(app, ["hoje"])
    assert resultado.exit_code == 1
    assert "Erro ao buscar dados: 1" not in resultado.stdout
