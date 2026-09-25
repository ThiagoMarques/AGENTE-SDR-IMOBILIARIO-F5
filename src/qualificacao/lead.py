"""Qualificação de leads (regras didáticas + score)."""
from __future__ import annotations

from typing import Any

import config


CAMPOS_COMPRA = ("intencao", "regiao", "quartos", "faixa_preco", "urgencia")
CAMPOS_INVESTIMENTO = ("intencao", "ticket", "retorno_esperado", "perfil")
CAMPOS_ALUGUEL = ("intencao", "regiao", "quartos", "faixa_preco", "urgencia")


def campos_faltantes(perfil: dict[str, Any]) -> list[str]:
    intencao = (perfil.get("intencao") or "").lower()
    if intencao in {"investimento", "investir"}:
        base = CAMPOS_INVESTIMENTO
    elif intencao in {"aluguel", "alugar"}:
        base = CAMPOS_ALUGUEL
    else:
        base = CAMPOS_COMPRA
    return [c for c in base if not perfil.get(c)]


def score_lead(perfil: dict[str, Any]) -> dict[str, Any]:
    """Score 0–100 com prioridade quente/morno/frio."""
    faltantes = campos_faltantes(perfil)
    preenchidos = 0
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


def proxima_pergunta(perfil: dict[str, Any]) -> str | None:
    faltantes = campos_faltantes(perfil)
    if not faltantes:
        return None
    perguntas = {
        "intencao": "Você busca comprar, alugar ou investir?",
        "regiao": "Qual região ou bairro tem mais interesse?",
        "quartos": "Quantos quartos você precisa?",
        "faixa_preco": "Qual faixa de preço cabe no seu orçamento?",
        "urgencia": "Até quando você gostaria de concluir (curto, médio ou sem pressa)?",
        "ticket": "Qual ticket aproximado você pensa investir?",
        "retorno_esperado": "Que retorno anual você espera (por exemplo, 6% a.a.)?",
        "perfil": "Prefere renda recorrente (locação) ou valorização no médio prazo?",
    }
    return perguntas.get(faltantes[0], "Pode me contar um pouco mais sobre o que procura?")
