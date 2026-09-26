"""Qualificação de leads (regras didáticas + score)."""
from __future__ import annotations

from typing import Any

import config
from src.coleta.perfil import (
    CAMPOS_ALUGUEL,
    CAMPOS_COMPRA,
    CAMPOS_INVESTIMENTO,
    campos_faltantes,
    proxima_pergunta,
)

__all__ = [
    "CAMPOS_ALUGUEL",
    "CAMPOS_COMPRA",
    "CAMPOS_INVESTIMENTO",
    "campos_faltantes",
    "proxima_pergunta",
    "score_lead",
]


def score_lead(perfil: dict[str, Any]) -> dict[str, Any]:
    """Score 0–100 com prioridade quente/morno/frio."""
    faltantes = campos_faltantes(perfil)
    intencao = (perfil.get("intencao") or "").lower()
    if intencao in {"investimento", "investir"}:
        total = len(CAMPOS_INVESTIMENTO)
    elif intencao in {"aluguel", "alugar"}:
        total = len(CAMPOS_ALUGUEL)
    else:
        total = len(CAMPOS_COMPRA)

    preenchidos = total - len(faltantes)
    base = int(100 * (preenchidos / total)) if total else 0

    urgencia = str(perfil.get("urgencia") or "").lower()
    if urgencia in {"alta", "urgente", "imediata", "agora"}:
        base = min(100, base + 15)
    elif urgencia in {"baixa", "sem pressa"}:
        base = max(0, base - 10)

    if base >= config.SCORE_QUENTE:
        prioridade = "quente"
    elif base >= config.SCORE_MORNO:
        prioridade = "morno"
    else:
        prioridade = "frio"

    return {
        "score": base,
        "prioridade": prioridade,
        "campos_faltantes": faltantes,
        "pronto_para_agendar": len(faltantes) == 0 and base >= config.SCORE_MORNO,
    }
