"""Falhas detectáveis sem LLM. São as que viram teste de regressão.

Cada função recebe a conversa como lista de {"papel": "lead"|"agente", "texto": str}
e devolve uma lista de falhas {"tipo", "turno", "descricao"}.
"""
from __future__ import annotations

import re
import unicodedata
from typing import Any

from src.imoveis.catalogo_br import CATALOGO_BR

Conversa = list[dict[str, Any]]
Falha = dict[str, Any]

# Frases de sistema que já foram trocadas por linguagem natural e não devem voltar.
JARGOES = (
    "conjunto de filtros",
    "filtro exato",
    "mesma praça",
    "com segurança",
    "contexto imobiliário",
    "para seguir com a busca",
)


def _norm(texto: str) -> str:
    t = unicodedata.normalize("NFKD", (texto or "").lower())
    return "".join(c for c in t if not unicodedata.combining(c))


def _cidades_por_lugar() -> dict[str, str]:
    lugares: dict[str, str] = {}
    for im in CATALOGO_BR:
        for nome in (im.get("bairro"), im.get("regiao")):
            if nome and str(nome).lower() not in {"centro", "zona sul", "zona norte", "zona oeste", "zona leste"}:
                lugares[_norm(str(nome))] = str(im.get("cidade"))
    return lugares


_LUGARES = _cidades_por_lugar()


def _falas_agente(conversa: Conversa) -> list[tuple[int, str]]:
    """(turno, texto) do agente; turno = índice da troca lead→agente, começando em 1."""
    falas, turno = [], 0
    for m in conversa:
        if m.get("papel") == "lead":
            turno += 1
        elif m.get("papel") == "agente":
            falas.append((turno, str(m.get("texto") or "")))
    return falas


def resposta_repetida(conversa: Conversa) -> list[Falha]:
    falhas = []
    falas = _falas_agente(conversa)
    for (_, anterior), (turno, atual) in zip(falas, falas[1:]):
        if atual.strip() and atual.strip() == anterior.strip():
            falhas.append({"tipo": "repetiu_resposta", "turno": turno,
                           "descricao": "O agente mandou exatamente a mesma resposta duas vezes seguidas."})
    return falhas


def pergunta_em_loop(conversa: Conversa) -> list[Falha]:
    """A mesma pergunta final três vezes seguidas: o lead respondeu e o agente não entendeu."""
    falhas, seguidas, ultima = [], 0, None
    for turno, texto in _falas_agente(conversa):
        linhas = [l for l in texto.strip().splitlines() if l.strip()]
        pergunta = linhas[-1].strip() if linhas and linhas[-1].strip().endswith("?") else None
        seguidas = seguidas + 1 if pergunta and pergunta == ultima else 1
        ultima = pergunta
        if pergunta and seguidas == 3:
            falhas.append({"tipo": "pergunta_em_loop", "turno": turno,
                           "descricao": f"Mesma pergunta 3 vezes seguidas: \"{pergunta}\""})
    return falhas


def cidades_misturadas(conversa: Conversa) -> list[Falha]:
    """Numa mesma resposta, lugares de cidades diferentes (ex.: Asa Sul e Pinheiros)."""
    falhas = []
    for turno, texto in _falas_agente(conversa):
        t = _norm(texto)
        cidades = {cidade for lugar, cidade in _LUGARES.items() if re.search(rf"\b{re.escape(lugar)}\b", t)}
        cidades |= {c for c in ("São Paulo", "Brasília") if f"{c}/" in texto}
        if len(cidades) > 1:
            falhas.append({"tipo": "cidades_misturadas", "turno": turno,
                           "descricao": f"A resposta mistura cidades: {', '.join(sorted(cidades))}."})
    return falhas


def texto_quebrado(conversa: Conversa) -> list[Falha]:
    padroes = {
        r"(?<!\.)\.\.(?!\.)": "ponto duplo",
        r"\b1 quartos\b": "plural errado ('1 quartos')",
        r"\bNone\b|\{|\}": "valor técnico vazando no texto",
        r"(?<!\ba\.a)\. [a-zà-ú]": "frase começando com minúscula",
        r"R\$ 0\b": "valor zerado",
    }
    falhas = []
    for turno, texto in _falas_agente(conversa):
        for padrao, nome in padroes.items():
            if re.search(padrao, texto):
                falhas.append({"tipo": "texto_quebrado", "turno": turno, "descricao": f"Texto com {nome}."})
    return falhas


def jargao(conversa: Conversa) -> list[Falha]:
    falhas = []
    for turno, texto in _falas_agente(conversa):
        t = _norm(texto)
        for frase in JARGOES:
            if _norm(frase) in t:
                falhas.append({"tipo": "jargao", "turno": turno,
                               "descricao": f"Frase de sistema na resposta: \"{frase}\"."})
    return falhas


def resposta_vazia(conversa: Conversa) -> list[Falha]:
    return [
        {"tipo": "resposta_vazia", "turno": turno, "descricao": "O agente não respondeu nada."}
        for turno, texto in _falas_agente(conversa)
        if not texto.strip()
    ]


VERIFICACOES = (resposta_repetida, pergunta_em_loop, cidades_misturadas, texto_quebrado, jargao, resposta_vazia)


def verificar_conversa(conversa: Conversa) -> list[Falha]:
    falhas: list[Falha] = []
    for verificacao in VERIFICACOES:
        falhas.extend(verificacao(conversa))
    return sorted(falhas, key=lambda f: f["turno"])


def formatar_falhas(falhas: list[Falha]) -> str:
    return "\n".join(f"- turno {f['turno']} [{f['tipo']}] {f['descricao']}" for f in falhas)
