"""Integração com CRM via webhook (diferencial do enunciado).

Desenho:
- Padrão adapter: o agente fala com `CRMAdapter`, não com um CRM específico.
  `WebhookCRM` envia JSON por HTTP POST para qualquer URL (CRM simulado,
  n8n/Zapier, ou um CRM real que aceite webhook). Um `HubSpotCRM`, por
  exemplo, seria outra classe com o mesmo método `enviar`.
- Envio por EVENTO, não por mensagem: só sincroniza quando algo relevante
  muda (prioridade, lead pronto para agendar, resumo gerado). Evita tráfego
  e chamadas desnecessárias.
- Resiliência: falha de rede nunca derruba o atendimento. O payload vai
  para uma fila local (`dados/crm_pendentes.jsonl`) e pode ser reenviado
  depois (`python main.py --crm-reenviar`).
- Idempotência: cada envio leva `lead_id` + `evento`; o CRM faz upsert
  pelo `lead_id`, então reenvios não duplicam o lead.
"""
from __future__ import annotations

import json
import urllib.error
import urllib.request
from datetime import datetime, timezone
from typing import Any, Protocol

import config

EVENTO_ATUALIZADO = "lead_atualizado"
EVENTO_QUALIFICADO = "lead_qualificado"
EVENTO_RESUMO = "resumo_gerado"


class CRMAdapter(Protocol):
    def enviar(self, payload: dict[str, Any]) -> dict[str, Any]: ...


class WebhookCRM:
    def __init__(self, url: str, token: str = "", timeout: float = 3.0) -> None:
        self.url = url
        self.token = token
        self.timeout = timeout

    def enviar(self, payload: dict[str, Any]) -> dict[str, Any]:
        corpo = json.dumps(payload, ensure_ascii=False, default=str).encode("utf-8")
        headers = {"Content-Type": "application/json", "User-Agent": "AGENTE-SDR-F5/1.0"}
        if self.token:
            headers["Authorization"] = f"Bearer {self.token}"
        req = urllib.request.Request(self.url, data=corpo, headers=headers, method="POST")
        with urllib.request.urlopen(req, timeout=self.timeout) as resp:
            texto = resp.read().decode("utf-8") or "{}"
            try:
                return {"http": resp.status, "resposta": json.loads(texto)}
            except json.JSONDecodeError:
                return {"http": resp.status, "resposta": texto}


def adapter_padrao() -> CRMAdapter | None:
    if not config.CRM_WEBHOOK_URL:
        return None
    return WebhookCRM(config.CRM_WEBHOOK_URL, config.CRM_WEBHOOK_TOKEN, config.CRM_TIMEOUT)


def montar_payload(evento: str, resumo: dict[str, Any]) -> dict[str, Any]:
    q = resumo.get("qualificacao") or {}
    return {
        "evento": evento,
        "enviado_em": datetime.now(timezone.utc).isoformat(),
        "lead_id": resumo.get("lead_id"),
        "prioridade": q.get("prioridade"),
        "score": q.get("score"),
        "encaminhamento": resumo.get("encaminhamento"),
        "acao_sugerida": resumo.get("acao_sugerida"),
        "resumo": resumo,
    }


def _enfileirar(payload: dict[str, Any], erro: str) -> None:
    config.CRM_PENDENTES.parent.mkdir(parents=True, exist_ok=True)
    with config.CRM_PENDENTES.open("a", encoding="utf-8") as f:
        f.write(json.dumps({"erro": erro, "payload": payload}, ensure_ascii=False, default=str) + "\n")


def enviar_evento(
    evento: str, resumo: dict[str, Any], adapter: CRMAdapter | None = None
) -> dict[str, Any]:
    """Envia ao CRM. Nunca levanta exceção: devolve o status do envio."""
    adapter = adapter or adapter_padrao()
    if adapter is None:
        return {"status": "desabilitado"}
    payload = montar_payload(evento, resumo)
    try:
        r = adapter.enviar(payload)
        return {"status": "enviado", "evento": evento, **r}
    except (urllib.error.URLError, OSError, ValueError) as exc:
        _enfileirar(payload, str(exc))
        return {"status": "pendente", "evento": evento, "erro": str(exc)}


def evento_necessario(estado: dict[str, Any], qual: dict[str, Any]) -> str | None:
    """Decide se vale sincronizar agora, comparando com o último envio."""
    ultimo = estado.get("crm") or {}
    if qual.get("pronto_para_agendar") and not ultimo.get("pronto_para_agendar"):
        return EVENTO_QUALIFICADO
    if (estado.get("perfil") or {}).get("intencao") and qual.get("prioridade") != ultimo.get("prioridade"):
        return EVENTO_ATUALIZADO
    return None


def sincronizar(
    estado: dict[str, Any], resumo: dict[str, Any], evento: str | None = None,
    adapter: CRMAdapter | None = None,
) -> dict[str, Any] | None:
    """Envia se houver evento relevante e registra o status em estado['crm']."""
    qual = resumo.get("qualificacao") or {}
    evento = evento or evento_necessario(estado, qual)
    if not evento:
        return None
    r = enviar_evento(evento, resumo, adapter)
    if r["status"] == "desabilitado":
        return r
    estado["crm"] = {
        "ultimo_evento": evento,
        "status": r["status"],
        "prioridade": qual.get("prioridade"),
        "pronto_para_agendar": bool(qual.get("pronto_para_agendar")),
        "em": datetime.now(timezone.utc).isoformat(),
    }
    return r


def reenviar_pendentes(adapter: CRMAdapter | None = None) -> dict[str, int]:
    adapter = adapter or adapter_padrao()
    if adapter is None or not config.CRM_PENDENTES.exists():
        return {"enviados": 0, "pendentes": 0}
    linhas = [json.loads(l) for l in config.CRM_PENDENTES.read_text(encoding="utf-8").splitlines() if l.strip()]
    restantes, enviados = [], 0
    for item in linhas:
        try:
            adapter.enviar(item["payload"])
            enviados += 1
        except (urllib.error.URLError, OSError, ValueError) as exc:
            item["erro"] = str(exc)
            restantes.append(item)
    config.CRM_PENDENTES.write_text(
        "".join(json.dumps(i, ensure_ascii=False, default=str) + "\n" for i in restantes), encoding="utf-8"
    )
    return {"enviados": enviados, "pendentes": len(restantes)}
