"""API FastAPI — chat, leads, dashboard e webhooks."""
from __future__ import annotations

from contextlib import asynccontextmanager
from typing import Any

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

import config
from src.db.session import init_db


@asynccontextmanager
async def lifespan(_app: FastAPI):
    init_db()
    yield


app = FastAPI(
    title="Agente SDR Imobiliário",
    version="0.1.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=config.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


class ChatIn(BaseModel):
    lead_id: str = Field(..., min_length=1, max_length=64)
    mensagem: str = Field(..., min_length=1)


class AgendarIn(BaseModel):
    horario: str = Field(..., min_length=1)
    tipo: str = "reuniao"
    imovel_id: str | None = None


class WebhookIn(BaseModel):
    canal: str = "generico"
    lead_id: str | None = None
    mensagem: str | None = None
    payload: dict[str, Any] | None = None


@app.get("/health")
def health() -> dict[str, Any]:
    api_ok = False
    detalhe = None
    try:
        from src.imoveis.catalogo import buscar
        import config as cfg

        amostra = buscar(intencao="compra", regiao="zona sul", quartos_min=2, limite=1)
        api_ok = bool(amostra)
        detalhe = amostra[0]["id"] if amostra else "sem itens"
        fonte = cfg.IMOVEIS_SOURCE
    except Exception as exc:
        detalhe = str(exc)
        fonte = "?"
    return {
        "status": "ok",
        "llm": bool(config.OPENAI_API_KEY),
        "modelo": config.LLM_MODEL,
        "database": config.DATABASE_URL.split("@")[-1] if "@" in config.DATABASE_URL else "local",
        "imoveis_source": fonte,
        "api_imoveis_ok": api_ok,
        "api_imoveis_detalhe": detalhe,
    }


@app.post("/chat")
def chat(body: ChatIn) -> dict[str, Any]:
    from src.agente.sdr import processar_mensagem

    try:
        out = processar_mensagem(body.lead_id, body.mensagem)
    except Exception as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    return {
        "lead_id": out["lead_id"],
        "resposta": out["resposta"],
        "perfil": out["perfil"],
        "qualificacao": out["qualificacao"],
        "imoveis": out["imoveis"],
        "exibir_imoveis": out.get("exibir_imoveis", bool(out.get("imoveis"))),
        "match_busca": out.get("match_busca", "vazio"),
        "motivo_busca": out.get("motivo_busca", ""),
        "fora_de_escopo": out.get("fora_de_escopo", False),
        "usou_llm": out["usou_llm"],
    }


@app.get("/leads")
def listar_leads() -> list[dict[str, Any]]:
    from src.memoria import conversa as memoria

    return memoria.listar_todos()


@app.get("/leads/{lead_id}")
def obter_lead(lead_id: str) -> dict[str, Any]:
    from src.memoria import conversa as memoria

    estado = memoria.carregar(lead_id)
    if not estado.get("mensagens") and not estado.get("perfil"):
        # lead ainda não existe de fato
        existentes = {c["lead_id"] for c in memoria.listar_todos()}
        if lead_id not in existentes:
            raise HTTPException(status_code=404, detail="Lead não encontrado")
    return estado


@app.get("/leads/{lead_id}/resumo")
def resumo_lead(lead_id: str) -> dict[str, Any]:
    from src.memoria import conversa as memoria
    from src.resumo.corretor import montar_resumo

    estado = memoria.carregar(lead_id)
    return montar_resumo(estado)


@app.post("/leads/{lead_id}/follow-up")
def follow_up_lead(lead_id: str) -> dict[str, Any]:
    from src.agente.sdr import follow_up

    return follow_up(lead_id)


@app.post("/leads/{lead_id}/agendar")
def agendar_lead(lead_id: str, body: AgendarIn) -> dict[str, Any]:
    from src.agenda.scheduler import registrar_agendamento
    from src.memoria import conversa as memoria

    estado = memoria.carregar(lead_id)
    registrar_agendamento(
        estado,
        horario=body.horario,
        tipo=body.tipo,
        imovel_id=body.imovel_id,
    )
    memoria.salvar(estado)
    return {"lead_id": lead_id, "agendamentos": estado.get("agendamentos") or []}


@app.get("/dashboard")
def dashboard() -> dict[str, Any]:
    from src.dashboard.metricas import montar_dashboard

    return montar_dashboard()


@app.post("/webhooks/canal")
def webhook_canal(body: WebhookIn) -> dict[str, Any]:
    """Stub para Chatwoot/WhatsApp — encaminha mensagem ao agente se houver texto."""
    if body.lead_id and body.mensagem:
        from src.agente.sdr import processar_mensagem

        out = processar_mensagem(body.lead_id, body.mensagem)
        return {
            "ok": True,
            "canal": body.canal,
            "lead_id": body.lead_id,
            "resposta": out["resposta"],
            "qualificacao": out["qualificacao"],
        }
    return {
        "ok": True,
        "canal": body.canal,
        "mensagem": "Webhook recebido (configure lead_id + mensagem para processar).",
        "payload": body.payload,
    }
