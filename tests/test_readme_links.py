"""Higiene dos links do README: formato, alvos locais e (rede) status 200.

Lê o README.md da raiz do repositório (caminho relativo a este arquivo) —
funciona nos dois repositórios, que têm READMEs diferentes. Alvos locais
relativos são resolvidos a partir da raiz; âncoras puras (``#seção``) são
ignoradas. Os alvos externos http(s) só são baixados no teste marcado
``network`` (job de CI semanal; deselecionado na suíte padrão pelos
addopts do pyproject).
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest
import requests

README = Path(__file__).resolve().parent.parent / "README.md"

PADRAO_IMAGEM = re.compile(r"!\[[^\]]*\]\(([^)]+)\)")
PADRAO_LINK = re.compile(r"\[([^\]]*)\]\(([^)]+)\)")
PADRAO_ESQUEMA = re.compile(r"^[A-Za-z][A-Za-z0-9+.-]*:")


def _texto_sem_blocos_de_codigo() -> str:
    """README sem os blocos cercados por ``` (o GitHub não os renderiza como link)."""
    texto = README.read_text(encoding="utf-8")
    return re.sub(r"^```.*?^```", "", texto, flags=re.S | re.M)


def _alvos() -> list[str]:
    """Todos os alvos de link do README (imagens ``![alt](alvo)`` inclusas)."""
    texto = _texto_sem_blocos_de_codigo()
    alvos = [m.group(1) for m in PADRAO_IMAGEM.finditer(texto)]
    texto_sem_imagens = PADRAO_IMAGEM.sub("", texto)
    alvos.extend(m.group(2) for m in PADRAO_LINK.finditer(texto_sem_imagens))
    return alvos


def _e_alvo_valido(alvo: str) -> bool:
    """Formato aceito: âncora pura, http(s):// ou caminho relativo sem esquema."""
    if not alvo or re.search(r"\s", alvo):
        return False  # destino vazio ou com espaço não é link renderizável
    if alvo.startswith("#"):
        return True
    if alvo.startswith(("http://", "https://")):
        return True
    return PADRAO_ESQUEMA.match(alvo) is None  # relativo: sem esquema (mailto:, ftp:, ...)


def test_readme_existe() -> None:
    """Guarda de sanidade: o README da raiz existe (todos os testes dependem dele)."""
    assert README.is_file()


def test_links_tem_formato_valido() -> None:
    """Todo alvo é âncora pura, http(s):// ou caminho relativo — nada além."""
    invalidos = [alvo for alvo in _alvos() if not _e_alvo_valido(alvo)]
    assert invalidos == []


def test_alvos_locais_existem() -> None:
    """Alvos locais relativos existem em disco, resolvidos a partir da raiz.

    A âncora de seção no fim do alvo (``docs/x.md#seção``) é ignorada —
    só o caminho do arquivo é cobrado aqui.
    """
    faltando = []
    for alvo in _alvos():
        if alvo.startswith(("#", "http://", "https://")):
            continue
        caminho = alvo.split("#", 1)[0]
        if caminho and not (README.parent / caminho).exists():
            faltando.append(alvo)
    assert faltando == []


@pytest.mark.network
@pytest.mark.parametrize(
    "alvo",
    [a for a in _alvos() if a.startswith(("http://", "https://"))],
)
def test_alvos_externos_respondem_200(alvo: str) -> None:
    """Alvo externo http(s) responde 200 (segue redirecionamento; timeout 30 s)."""
    resposta = requests.get(alvo, timeout=30)
    assert resposta.status_code == 200
