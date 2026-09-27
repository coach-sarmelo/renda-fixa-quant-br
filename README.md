# Renda Fixa Quant BR

> Ferramenta open source para **análise quantitativa de renda fixa brasileira** — precificação, duration, YTM, marcação a mercado e comparação líquida de IR.

[![CI](https://github.com/coach-sarmelo/renda-fixa-quant-br/actions/workflows/ci.yml/badge.svg)](https://github.com/coach-sarmelo/renda-fixa-quant-br/actions/workflows/ci.yml)
[![Python 3.11+](https://img.shields.io/badge/python-3.11%2B-blue.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

---

## Por que este projeto existe

- **104,8 milhões de CPFs** investem em renda fixa no Brasil (vs. ~5,5 milhões em renda variável).
- Nenhuma ferramenta open source ou SaaS de destaque faz **análise quantitativa séria** de renda fixa nacional.

## Funcionalidades

| Módulo | O que faz | Onde |
|--------|-----------|------|
| **Precificação** | PU, duration (Macaulay e modificada) e Current Yield na CLI (`rfq tesouro precificar`); YTM e marcação a mercado (linear e exata) via biblioteca | CLI e biblioteca |
| **Curva de juros** | Interpolação da ETTJ (linear / Nelson-Siegel), conversões nominal↔efetiva e pré↔IPCA+ | Biblioteca |
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

Exemplo de saída do `precificar` (a data de referência é sempre a data atual):

```
PU:              R$ 1,013.73
Duration Mac:   6.7261 anos
Duration Mod:   6.3334
Current Yield:  5.9187%
```

> **Sobre a opção `--fonte`:** o valor padrão é `auto` — um mapa declarado
> resolve cada dado pela sua fonte oficial (títulos → Tesouro Transparente;
> CDI → série SGS/BCB; fundos → CVM) e a CLI anuncia a fonte usada ("fonte:
> oficial"). `--fonte=oficial` continua disponível. `--fonte=brapi` hoje
> **não é utilizável** (exige plano pago e falha sem `BRAPI_TOKEN`) — a
> resolução automática nunca o escolhe. Detalhes em
> [Fontes de dados](docs/dados.md).

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

Gera um relatório Markdown **determinístico** de uma carteira de **exemplo**
(embutida no comando, apenas para demonstrar o formato): sem rede, sem
chave de API, com o disclaimer regulatório no rodapé. A saída é sempre a
mesma para o mesmo dia.

A opção `--no-offline` apenas encerra com erro (código 1): não existe
geração de relatório por IA nesta ferramenta — o único caminho é o
determinístico. Veja [Uso detalhado](docs/uso.md).

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

## Testes e qualidade

```bash
make test     # pytest com cobertura
make lint     # ruff + mypy
make format   # formata com ruff
```

## Arquitetura

```
src/rfquant/
├── data/            # Providers (Tesouro, SGS/BCB, CVM) + cache em disco
├── pricing/         # PU, duration, YTM, marcação a mercado, curva de juros
├── comparison/      # IR, IOF, taxa equivalente
├── cli.py           # Interface de linha de comando (rfq)
├── relatorio.py     # Relatório determinístico (Markdown)
└── config.py        # Settings (pydantic-settings, lê .env)
```

Princípio central: **cálculo determinístico**. Números vêm de fórmulas
explícitas e dados oficiais — nunca de fontes não auditáveis. Detalhes em
[Arquitetura](docs/arquitetura.md).

## Limitações que vale a pena conhecer

- **Dias úteis aproximados:** o núcleo estima dias úteis por
  `dias corridos × 252/365`; o Tesouro oficial usa o calendário real. O erro
  do PU cresce com o prazo — tabelas medidas em [dados.md](docs/dados.md).
- A comparação de taxas aplica o IR de forma linear pela alíquota do prazo
  informado — aproximação exata apenas para horizonte de 1 ano
  ([formulas.md](docs/formulas.md)).
- **Cupom linear:** o gerador de fluxos usa cupom linear (`VN × i / f`), não
  o composto do padrão STN/ANBIMA (NTN-F 10% a.a.: R$ 50,00 vs R$ 48,81 por
  cupom) — [formulas.md](docs/formulas.md).
- **Console Windows:** em terminais com codepage OEM os acentos podem sair
  quebrados; use Windows Terminal ou `chcp 65001`
  ([uso.md](docs/uso.md)).

## Documentação

- [Índice](docs/index.md)
- [Arquitetura](docs/arquitetura.md)
- [Fórmulas](docs/formulas.md)
- [Fontes de dados](docs/dados.md)
- [Uso detalhado](docs/uso.md)

## Disclaimer

Esta ferramenta é **educacional e informacional**. Não constitui consultoria de valores mobiliários nos termos da Resolução CVM nº 20/2021. Não há recomendação personalizada. Consulte um profissional certificado antes de investir.

## Licença

MIT — veja [LICENSE](LICENSE).
