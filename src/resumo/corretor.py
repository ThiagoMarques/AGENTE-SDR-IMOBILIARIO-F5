"""Resumo inteligente para o corretor (humano no loop)."""
from __future__ import annotations

from typing import Any

from src.qualificacao.lead import score_lead


def montar_resumo(estado: dict[str, Any]) -> dict[str, Any]:
    perfil = estado.get("perfil") or {}
    qual = score_lead(perfil)
    mensagens = estado.get("mensagens") or []
    return {
        "lead_id": estado.get("lead_id"),
        "perfil": perfil,
        "qualificacao": qual,
        "imoveis_sugeridos": estado.get("imoveis_sugeridos") or [],
        "agendamentos": estado.get("agendamentos") or [],
        "ultimas_mensagens": mensagens[-6:],
        "acao_sugerida": _acao(qual, estado),
    }


def _acao(qual: dict[str, Any], estado: dict[str, Any]) -> str:
    if estado.get("agendamentos"):
        return "Confirmar reunião/visita com o corretor responsável."
    if qual.get("pronto_para_agendar"):
        return "Lead qualificado: oferecer horários de visita/reunião."
    if qual.get("prioridade") == "quente":
        return "Priorizar retorno humano; completar campos faltantes."
    if qual.get("campos_faltantes"):
        return f"Continuar qualificação. Faltam: {', '.join(qual['campos_faltantes'])}."
    return "Manter nurture / follow-up."


def formatar_resumo_txt(resumo: dict[str, Any]) -> str:
    q = resumo["qualificacao"]
    linhas = [
        f"Lead: {resumo['lead_id']}",
        f"Prioridade: {q['prioridade']} (score {q['score']})",
        f"Perfil: {resumo.get('perfil')}",
        f"Imóveis sugeridos: {resumo.get('imoveis_sugeridos')}",
        f"Agendamentos: {resumo.get('agendamentos')}",
        f"Ação sugerida: {resumo.get('acao_sugerida')}",
        "",
        "Últimas mensagens:",
    ]
    for m in resumo.get("ultimas_mensagens") or []:
        linhas.append(f"  [{m.get('papel')}] {m.get('texto')}")
    return "\n".join(linhas)
