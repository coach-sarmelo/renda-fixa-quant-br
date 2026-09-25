"""Interface de linha de comando (CLI) do Renda Fixa Quant BR.

Uso:
    rfq tesouro listar --tipo IPCA+
    rfq tesouro listar --fonte=oficial   (sem BRAPI_TOKEN)
    rfq tesouro precificar --vencimento 2035-05-15 --taxa 0.062 --cupom 0.06
    rfq comparar --cdb 12.0 --lci 10.5 --prazo 720
    rfq relatorio gerar --output relatorio.md
"""

from __future__ import annotations

from datetime import date
from pathlib import Path
from typing import Annotated

import typer
from rich.console import Console
from rich.table import Table

from rfquant import __version__
from rfquant.comparison import ir, taxa_equivalente
from rfquant.config import settings
from rfquant.data import TesouroDiretoProvider, TesouroOficialProvider
from rfquant.data.base import DataProvider
from rfquant.pricing import current_yield, duration, pu

app = typer.Typer(
    name="rfq",
    help="Renda Fixa Quant BR — análise quantitativa de renda fixa brasileira.",
    no_args_is_help=True,
    add_completion=False,
)
console = Console()

tesouro_app = typer.Typer(help="Comandos do Tesouro Direto.")
relatorio_app = typer.Typer(help="Comandos de relatório.")
app.add_typer(tesouro_app, name="tesouro")
app.add_typer(relatorio_app, name="relatorio")

# ----------------------------------------------------------------------
# Top-level
# ----------------------------------------------------------------------
@app.command()
def version() -> None:
    """Mostra a versão do pacote."""
    console.print(f"rfquant [bold cyan]{__version__}[/]")

# ----------------------------------------------------------------------
# Tesouro Direto
# ----------------------------------------------------------------------
def _escolher_fonte(fonte: str) -> DataProvider:
    """Instancia o provider da fonte pedida — sem substituição silenciosa.

    `--fonte=brapi` sem BRAPI_TOKEN falha aqui com mensagem explícita e
    exit 1; nunca cai para outra fonte por conta própria.
    """
    if fonte == "oficial":
        return TesouroOficialProvider()
    if fonte == "brapi":
        if not settings.brapi_token:
            console.print(
                "[red]BRAPI_TOKEN ausente ou inválido.[/] "
                "Configure-o no .env (veja .env.example) ou use "
                "[cyan]--fonte=oficial[/] (não requer token)."
            )
            raise typer.Exit(code=1)
        return TesouroDiretoProvider()
    console.print(
        f"[red]Fonte '{fonte}' desconhecida.[/] Use --fonte=brapi ou --fonte=oficial."
    )
    raise typer.Exit(code=1)


@tesouro_app.command("listar")
def tesouro_listar(
    tipo: Annotated[str | None, typer.Option(help="Filtra por tipo: IPCA+, Prefixado, Selic")] = None,
    limite: Annotated[int, typer.Option(help="Número máximo de resultados")] = 50,
    fonte: Annotated[str, typer.Option(help="Fonte: brapi (requer BRAPI_TOKEN) | oficial (sem token)")] = "brapi",
) -> None:
    """Lista os títulos do Tesouro Direto disponíveis."""
    provider = _escolher_fonte(fonte)
    df = provider.titulos_disponiveis()
    if df.empty:
        console.print("[yellow]Nenhum título retornado.[/]")
        raise typer.Exit(code=1)

    if tipo:
        df = df[df["tipo"].str.lower() == tipo.lower()]

    tabela = Table(title=f"Tesouro Direto — {date.today().isoformat()}")
    tabela.add_column("Nome", style="cyan")
    tabela.add_column("Tipo")
    tabela.add_column("Vencimento")
    tabela.add_column("Taxa compra", justify="right")
    tabela.add_column("PU compra", justify="right")

    for _, row in df.head(limite).iterrows():
        taxa = row.get("taxa_compra")
        pu_v = row.get("pu_compra")
        tabela.add_row(
            str(row["nome"]),
            str(row["tipo"]),
            str(row["vencimento"]),
            f"{float(taxa):.4%}" if taxa is not None else "-",
            f"R$ {float(pu_v):,.2f}" if pu_v is not None else "-",
        )
    console.print(tabela)

@tesouro_app.command("precificar")
def tesouro_precificar(
    vencimento: Annotated[str, typer.Option(help="Data de vencimento (YYYY-MM-DD)")],
    taxa: Annotated[float, typer.Option(help="Taxa anual em decimal (ex: 0.06 = 6%)")],
    valor_nominal: Annotated[float, typer.Option(help="Valor de face")] = 1000.0,
    cupom: Annotated[float, typer.Option(help="Cupom anual (0 = zero-cupom)")] = 0.0,
) -> None:
    """Precifica um título genérico de renda fixa."""
    try:
        venc = date.fromisoformat(vencimento)
    except ValueError:
        console.print(
            f"[red]Data inválida:[/] '{vencimento}'. "
            "Use o formato YYYY-MM-DD (ex.: 2035-05-15)."
        )
        raise typer.Exit(code=1) from None
    hoje = date.today()

    p = pu.calcular(hoje, venc, taxa, valor_nominal=valor_nominal, taxa_cupom_anual=cupom)
    d_mac = duration.macaulay(hoje, venc, taxa, valor_nominal=valor_nominal, taxa_cupom_anual=cupom)
    d_mod = duration.modificada(hoje, venc, taxa, valor_nominal=valor_nominal, taxa_cupom_anual=cupom)

    console.print(f"[bold]PU:[/]              R$ {p:,.2f}")
    console.print(f"[bold]Duration Mac:[/]   {d_mac:.4f} anos")
    console.print(f"[bold]Duration Mod:[/]   {d_mod:.4f}")

    if cupom > 0:
        cy = current_yield.calcular(cupom * valor_nominal, p)
        console.print(f"[bold]Current Yield:[/]  {cy:.4%}")

# ----------------------------------------------------------------------
# Comparação
# ----------------------------------------------------------------------
@app.command()
def comparar(
    cdb: Annotated[float | None, typer.Option(help="Taxa bruta do CDB em % a.a.")] = None,
    lci: Annotated[float | None, typer.Option(help="Taxa da LCI/LCA em % a.a.")] = None,
    tesouro: Annotated[float | None, typer.Option(help="Taxa do Tesouro em % a.a.")] = None,
    prazo: Annotated[int, typer.Option(help="Prazo em dias corridos")] = 720,
) -> None:
    """Compara produtos de renda fixa pelo líquido de IR."""
    produtos: list[taxa_equivalente.ProdutoRF] = []
    if cdb is not None:
        produtos.append(taxa_equivalente.ProdutoRF("CDB", cdb / 100, prazo, isento=False))
    if lci is not None:
        produtos.append(taxa_equivalente.ProdutoRF("LCI/LCA", lci / 100, prazo, isento=True))
    if tesouro is not None:
        produtos.append(taxa_equivalente.ProdutoRF("Tesouro", tesouro / 100, prazo, isento=False))

    if not produtos:
        console.print("[yellow]Informe ao menos um produto.[/]")
        raise typer.Exit(code=1)

    resultados = taxa_equivalente.comparar(produtos)

    tabela = Table(title=f"Comparação — prazo {prazo} dias — IR {ir.aliquota(prazo):.1%}")
    tabela.add_column("Produto", style="cyan")
    tabela.add_column("Taxa bruta", justify="right")
    tabela.add_column("Taxa líquida", justify="right")
    tabela.add_column("Equivalente CDB", justify="right")
    tabela.add_column("Isento")

    for r in resultados:
        tabela.add_row(
            r.produto.nome,
            f"{r.produto.taxa_anual:.4%}",
            f"{r.taxa_liquida_anual:.4%}",
            f"{r.equivalente_cdb:.4%}",
            "sim" if r.produto.isento else "não",
        )
    console.print(tabela)

# ----------------------------------------------------------------------
# Carteira
# ----------------------------------------------------------------------


# ----------------------------------------------------------------------
# Relatório
# ----------------------------------------------------------------------
@relatorio_app.command("gerar")
def relatorio_gerar(
    output: Annotated[Path, typer.Option(help="Caminho do arquivo de saída")] = Path("relatorio.md"),
    offline: Annotated[bool, typer.Option(help="Gera sem LLM (único caminho disponível)")] = True,
) -> None:
    """Gera um relatório de carteira de exemplo (determinístico, sem LLM)."""
    from rfquant import relatorio

    if not offline:
        console.print(
            "[red]Narrativa por LLM não está disponível.[/] O relatório é "
            "sempre determinístico; por ora use o caminho offline (padrão)."
        )
        raise typer.Exit(code=1)

    dados = {
        "data": date.today().isoformat(),
        "carteira": [
            {"ativo": "Tesouro Selic 2029", "peso": 0.30, "taxa": 0.11, "classe": "selic"},
            {"ativo": "Tesouro IPCA+ 2035", "peso": 0.40, "taxa": 0.062, "classe": "ipca+"},
            {"ativo": "CDB AAA 3 anos", "peso": 0.20, "taxa": 0.12, "classe": "prefixado"},
            {"ativo": "LCI 2 anos", "peso": 0.10, "taxa": 0.10, "classe": "ipca+"},
        ],
        "métricas": {
            "duration_media_anos": 3.2,
            "liquidez_d0_d1_pct": 0.30,
            "concentracao_max_emissor": 0.40,
        },
    }

    conteudo = relatorio.gerar_offline(dados)

    relatorio.salvar(conteudo, str(output))
    console.print(f"[green]Relatório salvo em:[/] {output}")

# ----------------------------------------------------------------------
# Atalho de conveniência
# ----------------------------------------------------------------------
@app.command("hoje")
def resumo_hoje() -> None:
    """Mostra um resumo rápido do Tesouro Direto de hoje."""
    console.print(f"[bold]Tesouro Direto — {date.today().isoformat()}[/]\n")
    try:
        # fonte oficial: 'rfq hoje' funciona sem BRAPI_TOKEN
        tesouro_listar(tipo=None, limite=10, fonte="oficial")
    except Exception as e:
        console.print(f"[red]Erro ao buscar dados:[/] {e}")

if __name__ == "__main__":
    app()
