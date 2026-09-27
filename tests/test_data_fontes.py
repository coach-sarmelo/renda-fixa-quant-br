"""Testes do resolvedor declarado de fontes (mapa fixo dado→provider).

O mapa é uma declaração, não uma escolha: os testes fixam as entradas
(títulos → oficial; CDI → SGS; fundos → CVM), o determinismo da resolução
automática (mesmo dado ⇒ mesma fonte com e sem BRAPI_TOKEN no ambiente —
brapi não participa do mapa) e a falha explícita para dado/provider fora
do conjunto declarado — nunca fallback silencioso. Cada entrada única do
mapa É a garantia de ausência de cadeia de fallback: não existe segunda
opção para consultar.
"""

from __future__ import annotations

import pytest

from rfquant.config import settings
from rfquant.data.cvm_fundos import CVMFundosProvider
from rfquant.data.fontes import MAPA_FONTES, provider_do_dado, rotulo_do_provider
from rfquant.data.sgs_bcb import SGSProvider
from rfquant.data.tesouro_direto import TesouroDiretoProvider
from rfquant.data.tesouro_oficial import TesouroOficialProvider


# ----------------------------------------------------------------------
# Mapa declarado: entradas fixadas como contrato
# ----------------------------------------------------------------------
def test_mapa_declarado_fixa_a_fonte_de_cada_dado() -> None:
    """Uma fonte canônica por dado: títulos → oficial; CDI → SGS; fundos → CVM."""
    assert MAPA_FONTES["titulos"] is TesouroOficialProvider
    assert MAPA_FONTES["cdi"] is SGSProvider
    assert MAPA_FONTES["fundos"] is CVMFundosProvider
    assert len(MAPA_FONTES) == 3  # sem entradas além das declaradas


def test_brapi_fica_fora_do_mapa() -> None:
    """O provider brapi não participa da resolução automática: só é usado
    quando o usuário fixa a fonte explicitamente (--fonte=brapi na CLI)."""
    assert "brapi" not in MAPA_FONTES
    assert TesouroDiretoProvider not in MAPA_FONTES.values()


# ----------------------------------------------------------------------
# Resolução automática: determinística, sem consulta a token/ambiente
# ----------------------------------------------------------------------
def test_provider_do_dado_instancia_a_fonte_declarada() -> None:
    """Cada dado do mapa instancia exatamente o provider declarado."""
    assert isinstance(provider_do_dado("titulos"), TesouroOficialProvider)
    assert isinstance(provider_do_dado("cdi"), SGSProvider)
    assert isinstance(provider_do_dado("fundos"), CVMFundosProvider)


def test_resolucao_e_deterministica_com_e_sem_token_no_ambiente(monkeypatch) -> None:
    """Mesmo dado ⇒ mesma fonte com e sem BRAPI_TOKEN no ambiente: a
    resolução não consulta token — brapi fora do mapa não muda o resultado."""
    monkeypatch.delenv("BRAPI_TOKEN", raising=False)
    monkeypatch.setattr(settings, "brapi_token", None)
    sem_token = type(provider_do_dado("titulos"))

    monkeypatch.setenv("BRAPI_TOKEN", "token-ficticio")
    monkeypatch.setattr(settings, "brapi_token", "token-ficticio")
    com_token = type(provider_do_dado("titulos"))

    assert sem_token is TesouroOficialProvider
    assert com_token is sem_token


# ----------------------------------------------------------------------
# Falha explícita: dado ou provider fora do conjunto declarado
# ----------------------------------------------------------------------
def test_dado_fora_do_mapa_levanta_erro_ptbr() -> None:
    """Dado sem fonte declarada ⇒ ValueError em pt-BR, com as opções —
    nunca fallback silencioso para outra fonte."""
    with pytest.raises(ValueError, match="Sem fonte declarada") as erro:
        provider_do_dado("cotacoes")
    assert "cotacoes" in str(erro.value)
    assert "titulos" in str(erro.value)  # as declaradas acompanham a mensagem


def test_rotulo_do_provider_para_o_anuncio_da_fonte() -> None:
    """Rótulo anunciado na saída ("fonte: <rótulo>") para cada provider do mapa."""
    assert rotulo_do_provider(TesouroOficialProvider()) == "oficial"
    assert rotulo_do_provider(SGSProvider()) == "sgs"
    assert rotulo_do_provider(CVMFundosProvider()) == "cvm"


def test_rotulo_de_provider_fora_do_mapa_levanta_erro() -> None:
    """Provider sem entrada declarada não recebe rótulo: ValueError — o
    anúncio nunca inventa nome de fonte (brapi nem pertence ao conjunto)."""
    with pytest.raises(ValueError, match="Sem rótulo de fonte"):
        rotulo_do_provider(TesouroDiretoProvider())
