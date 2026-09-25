"""Dashboard mínimo: agrega leads/conversas salvas."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import config
from src.qualificacao.lead import score_lead


def carregar_conversas() -> list[dict[str, Any]]:
    config.CONVERSAS_DIR.mkdir(parents=True, exist_ok=True)
    itens = []
    for path in sorted(config.CONVERSAS_DIR.glob("*.json")):
        with path.open(encoding="utf-8") as f:
            itens.append(json.load(f))
    return itens


def montar_dashboard() -> dict[str, Any]:
    conversas = carregar_conversas()
    por_prioridade = {"quente": 0, "morno": 0, "frio": 0}
    agendamentos = 0
    for c in conversas:
        q = score_lead(c.get("perfil") or {})
        por_prioridade[q["prioridade"]] = por_prioridade.get(q["prioridade"], 0) + 1
        agendamentos += len(c.get("agendamentos") or [])
    return {
        "total_conversas": len(conversas),
        "por_prioridade": por_prioridade,
        "agendamentos": agendamentos,
        "leads": [
            {
                "lead_id": c.get("lead_id"),
                "score": score_lead(c.get("perfil") or {})["score"],
                "prioridade": score_lead(c.get("perfil") or {})["prioridade"],
                "mensagens": len(c.get("mensagens") or []),
            }
            for c in conversas
        ],
    }
