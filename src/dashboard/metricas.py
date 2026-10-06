"""Dashboard mínimo: agrega leads no PostgreSQL."""
from __future__ import annotations

from typing import Any

from src.agenda.scheduler import convite_enviado
from src.memoria import conversa as memoria
from src.qualificacao.lead import score_estado


def montar_dashboard() -> dict[str, Any]:
    conversas = memoria.listar_todos()
    por_prioridade = {"quente": 0, "morno": 0, "frio": 0}
    agendamentos = 0
    captura = {"com_nome": 0, "com_email": 0, "convites_enviados": 0}
    leads_out = []
    for c in conversas:
        perfil = c.get("perfil") or {}
        captura["com_nome"] += bool(perfil.get("nome"))
        captura["com_email"] += bool(perfil.get("email"))
        captura["convites_enviados"] += sum(
            1 for a in c.get("agendamentos") or []
            if a.get("status", "agendado") == "agendado" and convite_enviado(a)
        )
        # Recalcula sempre: o valor gravado no banco é só cache e pode estar
        # desatualizado se a regra de qualificação mudar (lista = detalhe).
        q = score_estado(c)
        prioridade = q["prioridade"]
        score = q["score"]
        por_prioridade[prioridade] = por_prioridade.get(prioridade, 0) + 1
        agendamentos += sum(
            1 for a in c.get("agendamentos") or [] if a.get("status", "agendado") == "agendado"
        )
        leads_out.append(
            {
                "lead_id": c.get("lead_id"),
                "nome": perfil.get("nome"),
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
        "captura": captura,
        "leads": leads_out,
    }
