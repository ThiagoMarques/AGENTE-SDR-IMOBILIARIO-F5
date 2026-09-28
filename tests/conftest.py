import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import config  # noqa: E402


@pytest.fixture(autouse=True)
def sem_llm(monkeypatch):
    """Testes rodam no modo determinístico (sem custo nem rede)."""
    monkeypatch.setattr(config, "OPENAI_API_KEY", "")


@pytest.fixture(autouse=True)
def memoria_em_ram(monkeypatch):
    """Substitui o Postgres por um dicionário: testes rodam sem banco."""
    import copy
    from datetime import datetime, timezone

    from src.memoria import conversa

    banco: dict = {}

    def carregar(lead_id):
        if lead_id in banco:
            return copy.deepcopy(banco[lead_id])
        return {"lead_id": lead_id, "criado_em": datetime.now(timezone.utc).isoformat(),
                "perfil": {}, "mensagens": [], "agendamentos": [], "imoveis_sugeridos": []}

    def salvar(estado):
        estado = copy.deepcopy(estado)
        estado.pop("crm", None)  # o banco real não persiste estado['crm']
        banco[str(estado["lead_id"])] = estado
        return str(estado["lead_id"])

    monkeypatch.setattr(conversa, "carregar", carregar)
    monkeypatch.setattr(conversa, "salvar", salvar)
    monkeypatch.setattr(conversa, "listar_todos", lambda: [copy.deepcopy(v) for v in banco.values()])
    return banco
