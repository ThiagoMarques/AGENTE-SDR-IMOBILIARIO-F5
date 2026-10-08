"""Chamada JSON ao LLM do treinador (mesma chave do projeto; modelo próprio via TREINADOR_MODEL)."""
from __future__ import annotations

import json
import os
from typing import Any

import config


def disponivel() -> bool:
    return bool(config.OPENAI_API_KEY)


def modelo() -> str:
    return (os.getenv("TREINADOR_MODEL") or config.LLM_MODEL).strip()


def json_do_llm(sistema: str, usuario: str, *, temperatura: float) -> dict[str, Any]:
    from openai import OpenAI

    cliente = OpenAI(api_key=config.OPENAI_API_KEY)
    resp = cliente.chat.completions.create(
        model=modelo(),
        messages=[{"role": "system", "content": sistema}, {"role": "user", "content": usuario}],
        response_format={"type": "json_object"},
        temperature=temperatura,
    )
    return json.loads(resp.choices[0].message.content or "{}")
