"""Interface de linha de comando (CLI) do Renda Fixa Quant BR.

Uso:
    rfq tesouro listar --tipo IPCA+
    rfq tesouro listar --fonte=oficial   (sem BRAPI_TOKEN)
    rfq tesouro precificar --vencimento 2035-05-15 --taxa 0.062 --cupom 0.06
    rfq comparar --cdb 12.0 --lci 10.5 --prazo 720
    rfq fundos resumo --cnpj 00.017.024/0001-53 --mes 2026-08
    rfq relatorio gerar --output relatorio.md
"""

from __future__ import annotations

import re
import zipfile
from datetime import date, datetime, timedelta
from decimal import Decimal
from pathlib import Path
from typing import Annotated, NoReturn

import requests
import typer
from rich.console import Console
from rich.table import Table

from rfquant import __version__
from rfquant.comparison import ir, taxa_equivalente
from rfquant.config import settings
from rfquant.data import TesouroDiretoProvider, TesouroOficialProvider, Titulo
from rfquant.data.base import DataProvider
from rfquant.data.cvm_fundos import (
    InformeNaoDisponivel,
    RedeIndisponivel,
    percentual_cdi,
    rentabilidade_anualizada,
    rentabilidade_periodo,
)
from rfquant.data.fontes import provider_do_dado, rotulo_do_provider
from rfquant.pricing import current_yield, duration, pu, risco
from rfquant.pricing.fluxo_caixa import cupom_periodo

app = typer.Typer(
    name="rfq",
    help="Renda Fixa Quant BR — análise quantitativa de renda fixa brasileira.",
    no_args_is_help=True,
    add_completion=False,
)
console = Console()

tesouro_app = typer.Typer(help="Comandos do Tesouro Direto.")
fundos_app = typer.Typer(help="Comandos de fundos de investimento.")
relatorio_app = typer.Typer(help="Comandos de relatório.")
app.add_typer(tesouro_app, name="tesouro")
app.add_typer(fundos_app, name="fundos")
app.add_typer(relatorio_app, name="relatorio")


# ----------------------------------------------------------------------
# Top-level
# ----------------------------------------------------------------------
@app.command()
def version() -> None:
    """Mostra a versão do pacote."""
    console.print(f"rfquant [bold cyan]{__version__}[/]")


def _falha_de_rede(contexto: str, erro: Exception) -> NoReturn:
    """Tratamento uniforme de falha de rede (timeout, HTTP 5xx, DNS) nos
    comandos que acessam rede: mensagem pt-BR com o detalhe da fonte, dica
    acionável e exit 1 — nenhum traceback cru chega ao usuário.

    O detalhe da exceção é sanitizado antes da impressão: a mensagem do
    requests embute a URL completa da requisição e, na fonte brapi, o
    token viaja na query — o parâmetro `token=` sai da mensagem.
    """
    detalhe = re.sub(r"([?&])token=[^&\s)]+", r"\1token=***", str(erro))
    console.print(
        f"[red]Falha de rede ao {contexto}:[/] {detalhe}. "
        "Verifique sua conexão e tente novamente; se persistir, a fonte pode "
        "estar indisponível no momento."
    )
    raise typer.Exit(code=1) from None


# ----------------------------------------------------------------------
# Tesouro Direto
# ----------------------------------------------------------------------
def _escolher_fonte(fonte: str) -> tuple[DataProvider, str]:
    """Resolve a fonte dos títulos e o rótulo do anúncio ("fonte: <rótulo>").

    `auto` (default) consulta o mapa declarado de rfquant.data.fontes
    (títulos → oficial): decisão única e determinística — brapi fica fora
    do mapa, com ou sem BRAPI_TOKEN no ambiente o resultado é o mesmo.
    `oficial` e `brapi` são pinos de reprodutibilidade; `--fonte=brapi`
    sem BRAPI_TOKEN falha aqui com mensagem explícita e exit 1 — nunca cai
    para outra fonte por conta própria, nem troca de fonte no meio da
    execução.
    """
    if fonte == "auto":
        provider = provider_do_dado("titulos")
        return provider, rotulo_do_provider(provider)
    if fonte == "oficial":
        return TesouroOficialProvider(), "oficial"
    if fonte == "brapi":
        if not settings.brapi_token:
            console.print(
                "[red]BRAPI_TOKEN ausente ou inválido.[/] "
                "Configure-o no .env (veja .env.example) ou use "
                "[cyan]--fonte=oficial[/] (não requer token)."
            )
            raise typer.Exit(code=1)
        return TesouroDiretoProvider(), "brapi"
    console.print(
        f"[red]Fonte '{fonte}' desconhecida.[/] Use --fonte=auto, --fonte=oficial ou --fonte=brapi."
    )
    raise typer.Exit(code=1)


@tesouro_app.command("listar")
def tesouro_listar(
    tipo: Annotated[
        str | None, typer.Option(help="Filtra por tipo: IPCA+, Prefixado, Selic")
    ] = None,
    limite: Annotated[int, typer.Option(help="Número máximo de resultados")] = 50,
    fonte: Annotated[
        str,
        typer.Option(
            help="Fonte: auto (default — mapa declarado) | oficial (sem token) | "
            "brapi (requer BRAPI_TOKEN)"
        ),
    ] = "auto",
) -> None:
    """Lista os títulos do Tesouro Direto disponíveis."""
    provider, fonte_usada = _escolher_fonte(fonte)
    console.print(f"fonte: {fonte_usada}")
    try:
        df = provider.titulos_disponiveis()
    except requests.RequestException as erro:
        _falha_de_rede("obter os títulos do Tesouro", erro)
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
            f"[red]Data inválida:[/] '{vencimento}'. Use o formato YYYY-MM-DD (ex.: 2035-05-15)."
        )
        raise typer.Exit(code=1) from None
    hoje = date.today()

    # Guarda de magnitude (não-bloqueante): taxa/cupom > 1.0 sugere
    # percentual (6.2) digitado onde se espera decimal (0.062) — muda a
    # magnitude 100x. Avisa e prossegue com o valor informado.
    suspeitos = [
        f"--{nome} {valor}" for nome, valor in (("taxa", taxa), ("cupom", cupom)) if valor > 1.0
    ]
    if suspeitos:
        console.print(
            "[yellow]Aviso:[/] este comando espera taxa e cupom em decimal "
            "(ex.: 0.062 = 6% a.a.); valor(es) aparentemente em percentual: "
            + ", ".join(suspeitos)
            + ". Prosseguindo com o valor informado."
        )

    p = pu.calcular(hoje, venc, taxa, valor_nominal=valor_nominal, taxa_cupom_anual=cupom)
    d_mac = duration.macaulay(hoje, venc, taxa, valor_nominal=valor_nominal, taxa_cupom_anual=cupom)
    d_mod = duration.modificada(
        hoje, venc, taxa, valor_nominal=valor_nominal, taxa_cupom_anual=cupom
    )

    d_v01 = risco.dv01(hoje, venc, taxa, valor_nominal=valor_nominal, taxa_cupom_anual=cupom)
    cvx = risco.convexidade(hoje, venc, taxa, valor_nominal=valor_nominal, taxa_cupom_anual=cupom)

    console.print(f"[bold]PU:[/]              R$ {p:,.2f}")
    console.print(f"[bold]Duration Mac:[/]   {d_mac:.4f} anos")
    console.print(f"[bold]Duration Mod:[/]   {d_mod:.4f}")
    console.print(f"[bold]DV01:[/]           R$ {d_v01:.4f} / bp")
    console.print(f"[bold]Convexidade:[/]    {cvx:.4f}")

    if cupom > 0:
        # Cupom anual efetivo na convenção composta STN/ANBIMA (2 cupons por
        # ano, a frequência padrão do núcleo de precificação): o mesmo cupom
        # que gerar_fluxos paga — e não a divisão linear cupom × nominal.
        cupom_anual = 2 * cupom_periodo(valor_nominal, cupom, 2)
        cy = current_yield.calcular(cupom_anual, p)
        console.print(f"[bold]Current Yield:[/]  {cy:.4%}")


# ----------------------------------------------------------------------
# Comparação
# ----------------------------------------------------------------------
@app.command()
def comparar(
    cdb: Annotated[float | None, typer.Option(help="Taxa bruta do CDB em % a.a.")] = None,
    cdb_cdi: Annotated[
        float | None,
        typer.Option(help="Taxa bruta do CDB em % do CDI (ex.: 110); exige --cdi-auto ou --cdi"),
    ] = None,
    lci: Annotated[float | None, typer.Option(help="Taxa da LCI/LCA em % a.a.")] = None,
    tesouro: Annotated[float | None, typer.Option(help="Taxa do Tesouro em % a.a.")] = None,
    debenture: Annotated[
        float | None, typer.Option(help="Taxa bruta da debênture em % a.a.")
    ] = None,
    incentivada: Annotated[
        bool, typer.Option(help="Debênture incentivada (isenta de IR por categoria)")
    ] = False,
    cdi_auto: Annotated[
        bool,
        typer.Option(help="Obtém o CDI anual da série oficial SGS/BCB (série 12, sem token)"),
    ] = False,
    cdi: Annotated[
        float | None, typer.Option(help="CDI anual informado pelo usuário, em % a.a. (ex.: 13.0)")
    ] = None,
    prazo: Annotated[int, typer.Option(help="Prazo em dias corridos")] = 720,
) -> None:
    """Compara produtos de renda fixa pelo líquido de IR."""
    # Uso ambíguo é rejeitado — sem adivinhação de unidade nem de fonte.
    if cdb is not None and cdb_cdi is not None:
        console.print(
            "[red]Informe o CDB em uma única unidade:[/] use --cdb (taxa em "
            "% a.a.) ou --cdb-cdi (% do CDI), não ambos."
        )
        raise typer.Exit(code=1)
    if cdi_auto and cdi is not None:
        console.print(
            "[red]Informe o CDI por uma única fonte:[/] use --cdi-auto (série "
            "oficial SGS/BCB) ou --cdi <valor>, não ambos."
        )
        raise typer.Exit(code=1)
    if cdb_cdi is not None and not cdi_auto and cdi is None:
        console.print(
            "[red]CDB em % do CDI exige o valor do CDI:[/] use --cdi-auto "
            "(busca a série oficial do SGS/BCB, sem token) ou informe "
            "--cdi <CDI anual em % a.a.>."
        )
        raise typer.Exit(code=1)
    if (cdi_auto or cdi is not None) and cdb_cdi is None:
        console.print(
            "[red]--cdi-auto/--cdi só são usados com --cdb-cdi[/] (CDB "
            "expresso em % do CDI). Informe --cdb-cdi ou remova-os."
        )
        raise typer.Exit(code=1)
    if incentivada and debenture is None:
        console.print(
            "[red]--incentivada exige --debenture:[/] informe a taxa bruta da debênture em % a.a."
        )
        raise typer.Exit(code=1)
    # Faixa do valor: percentual do CDI <= 0 estoura o ValueError do núcleo
    # de conversão, e CDI <= 0 não tem sentido econômico — ambos saem como
    # erro pt-BR de entrada, antes de qualquer cálculo.
    if cdb_cdi is not None and cdb_cdi <= 0:
        console.print(
            "[red]--cdb-cdi deve ser positivo:[/] informe o percentual do CDI "
            "(ex.: --cdb-cdi 110 = 110% do CDI)."
        )
        raise typer.Exit(code=1)
    if cdi is not None and cdi <= 0:
        console.print(
            "[red]--cdi deve ser positivo:[/] informe o CDI anual em % a.a. (ex.: --cdi 13.0)."
        )
        raise typer.Exit(code=1)
    # Prazo <= 0 estoura o ValueError do núcleo de IR (ir.aliquota) — mesmo
    # tratamento de entrada: erro pt-BR antes de qualquer cálculo.
    if prazo <= 0:
        console.print(
            "[red]--prazo deve ser positivo:[/] informe o prazo em dias "
            "corridos (ex.: --prazo 720)."
        )
        raise typer.Exit(code=1)

    produtos: list[taxa_equivalente.ProdutoRF] = []

    # Uma única fonte de CDI por execução, anunciada na saída.
    if cdb_cdi is not None:
        if cdi is not None:
            cdi_valor = cdi / 100
            fonte_cdi = "informado"
        else:
            provider_cdi = provider_do_dado("cdi")
            try:
                cdi_valor = taxa_equivalente.cdi_anual_do_provider(
                    provider_cdi, date.today() - timedelta(days=365), date.today()
                )
            except requests.RequestException as erro:
                _falha_de_rede("obter o CDI da série SGS/BCB", erro)
            except ValueError as erro:
                # SGS sem dados responde 200 + {"erro": ...} — forma de erro
                # real do BCB e o provider levanta ValueError; sem traceback
                # cru (espelho do except ValueError de fundos resumo).
                console.print(f"[red]Erro ao obter o CDI da série SGS/BCB:[/] {erro}")
                raise typer.Exit(code=1) from None
            # rótulo do anúncio vem do mapa declarado (fontes.py)
            fonte_cdi = rotulo_do_provider(provider_cdi)
        console.print(f"CDI ({fonte_cdi}): {cdi_valor:.2%}")

    if cdb is not None:
        produtos.append(taxa_equivalente.ProdutoRF("CDB", cdb / 100, prazo, isento=False))
    if cdb_cdi is not None:
        # A conversão '% do CDI' → % a.a. é contrato do núcleo de comparação.
        taxa_cdb_cdi = taxa_equivalente.cdi_para_taxa_anual(cdb_cdi / 100, cdi_valor)
        produtos.append(taxa_equivalente.ProdutoRF("CDB", taxa_cdb_cdi, prazo, isento=False))
    if lci is not None:
        produtos.append(taxa_equivalente.ProdutoRF("LCI/LCA", lci / 100, prazo, isento=True))
    if tesouro is not None:
        produtos.append(taxa_equivalente.ProdutoRF("Tesouro", tesouro / 100, prazo, isento=False))
    if debenture is not None:
        # Entra pelo modelo canônico de título: a isenção da incentivada é
        # derivada do tipo + categoria no modelo, não digitada à mão.
        titulo_deb = Titulo(
            nome="Debênture incentivada" if incentivada else "Debênture",
            tipo="Debênture",
            vencimento=date.today() + timedelta(days=prazo),
            taxa_compra=Decimal(str(debenture / 100)),
            data_referencia=date.today(),
            emissor="não informado",
            categoria="debênture-incentivada" if incentivada else "debênture-comum",
        )
        produtos.append(taxa_equivalente.ProdutoRF.de_titulo(titulo_deb, prazo_dias=prazo))

    # Guarda de magnitude (não-bloqueante): taxa < 1.0 sugere decimal
    # (0.12) digitado onde se espera percentual (12.0) — muda a magnitude
    # 100x. Avisa e prossegue com o valor informado.
    suspeitas = [
        f"--{nome} {valor}"
        for nome, valor in (
            ("cdb", cdb),
            ("lci", lci),
            ("tesouro", tesouro),
            ("debenture", debenture),
            ("cdi", cdi),
        )
        if valor is not None and valor < 1.0
    ]
    if suspeitas:
        console.print(
            "[yellow]Aviso:[/] este comando espera taxas em percentual "
            "(ex.: --cdb 12.0 = 12% a.a.); valor(es) aparentemente em "
            "decimal: " + ", ".join(suspeitas) + ". Prosseguindo com o "
            "valor informado."
        )

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
    console.print()
    console.print(
        "Material de caráter informativo: apresenta a comparação calculada "
        "dos produtos informados, líquida de IR, e não constitui oferta, "
        "proposta de investimento ou forma de captar recursos junto ao público."
    )
    console.print("Referência normativa: Resolução CVM 20/2021.")


# ----------------------------------------------------------------------
# Fundos
# ----------------------------------------------------------------------
@fundos_app.command("resumo")
def fundos_resumo(
    cnpj: Annotated[str, typer.Option(help="CNPJ do fundo (com ou sem pontuação)")],
    mes: Annotated[str, typer.Option(help="Mês de referência, no formato AAAA-MM (ex.: 2026-08)")],
) -> None:
    """Resume a rentabilidade de um fundo no mês (informe diário da CVM).

    Os três números seguem o contrato de métricas: acumulada do período,
    anualizada (base 252, dias úteis do calendário real) e expressa em % do
    CDI (série SGS/BCB na mesma janela do fundo).
    """
    try:
        referencia = datetime.strptime(mes, "%Y-%m").date()
    except ValueError:
        console.print(f"[red]Mês inválido:[/] '{mes}'. Use o formato AAAA-MM (ex.: 2026-08).")
        raise typer.Exit(code=1) from None

    # CNPJ validado na entrada: um CNPJ sem os 14 dígitos (ex.: "" ou raiz
    # parcial) cairia no ramo falsy do filtro do provider e devolveria o
    # mercado inteiro como se fosse o resumo do fundo.
    if len(re.sub(r"\D", "", cnpj)) != 14:
        console.print(
            f"[red]CNPJ inválido:[/] '{cnpj}' não tem 14 dígitos — informe o "
            "CNPJ completo (com ou sem pontuação; ex.: 00.017.024/0001-53)."
        )
        raise typer.Exit(code=1)

    provider = provider_do_dado("fundos")
    console.print(f"fonte: {rotulo_do_provider(provider)}")

    try:
        df = provider.informe_diario(referencia.year, referencia.month, cnpj=cnpj)
    except RedeIndisponivel as erro:
        # rede — a causa original segue encadeada na exceção de domínio
        _falha_de_rede("obter o informe da CVM", erro)
    except InformeNaoDisponivel as erro:
        # mês sem arquivo publicado na fonte: erro de domínio, distinto de
        # falha de rede — mensagem específica em vez do achatamento
        console.print(f"[red]{erro}[/]")
        raise typer.Exit(code=1) from None
    except (ValueError, zipfile.BadZipFile) as erro:
        # payload ilegível (ZIP sem entradas ou resposta truncada): erro
        # explícito em pt-BR, sem traceback cru
        console.print(f"[red]Informe ilegível:[/] {erro}")
        raise typer.Exit(code=1) from None

    if df.empty:
        console.print(
            f"[red]Nenhum informe do CNPJ {cnpj} em {referencia.month:02d}/"
            f"{referencia.year}.[/] Confira o CNPJ ou escolha um mês já publicado."
        )
        raise typer.Exit(code=1)

    try:
        acumulada = rentabilidade_periodo(df)
        anualizada = rentabilidade_anualizada(df)
        pct_cdi = percentual_cdi(df, provider_do_dado("cdi"))
    except requests.RequestException as erro:
        _falha_de_rede("obter o CDI da série SGS/BCB", erro)
    except ValueError as erro:
        # erros de domínio dos providers já saem em pt-BR; sem traceback cru
        console.print(f"[red]Erro ao calcular a rentabilidade:[/] {erro}")
        raise typer.Exit(code=1) from None

    console.print(
        f"[bold]Fundo CNPJ:[/] {cnpj} — referência {referencia.month:02d}/{referencia.year}"
    )
    console.print(f"[bold]Rentabilidade acumulada:[/] {acumulada:.4%}")
    console.print(f"[bold]Rentabilidade anualizada:[/] {anualizada:.4%}")
    console.print(f"[bold]% do CDI:[/] {pct_cdi:.2%}")
    console.print()
    console.print(
        "Material de caráter informativo: apresenta métricas calculadas do "
        "informe diário público da CVM para o fundo informado e não constitui "
        "oferta, proposta de investimento ou forma de captar recursos junto "
        "ao público."
    )
    console.print("Referência normativa: Resolução CVM 20/2021.")


# ----------------------------------------------------------------------
# Carteira
# ----------------------------------------------------------------------


# ----------------------------------------------------------------------
# Relatório
# ----------------------------------------------------------------------
@relatorio_app.command("gerar")
def relatorio_gerar(
    output: Annotated[Path, typer.Option(help="Caminho do arquivo de saída")] = Path(
        "relatorio.md"
    ),
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
