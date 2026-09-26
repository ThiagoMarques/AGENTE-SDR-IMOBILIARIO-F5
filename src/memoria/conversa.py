"""Memória conversacional persistida no PostgreSQL."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from src.db import repos
from src.db.session import init_db, session_scope


def _ensure_db() -> None:
    init_db()


def carregar(lead_id: str) -> dict[str, Any]:
    _ensure_db()
    session = session_scope()
    try:
        return repos.carregar(session, lead_id)
    finally:
        session.close()


def salvar(estado: dict[str, Any]) -> str:
    """Persiste o estado e devolve o lead_id (antes devolvia Path)."""
    _ensure_db()
    session = session_scope()
    try:
        lead_id = repos.salvar(session, estado)
        session.commit()
        return lead_id
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def adicionar_mensagem(estado: dict[str, Any], papel: str, texto: str) -> dict[str, Any]:
    estado.setdefault("mensagens", []).append(
        {
            "papel": papel,
            "texto": texto,
            "em": datetime.now(timezone.utc).isoformat(),
        }
    )
    return estado


def listar_todos() -> list[dict[str, Any]]:
    _ensure_db()
    session = session_scope()
    try:
        return repos.listar_leads(session)
    finally:
        session.close()
