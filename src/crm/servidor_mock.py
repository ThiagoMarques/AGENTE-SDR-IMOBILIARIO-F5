"""CRM simulado (FastAPI) que recebe o webhook do agente.

Assim como a base de imóveis é uma API fake, o CRM da POC é simulado, mas a
integração é real: o agente faz HTTP POST e o CRM responde. Trocar pelo
webhook de um CRM de verdade é só mudar CRM_WEBHOOK_URL.

Rotas:
- POST /webhook/leads   recebe eventos (upsert por lead_id + histórico)
- GET  /leads           lista leads, do maior para o menor score (JSON)
- GET  /leads/{id}      detalhe com histórico de eventos
- GET  /                painel HTML simples para o corretor
"""
from __future__ import annotations

import html
import json
from typing import Any

from fastapi import FastAPI, Header, HTTPException
from fastapi.responses import HTMLResponse

import config

app = FastAPI(title="CRM simulado — Agente SDR Imobiliário")


def _carregar() -> dict[str, Any]:
    if config.CRM_MOCK_DB.exists():
        return json.loads(config.CRM_MOCK_DB.read_text(encoding="utf-8"))
    return {}


def _salvar(db: dict[str, Any]) -> None:
    config.CRM_MOCK_DB.parent.mkdir(parents=True, exist_ok=True)
    config.CRM_MOCK_DB.write_text(json.dumps(db, ensure_ascii=False, indent=2), encoding="utf-8")


@app.post("/webhook/leads")
def receber(payload: dict[str, Any], authorization: str | None = Header(default=None)) -> dict[str, Any]:
    if config.CRM_WEBHOOK_TOKEN and authorization != f"Bearer {config.CRM_WEBHOOK_TOKEN}":
        raise HTTPException(status_code=401, detail="token inválido")
    lead_id = payload.get("lead_id")
    if not lead_id:
        raise HTTPException(status_code=422, detail="lead_id obrigatório")
    db = _carregar()
    registro = db.get(lead_id) or {"lead_id": lead_id, "eventos": []}
    registro.update({
        "prioridade": payload.get("prioridade"),
        "score": payload.get("score"),
        "encaminhamento": payload.get("encaminhamento"),
        "acao_sugerida": payload.get("acao_sugerida"),
        "resumo": payload.get("resumo"),
        "atualizado_em": payload.get("enviado_em"),
    })
    registro["eventos"].append({"evento": payload.get("evento"), "em": payload.get("enviado_em")})
    db[lead_id] = registro
    _salvar(db)
    return {"ok": True, "lead_id": lead_id, "total_eventos": len(registro["eventos"])}


@app.get("/leads")
def listar() -> list[dict[str, Any]]:
    leads = [{k: v for k, v in r.items() if k != "resumo"} for r in _carregar().values()]
    return sorted(leads, key=lambda r: r.get("score") or 0, reverse=True)


@app.get("/leads/{lead_id}")
def detalhe(lead_id: str) -> dict[str, Any]:
    r = _carregar().get(lead_id)
    if not r:
        raise HTTPException(status_code=404, detail="lead não encontrado")
    return r


@app.get("/", response_class=HTMLResponse)
def painel() -> str:
    cores = {"quente": "#c0392b", "morno": "#d68910", "frio": "#2e86c1"}
    linhas = []
    for r in listar():
        e = lambda v: html.escape(str(v if v is not None else "-"))
        cor = cores.get(r.get("prioridade"), "#777")
        linhas.append(
            f"<tr><td><a href='/leads/{e(r['lead_id'])}'>{e(r['lead_id'])}</a></td>"
            f"<td><b style='color:{cor}'>{e(r.get('prioridade'))}</b></td><td>{e(r.get('score'))}</td>"
            f"<td>{e(r.get('encaminhamento'))}</td><td>{e(r.get('acao_sugerida'))}</td>"
            f"<td>{e(r['eventos'][-1]['evento'] if r.get('eventos') else '-')}</td>"
            f"<td>{e(r.get('atualizado_em'))}</td></tr>"
        )
    corpo = "".join(linhas) or "<tr><td colspan='7'>Nenhum lead recebido ainda.</td></tr>"
    return f"""<!doctype html><html lang="pt-BR"><head><meta charset="utf-8">
<meta http-equiv="refresh" content="5"><title>CRM simulado</title>
<style>body{{font-family:system-ui,sans-serif;margin:24px;color:#222}}
table{{border-collapse:collapse;width:100%}}th,td{{padding:8px 10px;border-bottom:1px solid #ddd;text-align:left;font-size:14px}}
th{{background:#f4f4f4}}</style></head><body>
<h1>CRM simulado — leads do Agente SDR</h1>
<p>Atualiza a cada 5 s. Ordenado por score.</p>
<table><tr><th>Lead</th><th>Prioridade</th><th>Score</th><th>Encaminhar</th><th>Ação sugerida</th>
<th>Último evento</th><th>Atualizado</th></tr>{corpo}</table></body></html>"""
