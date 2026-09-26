"""Dashboard mínimo: agrega leads no PostgreSQL."""
from __future__ import annotations

from typing import Any

from src.memoria import conversa as memoria
from src.qualificacao.lead import score_lead


def montar_dashboard() -> dict[str, Any]:
    conversas = memoria.listar_todos()
    por_prioridade = {"quente": 0, "morno": 0, "frio": 0}
    agendamentos = 0
    leads_out = []
    for c in conversas:
        perfil = c.get("perfil") or {}
        q = score_lead(perfil)
        prioridade = c.get("prioridade") or q["prioridade"]
        score = c.get("score") if c.get("score") is not None else q["score"]
        por_prioridade[prioridade] = por_prioridade.get(prioridade, 0) + 1
        agendamentos += len(c.get("agendamentos") or [])
        leads_out.append(
            {
                "lead_id": c.get("lead_id"),
                "score": score,
                "prioridade": prioridade,
                "mensagens": len(c.get("mensagens") or []),
                "intencao": perfil.get("intencao"),
                "atualizado_em": c.get("atualizado_em"),
            }
        )
    return {
        "total_conversas": len(conversas),
        "por_prioridade": por_prioridade,
        "agendamentos": agendamentos,
        "leads": leads_out,
    }
