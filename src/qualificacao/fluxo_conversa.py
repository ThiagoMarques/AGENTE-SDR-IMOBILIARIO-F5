"""Motor determinístico do fluxo de qualificação.

O fluxo NÃO depende da ordem da conversa.
A cada mensagem o perfil é atualizado e o próximo campo faltante é recalculado.
"""

from __future__ import annotations

from typing import Any


FLUXOS: dict[str, tuple[str, ...]] = {
    "compra": (
        "regiao",
        "faixa_preco",
        "quartos",
        "urgencia",
    ),
    "aluguel": (
        "regiao",
        "faixa_preco",
        "quartos",
        "urgencia",
    ),
    "investimento": (
        "ticket",
        "perfil",
        "retorno_esperado",
    ),
}


PERGUNTAS: dict[str, str] = {
    "intencao": "Você está buscando comprar, alugar ou investir?",
    "regiao": "Qual bairro ou região você prefere?",
    "faixa_preco": "Qual faixa de valor você tem em mente?",
    "quartos": "Quantos quartos você procura?",
    "urgencia": "Você está com prazo mais curto, médio ou sem pressa por enquanto?",
    "ticket": "Qual valor você pretende investir?",
    "perfil": "Seu foco é renda recorrente, valorização ou outro objetivo?",
    "retorno_esperado": "Qual expectativa de retorno você tem para esse investimento?",
}


def campo_preenchido(perfil: dict[str, Any], campo: str) -> bool:
    """Considera valor explícito OU preferência flexível como campo respondido."""
    valor = perfil.get(campo)

    if valor not in (None, ""):
        return True

    return bool(perfil.get(f"{campo}_flexivel"))


def campos_faltantes_conversa(perfil: dict[str, Any]) -> list[str]:
    intencao = perfil.get("intencao")

    if not intencao:
        return ["intencao"]

    fluxo = FLUXOS.get(str(intencao))

    # Se chegar uma intenção inesperada, volta para intenção em vez de quebrar.
    if not fluxo:
        return ["intencao"]

    return [
        campo
        for campo in fluxo
        if not campo_preenchido(perfil, campo)
    ]


def proximo_campo(perfil: dict[str, Any]) -> str | None:
    faltantes = campos_faltantes_conversa(perfil)
    return faltantes[0] if faltantes else None


def pergunta_para(campo: str | None) -> str | None:
    if not campo:
        return None

    return PERGUNTAS.get(campo)


def qualificacao_concluida(perfil: dict[str, Any]) -> bool:
    return proximo_campo(perfil) is None
