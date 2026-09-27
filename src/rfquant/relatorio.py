"""Relatório determinístico de carteira de renda fixa.

Gera Markdown a partir de um dicionário de valores já calculados pelo
núcleo determinístico: sem LLM, sem rede e sem `openai`.
"""

from __future__ import annotations

from dataclasses import asdict, is_dataclass
from datetime import date
from pathlib import Path
from typing import Any

# Texto regulatório do disclaimer (constante única deste módulo). Se a mesma
# frase regulatória vier a existir em outro módulo, as duas cópias devem
# evoluir juntas — este módulo não importa nada de fora do núcleo
# determinístico.
DISCLAIMER_PADRAO = (
    "Este material é **educacional e informacional**. Não constitui "
    "consultoria de valores mobiliários nos termos da Resolução CVM nº 20/2021. "
    "Não há recomendação personalizada de compra ou venda. Rentabilidade passada "
    "não garante rentabilidade futura. Consulte um profissional certificado antes "
    "de tomar decisões de investimento."
)


def _serializar(obj: Any) -> Any:
    """Converte dataclasses, datas e NumPy arrays em estruturas serializáveis."""
    if is_dataclass(obj) and not isinstance(obj, type):
        return {k: _serializar(v) for k, v in asdict(obj).items()}
    if isinstance(obj, date):
        return obj.isoformat()
    if isinstance(obj, dict):
        return {k: _serializar(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [_serializar(v) for v in obj]
    try:
        import numpy as np

        if isinstance(obj, np.ndarray):
            return obj.tolist()
        if isinstance(obj, (np.floating, np.integer)):
            return obj.item()
    except ImportError:
        pass
    return obj


def _tabela(itens: list[dict[str, Any]]) -> list[str]:
    """Renderiza uma lista de dicts como tabela Markdown.

    O cabeçalho vem das chaves do primeiro item (ordem de inserção —
    determinística); item sem uma chave recebe célula vazia.
    """
    chaves = list(itens[0].keys())
    linhas = [
        "| " + " | ".join(chaves) + " |",
        "| " + " | ".join(["---"] * len(chaves)) + " |",
    ]
    for item in itens:
        linhas.append("| " + " | ".join(str(item.get(k, "")) for k in chaves) + " |")
    return linhas


def gerar_offline(dados: dict[str, Any]) -> str:
    """Gera um relatório estruturado em Markdown sem usar LLM.

    Determinístico: a mesma entrada produz a mesma saída no mesmo dia
    (o cabeçalho carrega `date.today()`). Sem rede e sem dependências de
    LLM — útil para a CLI e para testes. O disclaimer regulatório fecha
    o relatório.
    """
    linhas: list[str] = ["# Relatório de Carteira de Renda Fixa\n"]
    linhas.append(f"*Gerado em {date.today().isoformat()}*\n")

    for secao, valor in _serializar(dados).items():
        titulo = secao.replace("_", " ").title()
        linhas.append(f"\n## {titulo}\n")
        if isinstance(valor, list):
            if valor and all(isinstance(item, dict) for item in valor):
                linhas.extend(_tabela(valor))
            else:
                for item in valor:
                    linhas.append(f"- {item}")
        elif isinstance(valor, dict):
            for k, v in valor.items():
                linhas.append(f"- **{k}**: {v}")
        else:
            linhas.append(str(valor))

    linhas.append(f"\n---\n\n> **Disclaimer.** {DISCLAIMER_PADRAO}\n")
    return "\n".join(linhas)


def salvar(conteudo: str, caminho: str) -> None:
    """Salva o relatório em disco (markdown ou texto), criando diretórios pais."""
    p = Path(caminho)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(conteudo, encoding="utf-8")
