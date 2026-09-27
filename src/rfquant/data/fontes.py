"""Resolvedor declarado de fontes de dados — mapa fixo dado→provider.

O mapa abaixo é uma declaração, não uma escolha: cada tipo de dado tem
exatamente uma fonte canônica. Não é seleção dinâmica e não existe cadeia
de fallback em runtime — a fonte é decidida uma única vez por execução e,
se falhar, o erro sobe tratado (mensagem pt-BR + exit ≠ 0 na CLI); nunca
há troca de fonte no meio do caminho.

Mapa declarado (dado → provider):

    titulos → TesouroOficialProvider  (CSV oficial do Tesouro Direto, sem token)
    cdi     → SGSProvider             (SGS/BCB, série 12 — CDI diário)
    fundos  → CVMFundosProvider       (informes diários de fundos da CVM)

O provider brapi (``rfquant.data.tesouro_direto``) fica FORA do mapa:
depende de ``BRAPI_TOKEN`` e só é usado quando o usuário fixa a fonte na
CLI (``--fonte=brapi``, pino de reprodutibilidade). Por não consultar
ambiente, token nem disponibilidade de rede, a resolução automática é
determinística: o mesmo dado resolve para a mesma fonte com ou sem
``BRAPI_TOKEN`` no ambiente.
"""

from __future__ import annotations

from typing import Any

from rfquant.data.cvm_fundos import CVMFundosProvider
from rfquant.data.sgs_bcb import SGSProvider
from rfquant.data.tesouro_oficial import TesouroOficialProvider

# Mapa declarado: dado → provider. Fixo e determinístico — a resolução é
# uma busca por chave; não há preferências, tentativa-e-erro nem segunda
# opção caso a fonte declarada falhe.
MAPA_FONTES: dict[str, type] = {
    "titulos": TesouroOficialProvider,
    "cdi": SGSProvider,
    "fundos": CVMFundosProvider,
}

# Rótulo de anúncio de cada fonte na saída da CLI ("fonte: <rótulo>").
_ROTULOS: dict[type, str] = {
    TesouroOficialProvider: "oficial",
    SGSProvider: "sgs",
    CVMFundosProvider: "cvm",
}


def provider_do_dado(dado: str) -> Any:
    """Instancia a fonte declarada no mapa para o dado informado.

    Resolução automática (``--fonte=auto``): puramente tabular — não
    consulta token, ambiente nem rede; a mesma entrada produz sempre a
    mesma fonte. Dado fora do mapa ⇒ ``ValueError`` em pt-BR: falha
    explícita, nunca fallback silencioso para outra fonte.
    """
    try:
        fabrica = MAPA_FONTES[dado]
    except KeyError:
        declaradas = ", ".join(sorted(MAPA_FONTES))
        msg = f"Sem fonte declarada para o dado '{dado}' (declaradas: {declaradas})."
        raise ValueError(msg) from None
    return fabrica()


def rotulo_do_provider(provider: Any) -> str:
    """Rótulo da fonte resolvida, para o anúncio na saída ("fonte: <rótulo>").

    Provider fora do conjunto declarado ⇒ ``ValueError`` — o anúncio nunca
    inventa nome de fonte.
    """
    try:
        return _ROTULOS[type(provider)]
    except KeyError:
        msg = f"Sem rótulo de fonte declarado para {type(provider).__name__}."
        raise ValueError(msg) from None
