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
def agenda_sem_credenciais(monkeypatch, tmp_path):
    """Nenhum teste fala com Google/Microsoft de verdade nem lê tokens da máquina."""
    from src.agenda import calendario

    monkeypatch.setattr(config, "AGENDA_TOKENS", tmp_path / "agenda_tokens.json")
    for nome in ("GOOGLE_CLIENT_ID", "GOOGLE_CLIENT_SECRET", "GOOGLE_REFRESH_TOKEN",
                 "MS_CLIENT_ID", "MS_CLIENT_SECRET", "MS_REFRESH_TOKEN",
                 "EMAIL_PROVIDER", "EMAIL_FROM", "RESEND_API_KEY", "SENDGRID_API_KEY"):
        monkeypatch.setattr(config, nome, "")
    monkeypatch.setattr(config, "CRM_WEBHOOK_URL", "")
    calendario._ACCESS_TOKENS.clear()


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

    # Mesmas chaves que src/db/repos.py grava: o que ficar fora daqui some entre mensagens.
    persistidas = {"lead_id", "criado_em", "perfil", "controle_sdr", "mensagens",
                   "agendamentos", "imoveis_sugeridos"}

    def salvar(estado):
        estado = {k: copy.deepcopy(v) for k, v in estado.items() if k in persistidas}
        banco[str(estado["lead_id"])] = estado
        return str(estado["lead_id"])

    monkeypatch.setattr(conversa, "carregar", carregar)
    monkeypatch.setattr(conversa, "salvar", salvar)
    monkeypatch.setattr(conversa, "listar_todos", lambda: [copy.deepcopy(v) for v in banco.values()])
    return banco
