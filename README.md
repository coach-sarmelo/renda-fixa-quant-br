# Renda Fixa Quant BR

> Ferramenta open source para **análise quantitativa de renda fixa brasileira** — precificação, duration, YTM, marcação a mercado e comparação líquida de IR.

[![CI](https://github.com/coach-sarmelo/renda-fixa-quant-br/actions/workflows/ci.yml/badge.svg)](https://github.com/coach-sarmelo/renda-fixa-quant-br/actions/workflows/ci.yml)
[![Python 3.11+](https://img.shields.io/badge/python-3.11%2B-blue.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

---

## Funcionalidades

| Módulo | O que faz | Onde |
|--------|-----------|------|
| **Precificação** | PU (cupom composto, padrão STN/ANBIMA), duration (Macaulay e modificada) e Current Yield na CLI (`rfq tesouro precificar`); NTN-B/NTN-B Principal pela cotação em % do VNA — PU = VNA × cotação/100 (`--vna`); YTM e marcação a mercado (linear e exata) via biblioteca | CLI e biblioteca |
| **Risco** | DV01 (re-precificação para +1 bp e aproximação D_mod×PU×0,0001), convexidade (forma fechada base 252) e variação de PU de 2ª ordem (Duration + Convexidade) | CLI (`rfq tesouro precificar`) e biblioteca |
| **Curva de juros** | ETTJ com flat-forward (padrão B3/ANBIMA) como método default; interpolação linear e Nelson-Siegel disponíveis; conversões nominal↔efetiva e pré↔IPCA+ | Biblioteca |
| **Comparação** | IR regressivo + IOF, taxa equivalente entre produtos isentos e tributados | CLI e biblioteca |
| **Dados** | Tesouro Direto (CSV oficial do Tesouro Transparente), CDI (série SGS/BCB) e fundos (informes da CVM) — fontes oficiais, sem token | CLI e biblioteca |
| **Interfaces** | CLI (`rfq`), notebooks Jupyter e biblioteca Python | — |

## Instalação

Requisitos: Python 3.11+ e `make` (no Windows: `scoop install make` ou `choco install make`).

```bash
git clone https://github.com/coach-sarmelo/renda-fixa-quant-br.git
cd renda-fixa-quant-br

python -m venv .venv
source .venv/bin/activate      # Windows: .venv\Scripts\activate
make install-dev               # pip install -e ".[dev]"
```

(ou diretamente `pip install -e ".[dev]"`)

## Uso rápido (CLI) — sem token

Os comandos abaixo funcionam imediatamente após a instalação, sem nenhuma
configuração:

```bash
# 1) Listar títulos do Tesouro Direto — fonte oficial (Tesouro Transparente), sem token
rfq tesouro listar --fonte=oficial
rfq tesouro listar --fonte=oficial --tipo IPCA+

# 2) Precificar um título (matemática pura, sem rede)
rfq tesouro precificar --vencimento 2035-05-15 --taxa 0.062 --cupom 0.06

# 3) Comparar CDB vs LCI vs Tesouro pelo líquido de IR
rfq comparar --cdb 12.0 --lci 10.5 --tesouro 11.8 --prazo 720

# 4) Resumo rápido do Tesouro Direto de hoje (fonte oficial)
rfq hoje

# 5) Listar títulos com a fonte resolvida automaticamente (a CLI anuncia "fonte: oficial")
rfq tesouro listar --fonte=auto

# 6) Comparar CDB a 110% do CDI com o CDI real da série SGS/BCB (sem token)
rfq comparar --cdb-cdi 110 --cdi-auto --prazo 720

# 7) Resumo de um fundo de investimento no mês (troque pelo CNPJ real; informe da CVM, sem token)
rfq fundos resumo --cnpj 00.000.000/0000-00 --mes 2026-08
```

Exemplo de saída do `precificar` (executado em 2026-10-01; a data de
referência é sempre a data atual):

```
PU:              R$ 1,012.67
Duration Mac:   6.6626 anos
Duration Mod:   6.2737
DV01:           R$ 0.6350 / bp
Convexidade:    52.2252
Current Yield:  5.8386%
```

## Configuração (`.env`)

Opcional: copie o exemplo e preencha apenas o que for usar.

```bash
cp .env.example .env
```

| Variável | Para quê | Padrão |
|----------|----------|--------|
| `RFQ_CACHE_DIR` | diretório de cache de dados | `~/.rfquant/cache` |
| `BRAPI_TOKEN` | reservado à fonte `brapi` — **não utilizável hoje** (exige plano pago; ver [dados.md](docs/dados.md)) | — |

O `.env.example` lista também `RFQ_DB_PATH` e `RFQ_LOG_LEVEL` — variáveis
reservadas, sem efeito na prática hoje.

## Relatório de exemplo

```bash
rfq relatorio gerar --output relatorio.md
```

## Uso como biblioteca

```python
from datetime import date
from rfquant.pricing import pu, duration

p = pu.calcular(
    data_compra=date(2026, 1, 2),
    data_vencimento=date(2035, 5, 15),
    taxa_anual=0.062,
    taxa_cupom_anual=0.06,
)
d_mod = duration.modificada(date(2026, 1, 2), date(2035, 5, 15), 0.062, taxa_cupom_anual=0.06)
print(f"PU: R$ {p:,.2f} | Duration mod: {d_mod:.4f}")
```

Mais exemplos (YTM, marcação a mercado, ETTJ, IR, comparação) em
[Uso detalhado](docs/uso.md), e os notebooks em [`notebooks/`](notebooks/).


## Arquitetura

```
src/rfquant/
├── data/            # Providers (Tesouro, SGS/BCB, CVM) + cache em disco
├── pricing/         # PU, duration, DV01, convexidade, YTM, marcação a mercado, curva de juros
├── comparison/      # IR, IOF, taxa equivalente
├── cli.py           # Interface de linha de comando (rfq)
├── relatorio.py     # Relatório determinístico (Markdown)
└── config.py        # Settings (pydantic-settings, lê .env)
```


## Documentação

- [Índice](docs/index.md)
- [Arquitetura](docs/arquitetura.md)
- [Fórmulas](docs/formulas.md)
- [Fontes de dados](docs/dados.md)
- [Uso detalhado](docs/uso.md)

## Disclaimer

Esta ferramenta é **educacional e informacional**. Não constitui consultoria de valores mobiliários.

## Licença

MIT — veja [LICENSE](LICENSE).
