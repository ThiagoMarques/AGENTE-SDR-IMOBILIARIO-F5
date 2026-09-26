"""Coleta de perfil do lead (intenção + campos relevantes)."""
from __future__ import annotations

from typing import Any


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


def perfil_completo(perfil: dict[str, Any]) -> bool:
    """True quando intenção existe e os campos do funil estão preenchidos."""
    return bool(perfil.get("intencao")) and not campos_faltantes(perfil)


def proxima_pergunta(perfil: dict[str, Any]) -> str | None:
    """Uma pergunta por vez, com tom de conversa (não formulário)."""
    faltantes = campos_faltantes(perfil)
    if not faltantes:
        return None

    campo = faltantes[0]
    intencao = (perfil.get("intencao") or "").lower()

    if campo == "intencao":
        return "Me conta: você está buscando comprar, alugar ou investir?"

    if campo == "regiao":
        if intencao == "aluguel":
            return "Qual bairro ou região faz mais sentido para você morar?"
        if intencao == "investimento":
            return "Tem alguma região preferida para o investimento?"
        return "Em qual região ou bairro você gostaria de focar?"

    if campo == "quartos":
        if intencao == "aluguel":
            return "Quantos quartos você precisa no imóvel?"
        return "Quantos quartos você imagina para esse imóvel?"

    if campo == "faixa_preco":
        if intencao == "aluguel":
            return "Qual valor mensal de aluguel cabe confortavelmente no seu orçamento?"
        return "Qual faixa de preço você tem em mente? Pode ser um valor aproximado."

    if campo == "urgencia":
        return "Você está com prazo mais curto, médio, ou sem pressa por enquanto?"

    if campo == "ticket":
        return "Qual ticket aproximado você pensa investir? (pode ser em milhares ou um teto)"

    if campo == "retorno_esperado":
        return "Que retorno anual você espera? Por exemplo, por volta de 6% a.a."

    if campo == "perfil":
        return "Você prefere renda recorrente com locação, ou valorização no médio prazo?"

    return "Pode me contar um pouco mais sobre o que você procura?"
