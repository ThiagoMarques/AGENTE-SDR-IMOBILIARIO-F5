"""Repositório: estado de conversa no PostgreSQL (API compatível com o JSON antigo)."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from src.db.models import Agendamento, ImovelSugerido, Lead, Mensagem
from src.qualificacao.lead import score_estado


def _estado_vazio(lead_id: str) -> dict[str, Any]:
    return {
        "lead_id": lead_id,
        "criado_em": datetime.now(timezone.utc).isoformat(),
        "perfil": {},
        "mensagens": [],
        "agendamentos": [],
        "imoveis_sugeridos": [],
    }


def lead_para_estado(lead: Lead) -> dict[str, Any]:
    return {
        "lead_id": lead.id,
        "criado_em": lead.criado_em.isoformat() if lead.criado_em else None,
        "atualizado_em": lead.atualizado_em.isoformat() if lead.atualizado_em else None,
        "perfil": dict(lead.perfil or {}),
        "controle_sdr": dict(lead.controle or {}),
        "score": lead.score,
        "prioridade": lead.prioridade,
        "mensagens": [
            {
                "papel": m.papel,
                "texto": m.texto,
                "em": m.em.isoformat() if m.em else None,
            }
            for m in (lead.mensagens or [])
        ],
        "agendamentos": [
            {
                "tipo": a.tipo,
                "horario": a.horario,
                "imovel_id": a.imovel_id,
                "status": a.status,
                "inicio": a.inicio.isoformat() if a.inicio else None,
                "detalhes": dict(a.detalhes or {}),
            }
            for a in sorted(lead.agendamentos or [], key=lambda x: x.id or 0)
        ],
        "imoveis_sugeridos": [i.imovel_id for i in (lead.imoveis_sugeridos or [])],
    }


def carregar(session: Session, lead_id: str) -> dict[str, Any]:
    lead = session.scalar(
        select(Lead)
        .where(Lead.id == lead_id)
        .options(
            selectinload(Lead.mensagens),
            selectinload(Lead.agendamentos),
            selectinload(Lead.imoveis_sugeridos),
        )
    )
    if not lead:
        return _estado_vazio(lead_id)
    return lead_para_estado(lead)


def salvar(session: Session, estado: dict[str, Any]) -> str:
    lead_id = str(estado["lead_id"])
    perfil = dict(estado.get("perfil") or {})
    qual = score_estado(estado)  # mesmo score (com engajamento) que o agente mostra

    lead = session.scalar(
        select(Lead)
        .where(Lead.id == lead_id)
        .options(
            selectinload(Lead.mensagens),
            selectinload(Lead.agendamentos),
            selectinload(Lead.imoveis_sugeridos),
        )
    )
    if not lead:
        lead = Lead(id=lead_id, mensagens=[], agendamentos=[], imoveis_sugeridos=[])
        session.add(lead)

    lead.perfil = perfil
    lead.controle = dict(estado.get("controle_sdr") or {})
    lead.score = int(qual["score"])
    lead.prioridade = str(qual["prioridade"])
    lead.atualizado_em = datetime.now(timezone.utc)

    # Substitui coleções derivadas do estado (fonte da verdade na POC)
    lead.mensagens.clear()
    for m in estado.get("mensagens") or []:
        em = m.get("em")
        if isinstance(em, str):
            try:
                em_dt = datetime.fromisoformat(em.replace("Z", "+00:00"))
            except ValueError:
                em_dt = datetime.now(timezone.utc)
        else:
            em_dt = datetime.now(timezone.utc)
        lead.mensagens.append(
            Mensagem(papel=m.get("papel") or "lead", texto=m.get("texto") or "", em=em_dt)
        )

    lead.agendamentos.clear()
    for a in estado.get("agendamentos") or []:
        inicio = None
        if a.get("inicio"):
            try:
                inicio = datetime.fromisoformat(str(a["inicio"]))
            except ValueError:
                inicio = None
        lead.agendamentos.append(
            Agendamento(
                horario=a.get("horario") or "",
                tipo=a.get("tipo") or "reuniao",
                status=a.get("status") or "agendado",
                imovel_id=a.get("imovel_id"),
                inicio=inicio,
                detalhes=a.get("detalhes") or None,
            )
        )

    lead.imoveis_sugeridos.clear()
    for item in estado.get("imoveis_sugeridos") or []:
        if isinstance(item, dict):
            lead.imoveis_sugeridos.append(
                ImovelSugerido(imovel_id=str(item.get("id") or item.get("imovel_id")), snapshot=item)
            )
        else:
            lead.imoveis_sugeridos.append(ImovelSugerido(imovel_id=str(item), snapshot=None))

    session.flush()
    return lead_id


def listar_leads(session: Session) -> list[dict[str, Any]]:
    leads = session.scalars(
        select(Lead)
        .options(
            selectinload(Lead.mensagens),
            selectinload(Lead.agendamentos),
            selectinload(Lead.imoveis_sugeridos),
        )
        .order_by(Lead.atualizado_em.desc())
    ).all()
    return [lead_para_estado(l) for l in leads]
