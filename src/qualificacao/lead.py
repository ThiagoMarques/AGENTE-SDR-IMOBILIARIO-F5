"""Qualificação de leads: score ponderado e explicável (inspirado em BANT).

Por que ponderado e não "% de campos preenchidos"?
- Um SDR real prioriza pelo que indica chance de fechamento: intenção clara,
  orçamento, prazo e engajamento. Preencher "quartos" não pesa o mesmo que
  informar orçamento ou urgência.
- Cada critério gera uma justificativa legível, para o corretor entender
  POR QUE o lead é quente/morno/frio (IA explicável / human-in-the-loop).

Critérios (pontos máximos):
- necessidade  (20): intenção identificada (compra, aluguel, investimento)
- detalhamento (25): campos específicos do perfil (região/quartos ou retorno/perfil)
- orcamento    (20): faixa de preço ou ticket informado
- prazo        (20): urgência (alta 20, média 12, baixa 4, desconhecida 0)
- engajamento  (15): nº de mensagens do lead (1 -> 5, 2 -> 10, 3+ -> 15)

Se o nº de mensagens não for informado, o engajamento sai da conta e o score
é reescalado para 0–100 sobre os critérios disponíveis.
"""
from __future__ import annotations

from typing import Any

import config
from src.coleta.perfil import (  # funil e perguntas humanizadas (módulo de coleta)
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
    "score_estado",
    "avaliar_criterios",
    "encaminhamento",
    "formatar_valor",
]

PESOS = {
    "necessidade": 20,
    "detalhamento": 25,
    "orcamento": 20,
    "prazo": 20,
    "engajamento": 15,
}

URGENCIA_PONTOS = {
    "alta": 20, "urgente": 20, "imediata": 20, "agora": 20,
    "media": 12, "média": 12, "medio prazo": 12, "médio prazo": 12,
    "baixa": 4, "sem pressa": 4,
}

NOMES_CAMPOS = {
    "regiao": "região", "quartos": "quartos",
    "retorno_esperado": "retorno esperado", "perfil": "perfil de investidor",
}

def _intencao(perfil: dict[str, Any]) -> str:
    i = (perfil.get("intencao") or "").lower()
    if i in {"investimento", "investir"}:
        return "investimento"
    if i in {"aluguel", "alugar"}:
        return "aluguel"
    if i in {"compra", "comprar"}:
        return "compra"
    return ""


def _campos_detalhe(perfil: dict[str, Any]) -> tuple[str, ...]:
    if _intencao(perfil) == "investimento":
        return ("retorno_esperado", "perfil")
    return ("regiao", "quartos")


def _nivel_engajamento(mensagens_lead: int) -> int:
    if mensagens_lead >= 3:
        return 15
    if mensagens_lead == 2:
        return 10
    if mensagens_lead == 1:
        return 5
    return 0


def avaliar_criterios(perfil: dict[str, Any], mensagens_lead: int | None = None) -> list[dict[str, Any]]:
    """Retorna a pontuação de cada critério com justificativa."""
    intencao = _intencao(perfil)
    criterios: list[dict[str, Any]] = []

    criterios.append({
        "criterio": "necessidade",
        "pontos": PESOS["necessidade"] if intencao else 0,
        "maximo": PESOS["necessidade"],
        "motivo": f"Intenção identificada: {intencao}." if intencao else "Intenção ainda não identificada.",
    })

    detalhes = _campos_detalhe(perfil)
    preenchidos = [c for c in detalhes if perfil.get(c)]
    pts = round(PESOS["detalhamento"] * len(preenchidos) / len(detalhes))
    criterios.append({
        "criterio": "detalhamento",
        "pontos": pts,
        "maximo": PESOS["detalhamento"],
        "motivo": (
            f"Informou {', '.join(NOMES_CAMPOS[c] for c in preenchidos)}." if preenchidos
            else "Sem detalhes do imóvel/objetivo."
        ) + (
            f" Falta: {', '.join(NOMES_CAMPOS[c] for c in detalhes if c not in preenchidos)}."
            if len(preenchidos) < len(detalhes) else ""
        ),
    })

    campo_orc = "ticket" if intencao == "investimento" else "faixa_preco"
    valor = perfil.get(campo_orc) or perfil.get("faixa_preco") or perfil.get("ticket")
    criterios.append({
        "criterio": "orcamento",
        "pontos": PESOS["orcamento"] if valor else 0,
        "maximo": PESOS["orcamento"],
        "motivo": f"Orçamento informado: {formatar_valor(valor)}." if valor else "Orçamento não informado.",
    })

    urg = str(perfil.get("urgencia") or "").lower()
    pts_urg = URGENCIA_PONTOS.get(urg, 0)
    # O funil do investidor (enunciado: perfil, ticket, retorno) não pergunta
    # prazo; sem essa informação o critério sai da conta em vez de zerar.
    if not (intencao == "investimento" and not urg):
        criterios.append({
            "criterio": "prazo",
            "pontos": pts_urg,
            "maximo": PESOS["prazo"],
            "motivo": f"Urgência {urg}." if urg else "Prazo não informado.",
        })

    if mensagens_lead is not None:
        criterios.append({
            "criterio": "engajamento",
            "pontos": _nivel_engajamento(mensagens_lead),
            "maximo": PESOS["engajamento"],
            "motivo": f"{mensagens_lead} mensagem(ns) enviada(s) pelo lead.",
        })
    return criterios


def formatar_valor(valor: Any) -> str:
    try:
        return f"{float(valor):,.0f}".replace(",", ".")
    except (TypeError, ValueError):
        return str(valor)


def encaminhamento(perfil: dict[str, Any]) -> str:
    """Quem deve assumir o lead (enunciado: investidor vai para especialista)."""
    return "especialista em investimentos" if _intencao(perfil) == "investimento" else "corretor"


def score_lead(perfil: dict[str, Any], mensagens_lead: int | None = None) -> dict[str, Any]:
    """Score 0–100 ponderado, prioridade quente/morno/frio e justificativas.

    Mantém as chaves originais (score, prioridade, campos_faltantes,
    pronto_para_agendar) para não quebrar agente e dashboard.
    """
    criterios = avaliar_criterios(perfil, mensagens_lead)
    obtido = sum(c["pontos"] for c in criterios)
    maximo = sum(c["maximo"] for c in criterios)
    score = round(100 * obtido / maximo) if maximo else 0

    if score >= config.SCORE_QUENTE:
        prioridade = "quente"
    elif score >= config.SCORE_MORNO:
        prioridade = "morno"
    else:
        prioridade = "frio"

    faltantes = campos_faltantes(perfil)
    return {
        "score": score,
        "prioridade": prioridade,
        "campos_faltantes": faltantes,
        "pronto_para_agendar": not faltantes and score >= config.SCORE_MORNO,
        "encaminhamento": encaminhamento(perfil),
        "criterios": criterios,
        "justificativa": " ".join(c["motivo"] for c in criterios),
    }


def score_estado(estado: dict[str, Any]) -> dict[str, Any]:
    """Atalho: score a partir do estado da conversa (usa engajamento)."""
    msgs = estado.get("mensagens") or []
    n_lead = sum(1 for m in msgs if m.get("papel") == "lead")
    return score_lead(estado.get("perfil") or {}, mensagens_lead=n_lead)
