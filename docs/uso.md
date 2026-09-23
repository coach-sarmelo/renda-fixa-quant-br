# Uso Detalhado

Guia de referência para o dia a dia: instalação, configuração, CLI
(comandos, opções e saídas reais), notebooks e uso como biblioteca Python.

## Instalação

```bash
git clone https://github.com/coach-sarmelo/renda-fixa-quant-br.git
cd renda-fixa-quant-br

# Com uv (recomendado)
uv venv --python 3.11
source .venv/bin/activate
uv pip install -e ".[dev]"

# Ou com pip
python -m venv .venv
source .venv/bin/activate     # Windows: .venv\Scripts\activate
pip install -e ".[dev]"
```

## Configuração

Copie `.env.example` para `.env` e preencha o que for usar:

```bash
cp .env.example .env
```

Variáveis:

| Variável | Uso |
|---|---|
| `RFQ_CACHE_DIR` | Diretório do cache (padrão: `~/.rfquant/cache`) |
| `BRAPI_TOKEN` | Reservado à fonte `brapi` — **não utilizável hoje** (endpoint de renda fixa exige plano pago; ver [dados.md](dados.md)) |

O `.env.example` lista também `RFQ_DB_PATH` e `RFQ_LOG_LEVEL` — variáveis
reservadas, sem efeito na prática hoje. Para todo o uso documentado aqui,
nenhuma configuração é necessária.

## CLI

### `rfq version`

Mostra a versão instalada:

```
rfquant 0.1.0
```

### `rfq tesouro listar`

Lista os títulos do Tesouro Direto disponíveis.

```
rfq tesouro listar --fonte=oficial
rfq tesouro listar --fonte=oficial --tipo IPCA+
rfq tesouro listar --fonte=oficial --tipo Prefixado --limite 20
```

Opções:

| Opção | Descrição | Padrão |
|---|---|---|
| `--fonte` | `oficial` (sem token) ou `brapi` | `brapi` |
| `--tipo` | Filtra por tipo: `IPCA+`, `Prefixado`, `Selic` | — |
| `--limite` | Número máximo de resultados | 50 |

> **Use sempre `--fonte=oficial`.** O padrão é `brapi`, que falha sem
> `BRAPI_TOKEN` (exit 1, mensagem explícita) e, mesmo com token de conta
> gratuita, esbarra no paywall do endpoint de renda fixa. A fonte oficial
> baixa o CSV público do Tesouro Transparente (sem cadastro), com cache
> local de 24 h — a primeira execução do dia baixa ~14,5 MB; as seguintes
> leem do cache.

> **Por que o padrão é `brapi` se ela é inutilizável hoje?** Razão
> histórica: `brapi` foi a primeira fonte do projeto (configurável por
> `BRAPI_TOKEN`, plano Pro) e o default não foi trocado quando a fonte
> oficial chegou, para não quebrar quem já tinha token e scripts prontos.
> Não há variável de ambiente para trocar o default — passe
> `--fonte=oficial` explicitamente ou crie um alias
> (`alias rfq='rfq tesouro listar --fonte=oficial'` no seu shell). A troca
> do default para `oficial` está registrada como melhoria futura.

Exemplo de saída (`--fonte=oficial --tipo Prefixado --limite 3`):

```
                          Tesouro Direto — 2026-09-21
┌────────────────────────┬───────────┬────────────┬─────────────┬─────────────┐
│ Nome                   │ Tipo      │ Vencimento │ Taxa compra │   PU compra │
├────────────────────────┼───────────┼────────────┼─────────────┼─────────────┤
│ Tesouro Prefixado 2027 │ Prefixado │ 2027-01-01 │    13.5400% │   R$ 965.34 │
│ Tesouro Prefixado com  │ Prefixado │ 2027-01-01 │    13.3200% │ R$ 1,013.00 │
│ Juros Semestrais 2027  │           │            │             │             │
│ Tesouro Prefixado 2028 │ Prefixado │ 2028-01-01 │    13.6000% │   R$ 850.07 │
└────────────────────────┴───────────┴────────────┴─────────────┴─────────────┘
```

(Valores meramente ilustrativos — a saída real traz as taxas do dia.)

### `rfq tesouro precificar`

Precifica um título genérico de renda fixa — matemática pura, sem rede.
A data de referência é sempre a data atual.

```
rfq tesouro precificar --vencimento 2035-05-15 --taxa 0.062 --cupom 0.06
```

Opções:

| Opção | Descrição | Padrão |
|---|---|---|
| `--vencimento` | Data de vencimento (`YYYY-MM-DD`) | obrigatória |
| `--taxa` | Taxa anual em decimal (ex.: `0.062` = 6,2% a.a.) | obrigatória |
| `--valor-nominal` | Valor de face | 1000.0 |
| `--cupom` | Cupom anual em decimal (0 = zero-cupom) | 0.0 |

> **Atenção às convenções de unidade — elas diferem entre comandos.**
> `tesouro precificar --taxa` espera **decimal** (`0.062` = 6,2%), enquanto
> `comparar --cdb/--lci/--tesouro` espera **percentual** (`12.0` = 12%).
> `rfq comparar --cdb 0.12` e `rfq tesouro precificar --taxa 12` rodam sem
> erro — e devolvem números errados. Confira a coluna "Descrição" de cada
> tabela antes de digitar.

> **Título genérico sob o namespace `tesouro`.** O comando precifica
> qualquer título de renda fixa (incluindo CDB e debênture — daí o nome
> genérico), mas vive sob `tesouro` por ser o caso de uso principal. A data
> de referência é sempre **a data atual** e não há opção `--data`: para
> precificar em uma data histórica ou futura, use a biblioteca, que aceita
> `data_compra` explícita:

```python
from datetime import date
from rfquant.pricing import pu

p = pu.calcular(
    data_compra=date(2024, 7, 15),   # data de referência que você quiser
    data_vencimento=date(2035, 5, 15),
    taxa_anual=0.062,
)
```

Saída (com `--vencimento 2035-05-15 --taxa 0.062 --cupom 0.06`, executado
em 2026-09-21):

```
PU:              R$ 1,013.73
Duration Mac:   6.7261 anos
Duration Mod:   6.3334
Current Yield:  5.9187%
```

O Current Yield só aparece quando o cupom é maior que zero. As fórmulas e
a aproximação de dias úteis (D6) estão em [formulas.md](formulas.md).

### `rfq comparar`

Compara produtos de renda fixa pelo líquido de IR.

```
rfq comparar --cdb 12.0 --lci 10.5 --tesouro 11.8 --prazo 720
```

Opções:

| Opção | Descrição | Padrão |
|---|---|---|
| `--cdb` | Taxa bruta do CDB em % a.a. | — |
| `--lci` | Taxa da LCI/LCA em % a.a. | — |
| `--tesouro` | Taxa do Tesouro em % a.a. | — |
| `--prazo` | Prazo em dias corridos | 720 |

Informe ao menos um produto (senão a CLI encerra com erro). Saída real do
comando acima (IR de 17,5% para 720 dias):

```
              Comparação — prazo 720 dias — IR 17.5%
┌─────────┬────────────┬──────────────┬─────────────────┬────────┐
│ Produto │ Taxa bruta │ Taxa líquida │ Equivalente CDB │ Isento │
├─────────┼────────────┼──────────────┼─────────────────┼────────┤
│ LCI/LCA │   10.5000% │     10.5000% │        12.7273% │ sim    │
│ CDB     │   12.0000% │      9.9000% │        12.0000% │ não    │
│ Tesouro │   11.8000% │      9.7350% │        11.8000% │ não    │
└─────────┴────────────┴──────────────┴─────────────────┴────────┘
```

A coluna "Equivalente CDB" responde: qual taxa bruta de CDB renderia o
mesmo líquido? No exemplo, a LCI/LCA isenta a 10,5% equivale a um CDB bruto
de ~12,73% — melhor que o CDB de 12% oferecido. A convenção de cálculo e
sua limitação para prazos ≠ 1 ano estão em [formulas.md](formulas.md#13-convenção-de-taxa-líquida-na-comparação-limitação-declarada).

### `rfq relatorio gerar`

Gera um relatório Markdown **determinístico** de uma carteira de
**exemplo** (embutida no comando, para demonstrar o formato): sem rede, sem
chave de API, mesmo resultado para o mesmo dia, com o disclaimer
regulatório no rodapé.

```
rfq relatorio gerar --output relatorio.md
```

| Opção | Descrição | Padrão |
|---|---|---|
| `--output` | Caminho do arquivo de saída | `relatorio.md` |
| `--offline` / `--no-offline` | Modo de geração | `offline` |

**Comportamento real de `--no-offline`:** encerra com erro (exit 1).
Não existe geração de relatório por IA nesta ferramenta — o único caminho é
o determinístico (`--offline`, o padrão). Se você rodar `--no-offline`,
receberá uma mensagem explicando isso e nenhum arquivo será gerado.

### `rfq hoje`

Atalho que mostra um resumo rápido do Tesouro Direto de hoje — os 10
primeiros títulos da fonte oficial (sem token), com a mesma tabela do
`tesouro listar`.

```
rfq hoje
```

## Notebooks

Dois notebooks prontos para explorar (`notebooks/`):

- **`02_precificacao_tesouro.ipynb`** — PU, duration (Macaulay e
  modificada), YTM, Current Yield e marcação a mercado de títulos do
  Tesouro.
- **`03_comparacao_liquida_ir.ipynb`** — comparação de CDB, LCI/LCA e
  Tesouro Direto pela tabela regressiva de IR e a isenção de
  LCI/LCA/CRI/CRA.

```bash
jupyter lab notebooks/
```

## Biblioteca Python

Tudo que a CLI faz está disponível como biblioteca. Assinaturas completas
nos docstrings dos módulos.

### Precificação

```python
from datetime import date
from rfquant.pricing import pu, duration, ytm, marktomarket

# PU de um título com cupom semestral de 6% e yield 6,2% a.a.
p = pu.calcular(
    data_compra=date(2026, 1, 2),
    data_vencimento=date(2035, 5, 15),
    taxa_anual=0.062,
    taxa_cupom_anual=0.06,
)

d_mac = duration.macaulay(date(2026, 1, 2), date(2035, 5, 15), 0.062, taxa_cupom_anual=0.06)
d_mod = duration.modificada(date(2026, 1, 2), date(2035, 5, 15), 0.062, taxa_cupom_anual=0.06)

# YTM dado um PU de mercado
taxa = ytm.calcular(pu_mercado=1013.73, data_compra=date(2026, 1, 2),
                    data_vencimento=date(2035, 5, 15), taxa_cupom_anual=0.06)

# Marcação a mercado exata (re-precificação pelo fluxo remanescente)
res = marktomarket.exata(
    data_compra=date(2025, 9, 1),
    data_hoje=date(2026, 9, 21),
    data_vencimento=date(2035, 5, 15),
    pu_compra=980.0,
    taxa_compra=0.065,
    taxa_mercado=0.062,
)
print(res.pu_mercado, res.variacao_percentual)
```

### Curva de juros (ETTJ)

Com pontos digitados à mão (para estudo/testes):

```python
from rfquant.pricing.curva_juros import ETTJ

pontos = [(1.0, 0.115), (2.0, 0.118), (5.0, 0.125), (10.0, 0.135)]
e = ETTJ(pontos, metodo="nelson_siegel")
print(e.taxa(3.5))            # taxa interpolada para 3,5 anos
print(e.fator_desconto(3.5))  # (1 + y)^(-prazo)
```

E de onde vêm os pontos **reais** da curva de hoje? Do próprio CSV oficial
que a ferramenta já baixa — `titulos_disponiveis()` devolve os títulos da
data-base mais recente, e cada linha vira um ponto `(prazo em anos, taxa)`:

```python
from rfquant.data import TesouroOficialProvider
from rfquant.pricing.curva_juros import ETTJ

df = TesouroOficialProvider().titulos_disponiveis()   # data-base mais recente
df = df[df["tipo"] == "Prefixado"]                # ETTJ pré: só Prefixado
pontos = [
    ((row.vencimento - row.data_referencia).days / 365.0, float(row.taxa_compra))
    for row in df.itertuples()
]
e = ETTJ(pontos, metodo="nelson_siegel")
print(e.taxa(3.5))   # taxa da curva pré para 3,5 anos
```

Colunas úteis do DataFrame: `nome`, `tipo`, `vencimento`, `taxa_compra`,
`taxa_venda`, `pu_compra`, `pu_venda`, `data_referencia` (taxas já em
decimal). Para uma curva real (IPCA+), filtre `tipo == "IPCA+"`.

### Tributação e comparação

```python
from rfquant.comparison import ir, taxa_equivalente

# IR + IOF encadeados
res = ir.calcular(rendimento_bruto=1000.0, prazo_dias=720, isento=False)
print(res.rendimento_liquido, res.aliquota_ir)

# Comparação multi-produto (mesma lógica da CLI)
produtos = [
    taxa_equivalente.ProdutoRF("CDB", 0.12, 720, isento=False),
    taxa_equivalente.ProdutoRF("LCI", 0.105, 720, isento=True),
]
for r in taxa_equivalente.comparar(produtos):
    print(f"{r.produto.nome}: líq {r.taxa_liquida_anual:.4%}")

# Prefixado ↔ IPCA+ (Fisher exata)
real = taxa_equivalente.pre_para_ipca_mais(0.12, 0.04)      # pré 12%, IPCA 4%
pre = taxa_equivalente.ipca_mais_para_pre(real, 0.04)       # volta a 12%
print(f"IPCA+ equivalente: {real:.4%}  ·  pré de volta: {pre:.4%}")
```

### Dados do Tesouro Direto

```python
from datetime import date
from rfquant.data import TesouroOficialProvider

provider = TesouroOficialProvider()          # CSV oficial, sem token
df = provider.titulos_disponiveis()      # títulos da data-base mais recente
hist = provider.historico_taxas(
    titulo="Tesouro IPCA+ 2035",
    inicio=date(2026, 1, 1),
    fim=date(2026, 9, 21),
)
```

> `TesouroOficialProvider` é uma implementação enxuta e direta sobre o CSV
> oficial — um único download cacheado seguido de parsing/filtro, sem
> camadas extras. É a fonte de produção usada por `--fonte=oficial`.

**Regra de formação dos nomes de título** (válida para `historico_taxas`):
`nome = "Tipo Titulo" do CSV oficial + espaço + ano de vencimento`. Os
valores do CSV hoje são `Tesouro Selic`, `Tesouro IPCA+`, `Tesouro
Prefixado` e, para os com cupom semestral, `Tesouro IPCA+ com Juros
Semestrais` / `Tesouro Prefixado com Juros Semestrais`. Exemplos válidos:
`"Tesouro Selic 2029"`, `"Tesouro IPCA+ 2035"`, `"Tesouro Prefixado com
Juros Semestrais 2032"`. Para listar os nomes disponíveis no dia, veja a
coluna `nome` de `titulos_disponiveis()` (ou a saída de
`rfq tesouro listar --fonte=oficial`). O nome precisa casar exatamente.

## Testes

```bash
pytest                          # roda tudo com cobertura
pytest tests/test_pricing_pu.py # só PU
pytest -k duration              # testes com "duration" no nome
```

Testes que exigem rede real são marcados `network` e ficam de fora da
execução padrão.

## Qualidade de código

```bash
make lint    # ruff + mypy
make format  # formata com ruff
```

## Solução de problemas

| Sintoma | Causa e solução |
|---|---|
| `BRAPI_TOKEN ausente ou inválido.` ao listar títulos | Você rodou `rfq tesouro listar` sem `--fonte` (o padrão é `brapi`). Use `--fonte=oficial`. |
| `Fonte '...' desconhecida.` | Valor inválido em `--fonte`. Os valores aceitos são `oficial` e `brapi`. |
| Primeira listagem do dia demora | O CSV oficial (~14,5 MB) está sendo baixado; execuções seguintes leem do cache de 24 h (`~/.rfquant/cache`). |
| `rfq relatorio gerar --no-offline` termina com erro | Comportamento esperado: não existe geração por IA. Use o padrão (`--offline`). |
| PU difere do site do Tesouro | Aproximação de dias úteis (D6) — o erro cresce com o prazo. Tabelas medidas em [dados.md](dados.md). |
