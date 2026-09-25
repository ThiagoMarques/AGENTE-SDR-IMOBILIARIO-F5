"""Agendamento simples de reuniões/visitas (POC)."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any


def sugerir_horarios(qtd: int = 3) -> list[str]:
    """Gera janelas didáticas a partir de amanhã (10h, 14h, 16h)."""
    base = datetime.now(timezone.utc).astimezone() + timedelta(days=1)
    base = base.replace(minute=0, second=0, microsecond=0)
    slots = []
    for dia in range(0, 3):
        for hora in (10, 14, 16):
            dt = (base + timedelta(days=dia)).replace(hour=hora)
            slots.append(dt.strftime("%d/%m/%Y %H:%M"))
            if len(slots) >= qtd:
                return slots
    return slots


def registrar_agendamento(
    estado: dict[str, Any],
    *,
    horario: str,
    tipo: str = "reuniao",
    imovel_id: str | None = None,
) -> dict[str, Any]:
    item = {
        "tipo": tipo,
        "horario": horario,
        "imovel_id": imovel_id,
        "status": "agendado",
    }
    estado.setdefault("agendamentos", []).append(item)
    return estado
