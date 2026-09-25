"""Memória conversacional persistida em JSON (POC)."""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import config


def _path(lead_id: str) -> Path:
    config.CONVERSAS_DIR.mkdir(parents=True, exist_ok=True)
    safe = "".join(c if c.isalnum() or c in "-_" else "_" for c in lead_id)
    return config.CONVERSAS_DIR / f"{safe}.json"


def carregar(lead_id: str) -> dict[str, Any]:
    path = _path(lead_id)
    if not path.exists():
        return {
            "lead_id": lead_id,
            "criado_em": datetime.now(timezone.utc).isoformat(),
            "perfil": {},
            "mensagens": [],
            "agendamentos": [],
            "imoveis_sugeridos": [],
        }
    with path.open(encoding="utf-8") as f:
        return json.load(f)


def salvar(estado: dict[str, Any]) -> Path:
    path = _path(str(estado["lead_id"]))
    estado["atualizado_em"] = datetime.now(timezone.utc).isoformat()
    with path.open("w", encoding="utf-8") as f:
        json.dump(estado, f, ensure_ascii=False, indent=2)
    return path


def adicionar_mensagem(estado: dict[str, Any], papel: str, texto: str) -> dict[str, Any]:
    estado.setdefault("mensagens", []).append(
        {
            "papel": papel,
            "texto": texto,
            "em": datetime.now(timezone.utc).isoformat(),
        }
    )
    return estado
