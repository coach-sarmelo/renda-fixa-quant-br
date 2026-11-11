# Renda Fixa Quant BR — Documentação

> Ferramenta open source para **análise quantitativa de renda fixa brasileira**.

## O que é

O **Renda Fixa Quant BR** (`rfquant`) é uma biblioteca Python com CLI para
precificação, estrutura a termo de juros (ETTJ), marcação a mercado e comparação
de investimentos de renda fixa no Brasil.

Cobre:

- **Tesouro Direto** — cotações pela fonte oficial (Tesouro Transparente,
  CSV público, sem token), avaliação unificada (`precificar` → `AvaliacaoTitulo`)
  de títulos nominais e indexados ao IPCA (`vna` / NTN-B) e marcação a mercado
  acoplada à curva de juros (`ETTJ`).
- **CDB, LCI/LCA, Debêntures e Fundos** — comparação pelo líquido de IR
  (tabela regressiva + IOF, convenções linear e composta), isenção derivada por
  categoria (incluindo debêntures incentivadas da Lei 12.431/2011), conversão
  entre taxas (Fisher exata e % do CDI) e resumo de informes diários da CVM vs.
  CDI oficial (série 12 do SGS/BCB).

## Por que existe e rigor empírico

- **104,8 milhões de CPFs** em renda fixa no Brasil (vs. ~5,5 milhões em
  renda variável).
- O núcleo de precificação implementa as convenções oficiais da STN/ANBIMA e da
  B3/SFN (cupom semestral composto, calendário real de dias úteis e regra de
  liquidação D+1) e é confrontado em suíte automatizada contra o `PU Compra Manhã`
  publicado pelo Tesouro Nacional, fechando erros relativos de **$\le 1,7 \times 10^{-5}$**
  em LTN e **$\le 9,39 \times 10^{-5}$** em NTN-F (ver [Fontes de dados](dados.md)).

## Instalação

```bash
git clone https://github.com/coach-sarmelo/renda-fixa-quant-br.git
cd renda-fixa-quant-br
python -m venv .venv
source .venv/bin/activate      # Windows: .venv\Scripts\activate
pip install -e ".[dev]"
```

Requisitos: Python 3.11+. Nenhuma chave de API é necessária para o uso
básico (as fontes de dados oficiais do Tesouro, BCB e CVM são públicas e sem token).

## Uso rápido

```bash
# Listar títulos do Tesouro Direto (sem token)
rfq tesouro listar --fonte=oficial --tipo IPCA+

# Precificar um título nominal ou NTN-B (--vna)
rfq tesouro precificar --vencimento 2035-05-15 --taxa 0.062 --cupom 0.06
rfq tesouro precificar --vencimento 2035-05-15 --taxa 0.062 --cupom 0.06 --vna 4500.00

# Comparar CDB vs LCI vs Tesouro vs Debênture incentivada
rfq comparar --cdb 12.0 --lci 10.5 --tesouro 11.8 --debenture 10.2 --incentivada --prazo 720

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

**Hoje:** precificação unificada (`precificar` com PU, cotação % VNA, durations
Macaulay e modificada, DV01, convexidade e current yield em uma única passagem;
YTM e marcação a mercado acoplada à ETTJ), curva de juros (ETTJ com flat-forward
como método default; interpolação linear e Nelson-Siegel disponíveis),
tributação (IR regressivo + IOF), comparação de produtos (linear e composta,
isenção por categoria), calendário real de dias úteis B3/SFN, dados oficiais
(Tesouro Direto, CDI via SGS/BCB, fundos via CVM) e relatório determinístico de
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
