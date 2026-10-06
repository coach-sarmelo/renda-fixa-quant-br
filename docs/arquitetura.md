# Arquitetura

Como o `rfquant` está organizado por dentro. Para a matemática, veja
[formulas.md](formulas.md); para as fontes de dados, [dados.md](dados.md).

## Visão geral

```
Fonte oficial (Tesouro Transparente/CKAN — CSV público, sem token)
│
▼
Camada de dados e cache (providers + diskcache, download ≤ 1×/24 h)
│
▼
Núcleo quant (PU, duration, DV01, convexidade, YTM, current yield, marcação a mercado, ETTJ)
│
▼
Comparação (IR regressivo, IOF, taxa equivalente)
│
▼
Interfaces (CLI `rfq`, notebooks, biblioteca Python)
```

**Status das fontes:** três fontes oficiais em produção, cada uma dona de
um tipo de dado no mapa declarado (`src/rfquant/data/fontes.py`): títulos do
Tesouro Direto → CSV oficial do Tesouro Transparente (baixado no máximo
1×/24 h); CDI → série 12 do SGS/BCB (JSON, sem token); fundos → informes
diários da CVM. O provider brapi existe no código, mas fica **fora** do
mapa: o endpoint de renda fixa da brapi hoje exige plano pago — não é
utilizável e só é acionado se o usuário fixar `--fonte=brapi`
(detalhes em [dados.md](dados.md)).

## Princípios arquiteturais

### 1. Cálculo determinístico

Todo número vem de uma fórmula explícita aplicada a dados oficiais. As
mesmas entradas produzem sempre as mesmas saídas, no mesmo dia. Não há
geração de números por modelos de linguagem nem por fontes não auditáveis.

### 2. Dados atrás de uma interface

O acesso aos **títulos** passa pela interface abstrata `DataProvider`
(`src/rfquant/data/base.py`). Isso permite trocar a fonte sem mexer no
núcleo:

```python
class DataProvider(ABC):
    @abstractmethod
    def titulos_disponiveis(self, data: date | None = None) -> pd.DataFrame: ...

    @abstractmethod
    def historico_taxas(self, titulo: str, inicio: date, fim: date) -> pd.DataFrame: ...
```

Implementação existente: `TesouroOficialProvider` (CSV oficial do Tesouro
Transparente) — um download cacheado seguido de parsing/filtro; é a fonte
de produção de `--fonte=oficial`. O modelo normalizado de saída é o
`Titulo` (pydantic), com nome, tipo, vencimento, taxas e PUs de
compra/venda.

Os providers de **séries** — CDI (`SGSProvider`, SGS/BCB) e fundos
(`CVMFundosProvider`, CVM) — usam contrato próprio de série e **não**
estendem a `DataProvider`: `titulos_disponiveis`/`historico_taxas`
descrevem títulos, e forçar séries macro ou informes de fundos nesse molde
distorceria o contrato. A disciplina de contrato deles fica com a bateria
de `tests/test_data_contrato_series.py`, e a escolha da fonte por tipo de
dado é o mapa declarado de `src/rfquant/data/fontes.py` (`--fonte=auto`).

### 3. Cache obrigatório

Todo acesso HTTP passa por um cache `diskcache` (SQLite por baixo) com TTL
configurável — 24 h para o CSV oficial do Tesouro (o arquivo de ~14,5 MB é
baixado no máximo 1×/dia). Nenhum download redundante. O diretório padrão é
`~/.rfquant/cache` (`RFQ_CACHE_DIR` no `.env`).

### 4. Testável e auditável

Cada função de cálculo tem teste unitário com valores conhecidos — incluindo
**regressão contra PU oficiais publicados** pelo Tesouro
(`tests/test_regressao_oficial.py`, com fixture extraída byte a byte do CSV
oficial; contexto em [dados.md](dados.md)).

## Estrutura de diretórios

```
src/rfquant/
├── data/            # Providers (Tesouro oficial) + cache em disco
│   ├── base.py      #   Interface DataProvider + modelo Titulo
│   ├── tesouro_oficial.py  #   CSV oficial do Tesouro Transparente
│   ├── tesouro_direto.py   #   Provider brapi (não utilizável hoje)
│   └── cache.py     #   Cache HTTP (diskcache)
├── pricing/         # PU, duration, DV01, convexidade, YTM, current yield, marcação, curva
├── comparison/      # IR regressivo, IOF, taxa equivalente
├── cli.py           # Interface de linha de comando (rfq)
├── relatorio.py     # Relatório determinístico (Markdown)
└── config.py        # Settings (pydantic-settings, lê .env)
```

## Fluxo de dados típico

**Precificação** (`rfq tesouro precificar ...`):

1. O usuário invoca a CLI.
2. A CLI chama `rfquant.pricing.pu.calcular(...)` — matemática pura, sem rede.
3. O núcleo gera os fluxos de caixa e desconta pela taxa (base 252).
4. O resultado é formatado e impresso via `rich`.

**Listagem** (`rfq tesouro listar --fonte=oficial`):

1. A CLI instancia o provider oficial.
2. O provider baixa (ou lê do cache) o CSV do Tesouro Transparente.
3. O parsing normaliza as colunas para o modelo `Titulo` e filtra a
   `Data Base` mais recente.
4. A CLI renderiza a tabela via `rich`.

**Relatório** (`rfq relatorio gerar`):

1. A CLI monta um dicionário com a carteira de exemplo e métricas.
2. `rfquant.relatorio.gerar_offline(dados)` renderiza o Markdown
   deterministicamente — sem rede e sem chave de API.
3. O disclaimer regulatório é anexado ao rodapé automaticamente.

## Decisões de design

| Decisão | Motivo |
|---|---|
| Python 3.11+ | Melhorias de tipagem e performance |
| Pydantic v2 | Validação forte, serialização rápida |
| diskcache | Cache em disco, sem servidor externo |
| Typer + Rich | CLI moderna com saída formatada |
| scipy.optimize | YTM (brentq) e ajuste de curva (Nelson-Siegel) sem dependências pesadas |
| Falha explícita de fonte | `--fonte=brapi` sem token (ou com paywall) falha com mensagem clara — nunca há troca silenciosa de fonte |
