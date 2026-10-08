"""Contextos escritos pelo usuário ("um senhor de idade que fala pausadamente…") viram personas.

Ficam em treinador/contextos.json (fora do Git). Sem roteiro: só rodam com o LLM interpretando o lead.
"""
from __future__ import annotations

import json
import os
import re
import unicodedata
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any

from treinador.personas import Persona

ARQUIVO = Path(__file__).resolve().parent / "contextos.json"
PREFIXO = "ctx_"

_OBJETIVO = (
    "Siga o contexto acima. Se ele não disser o que a pessoa procura, escolha uma busca de imóvel plausível "
    "no Brasil (comprar, alugar ou investir, com região e valor) e mantenha essa busca coerente até o fim."
)


def _slug(texto: str) -> str:
    sem_acento = unicodedata.normalize("NFKD", texto).encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z0-9]+", "_", sem_acento.lower()).strip("_")[:30] or "contexto"


_PEDIDO = re.compile(
    r"^(?:simul[ea]r?|crie|criar|fa[cç]a|testar?)\s+"
    r"(?:(?:uma?s?)\s+)?(?:(?:conversas?|atendimentos?|di[aá]logos?)\s+)?"
    r"(?:(?:de|com|entre|para|pra)\s+)?(?:(?:uns|umas|um|uma|o|a|os|as)\s+)?",
    re.I,
)
_CONECTIVOS = {"que", "com", "de", "do", "da", "e", "em", "no", "na", "para", "pra", "sem", "um", "uma", "o", "a"}


def _nome_padrao(contexto: str) -> str:
    palavras = _PEDIDO.sub("", contexto.strip()).split()[:5]
    while palavras and palavras[-1].lower().strip(",.;") in _CONECTIVOS:
        palavras.pop()
    nome = " ".join(palavras).rstrip(",.;")
    return (nome[:1].upper() + nome[1:]) if nome else "Contexto"


def listar(arquivo: Path | None = None) -> list[dict[str, Any]]:
    caminho = arquivo or ARQUIVO
    try:
        return json.loads(caminho.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError):
        return []


def _gravar(contextos: list[dict[str, Any]], arquivo: Path | None = None) -> None:
    caminho = arquivo or ARQUIVO
    tmp = caminho.with_suffix(".tmp")
    tmp.write_text(json.dumps(contextos, ensure_ascii=False, indent=2), encoding="utf-8")
    os.replace(tmp, caminho)


def criar(contexto: str, nome: str = "", arquivo: Path | None = None) -> dict[str, Any]:
    contexto = contexto.strip()
    nome = nome.strip() or _nome_padrao(contexto)
    novo = {
        "id": f"{PREFIXO}{_slug(nome)}_{uuid.uuid4().hex[:4]}",
        "nome": nome,
        "contexto": contexto,
        "criado_em": datetime.now().isoformat(timespec="seconds"),
    }
    _gravar([*listar(arquivo), novo], arquivo)
    return novo


def remover(contexto_id: str, arquivo: Path | None = None) -> bool:
    atuais = listar(arquivo)
    restantes = [c for c in atuais if c["id"] != contexto_id]
    if len(restantes) == len(atuais):
        return False
    _gravar(restantes, arquivo)
    return True


def como_persona(ctx: dict[str, Any]) -> Persona:
    return Persona(id=ctx["id"], nome=ctx["nome"], descricao=ctx["contexto"], objetivo=_OBJETIVO)
