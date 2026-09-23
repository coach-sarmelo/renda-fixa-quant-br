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
