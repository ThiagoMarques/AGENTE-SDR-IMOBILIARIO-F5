"""Como o treinador fala com o agente.

- api: HTTP no /chat, exatamente como o front (grava no PostgreSQL; leads com prefixo TREINO-).
- local: chama o agente no mesmo processo, com memória em RAM e sem agenda/CRM/e-mail reais.
"""
from __future__ import annotations

import copy
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any, Iterator, Protocol

import httpx

PREFIXO_LEAD = "TREINO-"


class Canal(Protocol):
    def enviar(self, lead_id: str, mensagem: str) -> dict[str, Any]: ...


class CanalApi:
    def __init__(self, url: str, timeout: float = 60.0):
        self.url = url.rstrip("/")
        self.cliente = httpx.Client(timeout=timeout)

    def enviar(self, lead_id: str, mensagem: str) -> dict[str, Any]:
        r = self.cliente.post(f"{self.url}/chat", json={"lead_id": lead_id, "mensagem": mensagem})
        r.raise_for_status()
        return r.json()


class CanalLocal:
    def enviar(self, lead_id: str, mensagem: str) -> dict[str, Any]:
        from src.agente.sdr import processar_mensagem

        return processar_mensagem(lead_id, mensagem)


@contextmanager
def ambiente_isolado() -> Iterator[None]:
    """Memória em RAM e integrações desligadas: nada sai da máquina nem vai para o banco."""
    import config
    from src.agenda import calendario
    from src.memoria import conversa

    banco: dict[str, Any] = {}
    persistidas = {"lead_id", "criado_em", "perfil", "controle_sdr", "mensagens",
                   "agendamentos", "imoveis_sugeridos"}

    def carregar(lead_id):
        if lead_id in banco:
            return copy.deepcopy(banco[lead_id])
        return {"lead_id": lead_id, "criado_em": datetime.now(timezone.utc).isoformat(),
                "perfil": {}, "mensagens": [], "agendamentos": [], "imoveis_sugeridos": []}

    def salvar(estado):
        estado = {k: copy.deepcopy(v) for k, v in estado.items() if k in persistidas}
        banco[str(estado["lead_id"])] = estado
        return str(estado["lead_id"])

    desligar = ("GOOGLE_CLIENT_ID", "GOOGLE_CLIENT_SECRET", "GOOGLE_REFRESH_TOKEN",
                "MS_CLIENT_ID", "MS_CLIENT_SECRET", "MS_REFRESH_TOKEN",
                "EMAIL_PROVIDER", "EMAIL_FROM", "RESEND_API_KEY", "SENDGRID_API_KEY", "CRM_WEBHOOK_URL")
    originais_config = {nome: getattr(config, nome) for nome in (*desligar, "AGENDA_TOKENS") if hasattr(config, nome)}
    originais_memoria = (conversa.carregar, conversa.salvar)

    with TemporaryDirectory() as tmp:
        try:
            for nome in desligar:
                if hasattr(config, nome):
                    setattr(config, nome, "")
            config.AGENDA_TOKENS = Path(tmp) / "agenda_tokens.json"
            calendario._ACCESS_TOKENS.clear()
            conversa.carregar, conversa.salvar = carregar, salvar
            yield
        finally:
            for nome, valor in originais_config.items():
                setattr(config, nome, valor)
            conversa.carregar, conversa.salvar = originais_memoria
