"""Conversa entre um lead simulado e o agente."""
from __future__ import annotations

import uuid
from typing import Any

from treinador import llm
from treinador.canal import PREFIXO_LEAD, Canal
from treinador.personas import Persona

_SISTEMA = (
    "Você interpreta um lead brasileiro conversando por chat com o assistente de uma imobiliária. "
    "Fale como uma pessoa real no WhatsApp: mensagens curtas, informais, às vezes com erro de digitação. "
    "Se a persona descrever outro jeito de falar (idade, ritmo, confusões, sotaque, humor), esse jeito vale mais "
    "que o padrão: mantenha-o em todas as mensagens. "
    "Nunca diga que é uma IA nem descreva a persona. Mande uma mensagem por vez. "
    "Siga o objetivo, mas reaja ao que o assistente disser: se ele perguntar algo, responda do jeito da persona; "
    "se ele sugerir algo, aceite ou recuse de forma coerente com o objetivo. "
    "Encerre (encerrar=true) quando o objetivo for cumprido, quando a conversa travar ou quando você, "
    "como cliente real, desistiria. "
    'Responda SOMENTE JSON: {"mensagem": "texto do lead", "encerrar": false, "motivo": "por que encerrou, se encerrou"}'
)


def _historico(conversa: list[dict[str, Any]]) -> str:
    nomes = {"lead": "VOCÊ", "agente": "ASSISTENTE"}
    return "\n".join(f"{nomes[m['papel']]}: {m['texto']}" for m in conversa) or "(a conversa ainda não começou)"


def _proxima_mensagem(persona: Persona, conversa: list[dict[str, Any]]) -> tuple[str | None, str]:
    usuario = (
        f"Persona: {persona.descricao}\nObjetivo: {persona.objetivo}\n\n"
        f"Conversa até agora:\n{_historico(conversa)}\n\nSua próxima mensagem:"
    )
    bruto = llm.json_do_llm(_SISTEMA, usuario, temperatura=0.8)
    mensagem = str(bruto.get("mensagem") or "").strip()
    if bruto.get("encerrar") or not mensagem:
        return None, str(bruto.get("motivo") or "persona encerrou")
    return mensagem, ""


def conversar(
    persona: Persona,
    canal: Canal,
    *,
    usar_llm: bool,
    max_turnos: int,
) -> dict[str, Any]:
    lead_id = f"{PREFIXO_LEAD}{persona.id}-{uuid.uuid4().hex[:6]}"
    conversa: list[dict[str, Any]] = []
    fim, erro = "roteiro concluído", None
    roteiro = iter(persona.roteiro)

    for _ in range(max_turnos):
        if usar_llm:
            mensagem, motivo = _proxima_mensagem(persona, conversa)
        else:
            mensagem, motivo = next(roteiro, None), "roteiro concluído"
        if mensagem is None:
            fim = motivo
            break
        conversa.append({"papel": "lead", "texto": mensagem})
        try:
            r = canal.enviar(lead_id, mensagem)
        except Exception as exc:  # o agente caiu: isso é uma falha a reportar, não a esconder
            erro = f"{type(exc).__name__}: {exc}"
            conversa.append({"papel": "agente", "texto": ""})
            fim = "erro no agente"
            break
        conversa.append({"papel": "agente", "texto": str(r.get("resposta") or "")})
    else:
        fim = f"limite de {max_turnos} turnos"

    return {
        "persona": persona.id,
        "persona_nome": persona.rotulo,
        "persona_descricao": persona.descricao,
        "lead_id": lead_id,
        "modo_lead": "llm" if usar_llm else "roteiro",
        "conversa": conversa,
        "fim": fim,
        "erro": erro,
    }
