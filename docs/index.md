# Renda Fixa Quant BR — Documentação

> Ferramenta open source para **análise quantitativa de renda fixa brasileira**.

## O que é

O **Renda Fixa Quant BR** (`rfquant`) é uma biblioteca Python com CLI para
precificação e comparação de investimentos de renda fixa no Brasil.

Cobre:

- **Tesouro Direto** — cotações pela fonte oficial (Tesouro Transparente,
  CSV público, sem token) e precificação de títulos genéricos.
- **CDB, LCI/LCA, Tesouro e outros** — comparação pelo líquido de IR
  (tabela regressiva + IOF) e conversão entre taxas.

## Por que existe

- **104,8 milhões de CPFs** em renda fixa no Brasil (vs. ~5,5 milhões em
  renda variável).
- Nenhuma ferramenta open source de destaque faz análise quantitativa
  séria de renda fixa nacional.

## Instalação

```bash
git clone https://github.com/coach-sarmelo/renda-fixa-quant-br.git
cd renda-fixa-quant-br
python -m venv .venv
source .venv/bin/activate      # Windows: .venv\Scripts\activate
pip install -e ".[dev]"
```

Requisitos: Python 3.11+. Nenhuma chave de API é necessária para o uso
básico (a fonte de dados oficial do Tesouro é pública e sem token).

## Uso rápido

```bash
# Listar títulos do Tesouro Direto (sem token)
rfq tesouro listar --fonte=oficial --tipo IPCA+

# Precificar um título
rfq tesouro precificar --vencimento 2035-05-15 --taxa 0.062 --cupom 0.06

# Comparar CDB vs LCI vs Tesouro
rfq comparar --cdb 12.0 --lci 10.5 --tesouro 11.8 --prazo 720

# Resumo do Tesouro Direto de hoje
rfq hoje
```

Guia completo com saídas reais e todos os parâmetros: [Uso detalhado](uso.md).

## Índice da documentação

| Documento | Conteúdo |
|---|---|
| [Arquitetura](arquitetura.md) | Como o código está organizado, princípios e fluxo de dados |
| [Fórmulas](formulas.md) | Toda a matemática implementada, com as convenções e limitações |
| [Fontes de dados](dados.md) | Por que o CSV oficial do Tesouro Transparente foi escolhido, cache e limitações medidas |
| [Uso detalhado](uso.md) | Referência da CLI, biblioteca Python e notebooks |

## O que existe hoje e o que está no radar

**Hoje:** precificação (PU com cupom composto STN/ANBIMA, duration, YTM,
current yield, marcação a mercado), risco (DV01 e convexidade), curva de
juros (ETTJ com flat-forward como método default; interpolação linear e
Nelson-Siegel disponíveis), tributação (IR regressivo + IOF), comparação
de produtos, calendário real de dias úteis, dados oficiais (Tesouro
Direto, CDI via SGS/BCB, fundos via CVM) e relatório determinístico de
carteira de exemplo.

**No radar (planejado, sem data):** demais séries macro (Selic meta, IPCA)
via SGS/BCB, fonte contingencial de scraping do portal do Tesouro Direto e
integração com outras fontes (ver [dados.md](dados.md)).

Não existe, e não está planejado para agora: recomendação automática de
investimentos, otimização de carteira, dashboard ou API web.

## Licença

MIT — veja [LICENSE](../LICENSE).

## Disclaimer

Ferramenta **educacional e informacional**. Não constitui consultoria de
valores mobiliários nos termos da Resolução CVM nº 20/2021. Não há
recomendação personalizada. Consulte um profissional certificado antes de
investir.
