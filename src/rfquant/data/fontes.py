"""Resolvedor declarado de fontes de dados — mapa fixo dado→(provider, rótulo).

O mapa abaixo é uma declaração, não uma escolha: cada tipo de dado tem
exatamente uma fonte canônica, com o rótulo do anúncio na MESMA entrada.
Não é seleção dinâmica e não existe cadeia de fallback em runtime — a
fonte é decidida uma única vez por execução e, se falhar, o erro sobe
tratado (mensagem pt-BR + exit ≠ 0 na CLI); nunca há troca de fonte no
meio do caminho.

Mapa declarado (dado → provider, rótulo do anúncio "fonte: <rótulo>"):

    titulos → TesouroOficialProvider  ("oficial")  — CSV oficial do Tesouro Direto, sem token
    cdi     → SGSProvider             ("sgs")      — SGS/BCB, série 12 — CDI diário
    fundos  → CVMFundosProvider       ("cvm")      — informes diários de fundos da CVM

O provider brapi (``rfquant.data.tesouro_direto``) fica FORA do mapa:
depende de ``BRAPI_TOKEN`` e só é usado quando o usuário fixa a fonte na
CLI (``--fonte=brapi``, pino de reprodutibilidade). Por não consultar
ambiente, token nem disponibilidade de rede, a resolução automática é
determinística: o mesmo dado resolve para a mesma fonte com ou sem
``BRAPI_TOKEN`` no ambiente.
"""

from __future__ import annotations

from typing import Literal, overload

from rfquant.data.cvm_fundos import CVMFundosProvider
from rfquant.data.sgs_bcb import SGSProvider
from rfquant.data.tesouro_oficial import TesouroOficialProvider

# União fechada dos providers com fonte declarada — o retorno de
# `provider_do_dado` nunca é um Any: a fronteira CLI↔data fica checada
# estaticamente (mypy) e as sobrecargas abaixo dão a classe exata de cada
# dado no ponto de chamada.
ProviderDeclarado = TesouroOficialProvider | SGSProvider | CVMFundosProvider

# Mapa declarado: dado → (provider, rótulo do anúncio). Fixo e
# determinístico — a resolução é uma busca por chave; não há preferências,
# tentativa-e-erro nem segunda opção caso a fonte declarada falhe. Provider
# e rótulo vivem na MESMA entrada: não há mapas paralelos para manter em
# sincronia.
MAPA_FONTES: dict[str, tuple[type[ProviderDeclarado], str]] = {
    "titulos": (TesouroOficialProvider, "oficial"),
    "cdi": (SGSProvider, "sgs"),
    "fundos": (CVMFundosProvider, "cvm"),
}


@overload
def provider_do_dado(dado: Literal["titulos"]) -> TesouroOficialProvider: ...


@overload
def provider_do_dado(dado: Literal["cdi"]) -> SGSProvider: ...


@overload
def provider_do_dado(dado: Literal["fundos"]) -> CVMFundosProvider: ...


@overload
def provider_do_dado(dado: str) -> ProviderDeclarado: ...


def provider_do_dado(dado: str) -> ProviderDeclarado:
    """Instancia a fonte declarada no mapa para o dado informado.

    Resolução automática (``--fonte=auto``): puramente tabular — não
    consulta token, ambiente nem rede; a mesma entrada produz sempre a
    mesma fonte. Dado fora do mapa ⇒ ``ValueError`` em pt-BR: falha
    explícita, nunca fallback silencioso para outra fonte.
    """
    try:
        fabrica, _ = MAPA_FONTES[dado]
    except KeyError:
        declaradas = ", ".join(sorted(MAPA_FONTES))
        msg = f"Sem fonte declarada para o dado '{dado}' (declaradas: {declaradas})."
        raise ValueError(msg) from None
    return fabrica()


def rotulo_do_provider(provider: object) -> str:
    """Rótulo da fonte resolvida, para o anúncio na saída ("fonte: <rótulo>").

    Provider fora do conjunto declarado ⇒ ``ValueError`` — o anúncio nunca
    inventa nome de fonte.
    """
    for fabrica, rotulo in MAPA_FONTES.values():
        if type(provider) is fabrica:
            return rotulo
    msg = f"Sem rótulo de fonte declarado para {type(provider).__name__}."
    raise ValueError(msg)
