"""Avaliação de uma conversa: verificações determinísticas + LLM juiz com rubrica fixa."""
from __future__ import annotations

from typing import Any

from treinador import llm
from treinador.personas import Persona
from treinador.verificacoes import verificar_conversa

CRITERIOS = {
    "compreensao": "Entendeu o que o lead disse (inclusive com erro de digitação, resposta curta ou mudança de ideia)?",
    "naturalidade": "Soa como um bom atendente humano, sem frases de sistema, sem repetir texto?",
    "progresso": "Conduziu a conversa para o objetivo do lead (opções e/ou visita) sem perguntas desnecessárias?",
    "veracidade": "Evitou inventar dados de imóvel, preços ou condições que não estavam na conversa?",
    "duvidas": "Respondeu às perguntas do lead de forma útil antes de retomar a busca? (5 se não houve perguntas)",
}

TIPOS_FALHA = (
    "nao_entendeu", "repetiu", "pergunta_desnecessaria", "tom_robotico", "inventou_dado",
    "sugestao_incoerente", "nao_respondeu_duvida", "perdeu_contexto", "outro",
)

NOTA_MINIMA = 3.5

_SISTEMA = (
    "Você é um avaliador exigente de atendimento imobiliário por chat. Avalie SOMENTE as falas do ASSISTENTE. "
    "Dê nota de 1 a 5 em cada critério:\n"
    + "\n".join(f"- {k}: {v}" for k, v in CRITERIOS.items())
    + "\nContexto do produto (não é falha): o assistente precisa coletar intenção, região, valor, quartos e "
    "prazo (investidor: valor, foco e retorno esperado) antes de buscar, então perguntar esses itens uma vez é "
    "esperado; perguntar de novo algo já respondido é falha. Só marque pergunta_desnecessaria se você conseguir "
    "apontar a fala ANTERIOR do lead que já trazia aquela informação; se não houver, não é falha. Preços e imóveis citados vêm do catálogo real da "
    "imobiliária: só considere inventado se contradizer a própria conversa. Assuntos fora do ramo imobiliário "
    "não precisam ser respondidos, só reconhecidos com educação."
    + "\nListe as falhas concretas (no máximo 5), cada uma com o turno (número da mensagem do lead que a "
    "provocou, começando em 1), o tipo, uma descrição curta e uma sugestão de como o assistente deveria ter "
    f"respondido. Tipos permitidos: {', '.join(TIPOS_FALHA)}. Não invente falhas: se foi bom, liste nenhuma. "
    'Responda SOMENTE JSON: {"notas": {"compreensao": 1-5, ...}, '
    '"falhas": [{"turno": 1, "tipo": "...", "descricao": "...", "sugestao": "..."}], "resumo": "uma frase"}'
)


def _transcricao(conversa: list[dict[str, Any]]) -> str:
    linhas, turno = [], 0
    for m in conversa:
        if m["papel"] == "lead":
            turno += 1
            linhas.append(f"[{turno}] LEAD: {m['texto']}")
        else:
            linhas.append(f"[{turno}] ASSISTENTE: {m['texto']}")
    return "\n".join(linhas)


def _avaliar_com_llm(persona: Persona, conversa: list[dict[str, Any]]) -> dict[str, Any]:
    usuario = (
        f"Perfil do lead (o assistente não conhecia): {persona.descricao}\nObjetivo do lead: {persona.objetivo}\n\n"
        f"Conversa:\n{_transcricao(conversa)}"
    )
    bruto = llm.json_do_llm(_SISTEMA, usuario, temperatura=0)
    notas = {k: float(v) for k, v in (bruto.get("notas") or {}).items() if k in CRITERIOS and isinstance(v, (int, float))}
    falhas = [
        {
            "turno": int(f.get("turno") or 0),
            "tipo": f.get("tipo") if f.get("tipo") in TIPOS_FALHA else "outro",
            "descricao": str(f.get("descricao") or ""),
            "sugestao": str(f.get("sugestao") or ""),
        }
        for f in (bruto.get("falhas") or [])
        if isinstance(f, dict)
    ]
    return {"notas": notas, "falhas": falhas, "resumo": str(bruto.get("resumo") or "")}


def avaliar(persona: Persona, resultado: dict[str, Any], *, usar_llm: bool) -> dict[str, Any]:
    conversa = resultado["conversa"]
    deterministicas = verificar_conversa(conversa)
    if resultado.get("erro"):
        deterministicas.append({"tipo": "erro_no_agente", "turno": len(conversa) // 2,
                                "descricao": resultado["erro"]})

    juiz: dict[str, Any] = {"notas": {}, "falhas": [], "resumo": ""}
    if usar_llm and conversa:
        try:
            juiz = _avaliar_com_llm(persona, conversa)
        except Exception as exc:
            juiz["resumo"] = f"avaliação por LLM falhou: {type(exc).__name__}: {exc}"

    notas = juiz["notas"]
    media = round(sum(notas.values()) / len(notas), 2) if notas else None
    aprovada = not deterministicas and (media is None or media >= NOTA_MINIMA)
    return {
        "deterministicas": deterministicas,
        "juiz": juiz,
        "media": media,
        "aprovada": aprovada,
    }
