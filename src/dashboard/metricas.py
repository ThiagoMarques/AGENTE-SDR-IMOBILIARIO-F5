"""Dashboard mínimo: agrega leads no PostgreSQL."""
from __future__ import annotations

from typing import Any

from src.memoria import conversa as memoria
from src.qualificacao.lead import score_estado


def montar_dashboard() -> dict[str, Any]:
    conversas = memoria.listar_todos()
    por_prioridade = {"quente": 0, "morno": 0, "frio": 0}
    agendamentos = 0
    leads_out = []
    for c in conversas:
        perfil = c.get("perfil") or {}
        # Recalcula sempre: o valor gravado no banco é só cache e pode estar
        # desatualizado se a regra de qualificação mudar (lista = detalhe).
        q = score_estado(c)
        prioridade = q["prioridade"]
        score = q["score"]
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
