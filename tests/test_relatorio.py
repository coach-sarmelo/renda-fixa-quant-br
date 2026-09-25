"""Testes do relatório determinístico.

`rfquant/relatorio.py` gera Markdown determinístico, sem LLM e sem
`rfquant.ai` no grafo de imports. O teste de contrato lê o texto
dos arquivos-fonte para manter a fronteira determinístico/IA no código, não só em runtime.
"""

from __future__ import annotations

from datetime import date
from pathlib import Path

from typer.testing import CliRunner

from rfquant import relatorio
from rfquant.cli import app

SRC_RFQUANT = Path(__file__).resolve().parents[1] / "src" / "rfquant"
runner = CliRunner()

DADOS = {
    "data": date(2026, 9, 20),
    "carteira": [
        {"ativo": "Tesouro Selic 2029", "peso": 0.30, "classe": "selic"},
        {"ativo": "Tesouro IPCA+ 2035", "peso": 0.40, "classe": "ipca+"},
    ],
    "métricas": {"duration_media_anos": 3.2, "concentracao_max_emissor": 0.40},
}


# ----------------------------------------------------------------------
# Determinismo e conteúdo
# ----------------------------------------------------------------------
def test_gerar_offline_mesma_entrada_mesmo_markdown() -> None:
    """Mesmo dict de entrada => mesmo Markdown em 2 chamadas.

    O único dado de relógio é `date.today()` no cabeçalho — duas chamadas
    no mesmo dia produzem saída byte a byte idêntica. A data embutida em
    DADOS serializa para "2026-09-20" (date -> isoformat em _serializar).
    """
    primeiro = relatorio.gerar_offline(DADOS)
    segundo = relatorio.gerar_offline(DADOS)
    assert primeiro == segundo
    assert primeiro.startswith("# Relatório de Carteira de Renda Fixa")
    assert "2026-09-20" in primeiro  # date serializada, não repr(dataclass)


def test_conteudo_termina_com_disclaimer_do_modulo() -> None:
    """O relatório termina com o disclaimer da constante do módulo.

    O texto esperado vem de relatorio.DISCLAIMER_PADRAO — o teste não
    inventa o texto regulatório.
    """
    conteudo = relatorio.gerar_offline(DADOS)
    assert conteudo.strip().endswith(f"> **Disclaimer.** {relatorio.DISCLAIMER_PADRAO}")
    assert "Resolução CVM nº 20/2021" in conteudo


def test_salvar_escreve_o_arquivo(tmp_path: Path) -> None:
    """salvar() cria diretórios pais e escreve o conteúdo em utf-8."""
    conteudo = relatorio.gerar_offline(DADOS)
    destino = tmp_path / "sub" / "relatorio.md"
    relatorio.salvar(conteudo, str(destino))
    assert destino.read_text(encoding="utf-8") == conteudo


def test_lista_de_dicts_vira_tabela_markdown_sem_repr() -> None:
    """Seção lista de dicts vira tabela Markdown — sem repr cru de dict.

    Correção cosmética pós-demo: '- {'ativo': ...}' virou tabela cujo
    cabeçalho vem das chaves do primeiro item (ordem de inserção,
    determinística). Títulos de seção carregam o acento da própria chave
    (métricas -> "## Métricas" via .title()).
    """
    conteudo = relatorio.gerar_offline(DADOS)
    assert "| ativo | peso | classe |" in conteudo
    assert "| --- | --- | --- |" in conteudo
    assert "| Tesouro Selic 2029 | 0.3 | selic |" in conteudo
    assert "{'ativo'" not in conteudo
    assert "## Métricas" in conteudo


# ----------------------------------------------------------------------
# CLI (caminho determinístico sempre offline)
# ----------------------------------------------------------------------
def test_cli_gerar_produve_markdown_com_disclaimer(tmp_path: Path) -> None:
    """`rfq relatorio gerar --output`: exit 0 e arquivo com disclaimer."""
    destino = tmp_path / "r.md"
    resultado = runner.invoke(app, ["relatorio", "gerar", "--output", str(destino)])
    assert resultado.exit_code == 0
    assert "Relatório salvo em" in resultado.stdout
    assert "Resolução CVM nº 20/2021" in destino.read_text(encoding="utf-8")


def test_cli_no_offline_falha_com_erro_claro(tmp_path: Path) -> None:
    """`--no-offline`: exit 1 com erro claro — não há narrativa por LLM.

    A narrativa por LLM não está disponível — o comando falha sem
    substituição silenciosa e sem escrever arquivo.
    """
    destino = tmp_path / "r.md"
    resultado = runner.invoke(app, ["relatorio", "gerar", "--no-offline", "--output", str(destino)])
    assert resultado.exit_code == 1
    assert "LLM" in resultado.stdout
    assert "offline" in resultado.stdout.lower()
    assert not destino.exists()


# ----------------------------------------------------------------------
# Contrato da fronteira determinístico/IA (CI-enforced)
# ----------------------------------------------------------------------
def test_contrato_sem_ia_no_codigo_deterministico() -> None:
    """Contrato da fronteira determinístico/IA: o código determinístico
    (relatorio.py, cli.py) não referencia `openai` nem `rfquant.ai` —
    nem para importar, nem disfarçado em comentário.
    """
    assert not (SRC_RFQUANT / "ai" / "relatorio.py").exists()

    texto_relatorio = (SRC_RFQUANT / "relatorio.py").read_text(encoding="utf-8")
    texto_cli = (SRC_RFQUANT / "cli.py").read_text(encoding="utf-8")
    for texto in (texto_relatorio, texto_cli):
        assert "import openai" not in texto
        assert "rfquant.ai" not in texto
