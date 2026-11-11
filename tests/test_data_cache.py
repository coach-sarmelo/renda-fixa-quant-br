"""Testes do cache HTTP: TTL por comportamento.

Padrões usados aqui (definidos no conftest, replicáveis): ``fetch_mockado``
(requests.get instrumentado), ``cache_isolado`` (diskcache em tmp_path) e
``relogio`` (patch de time.time — diskcache grava expire absoluto; nunca sleep).
"""

from __future__ import annotations

from datetime import date

from rfquant.data.tesouro_direto import TesouroDiretoProvider

DATA_REF = date(2026, 1, 2)
# TTL do endpoint /treasury em _fetch_treasury: 900s
TTL_TREASURY = 900


def test_ttl_um_hit_dentro_do_ttl(
    provider_tesouro_teste: TesouroDiretoProvider,
    fetch_mockado,
    cache_isolado,
    relogio,
) -> None:
    """Chamadas dentro do TTL → um único fetch HTTP (as demais são hit de cache)."""
    df1 = provider_tesouro_teste.titulos_disponiveis(data=DATA_REF)
    df2 = provider_tesouro_teste.titulos_disponiveis(data=DATA_REF)
    assert fetch_mockado.chamadas == 1
    assert len(df1) == 5
    assert len(df2) == 5

    relogio.avancar(TTL_TREASURY - 1)  # 1s antes de expirar
    provider_tesouro_teste.titulos_disponiveis(data=DATA_REF)
    assert fetch_mockado.chamadas == 1  # ainda hit


def test_ttl_dois_hits_apos_expiracao(
    provider_tesouro_teste: TesouroDiretoProvider,
    fetch_mockado,
    cache_isolado,
    relogio,
) -> None:
    """Relógio avança além do TTL → cache expira → segundo fetch real."""
    provider_tesouro_teste.titulos_disponiveis(data=DATA_REF)
    assert fetch_mockado.chamadas == 1

    relogio.avancar(TTL_TREASURY + 1)
    provider_tesouro_teste.titulos_disponiveis(data=DATA_REF)
    assert fetch_mockado.chamadas == 2


def test_obter_ou_parsear_frame_hit_bypass_ttl_e_portabilidade(
    cache_isolado,
    relogio,
) -> None:
    """Seam 3: `cache.obter_ou_parsear_frame` gerencia a chave `::df`, a
    serialização portável sem pyarrow, o bypass `usar_cache=False` e o TTL."""
    import pickle

    import pandas as pd

    from rfquant.data import cache

    assert "rfquant/0.1.0" in cache.USER_AGENT

    chamadas = 0
    url = "https://exemplo.gov.br/dados.csv"

    def construir() -> pd.DataFrame:
        nonlocal chamadas
        chamadas += 1
        return pd.DataFrame({"nome": ["LTN 2027"], "pu": [850.5], "versao": [chamadas]})

    df1 = cache.obter_ou_parsear_frame(url, ttl=60, construtor=construir)
    assert chamadas == 1
    assert df1["versao"].iloc[0] == 1

    # Payload gravado na chave ::df é o dict portável (sem pyarrow no pickle)
    payload = cache.get(f"{url}::df")
    assert isinstance(payload, dict)
    assert b"pyarrow" not in pickle.dumps(payload)

    # Hit dentro do TTL: não chama `construir` novamente
    df2 = cache.obter_ou_parsear_frame(url, ttl=60, construtor=construir)
    assert chamadas == 1
    assert df2.equals(df1)

    # usar_cache=False força reconstrução e atualiza a entrada
    df3 = cache.obter_ou_parsear_frame(url, ttl=60, construtor=construir, usar_cache=False)
    assert chamadas == 2
    assert df3["versao"].iloc[0] == 2

    # Após expiração do TTL, reconstrói novamente
    relogio.avancar(61)
    df4 = cache.obter_ou_parsear_frame(url, ttl=60, construtor=construir)
    assert chamadas == 3
    assert df4["versao"].iloc[0] == 3
