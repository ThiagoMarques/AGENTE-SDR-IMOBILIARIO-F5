import socket
import threading
import time

import pytest
import uvicorn
from fastapi.testclient import TestClient

import config
from src.crm import cliente
from src.crm.servidor_mock import app
from src.resumo.corretor import montar_resumo


@pytest.fixture(autouse=True)
def isolar(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "CRM_PENDENTES", tmp_path / "pendentes.jsonl")
    monkeypatch.setattr(config, "CRM_MOCK_DB", tmp_path / "crm.json")
    monkeypatch.setattr(config, "CRM_WEBHOOK_TOKEN", "")
    monkeypatch.setattr(config, "CRM_WEBHOOK_URL", "")


def _estado(intencao="compra", completo=True):
    perfil = {"intencao": intencao}
    if completo:
        perfil.update({"regiao": "moema", "quartos": 2, "faixa_preco": 600000, "urgencia": "alta"})
    return {"lead_id": "LEAD-CRM", "perfil": perfil,
            "mensagens": [{"papel": "lead", "texto": "oi"}, {"papel": "lead", "texto": "quero"}],
            "imoveis_sugeridos": ["RE-1"]}


def _porta_livre():
    s = socket.socket(); s.bind(("127.0.0.1", 0)); p = s.getsockname()[1]; s.close(); return p


@pytest.fixture
def servidor():
    porta = _porta_livre()
    srv = uvicorn.Server(uvicorn.Config(app, host="127.0.0.1", port=porta, log_level="error"))
    t = threading.Thread(target=srv.run, daemon=True); t.start()
    for _ in range(50):
        if srv.started:
            break
        time.sleep(0.05)
    yield f"http://127.0.0.1:{porta}"
    srv.should_exit = True; t.join(timeout=5)


def test_sem_url_fica_desabilitado():
    e = _estado()
    assert cliente.sincronizar(e, montar_resumo(e))["status"] == "desabilitado"
    assert "crm" not in e


def test_envio_http_real_para_crm_mock(servidor, monkeypatch):
    monkeypatch.setattr(config, "CRM_WEBHOOK_URL", f"{servidor}/webhook/leads")
    e = _estado()
    r = cliente.sincronizar(e, montar_resumo(e))
    assert r["status"] == "enviado" and r["http"] == 200
    assert r["evento"] == cliente.EVENTO_QUALIFICADO
    assert e["crm"]["pronto_para_agendar"] is True
    leads = TestClient(app).get("/leads").json()
    assert leads[0]["lead_id"] == "LEAD-CRM" and leads[0]["prioridade"] == "quente"


def test_nao_reenvia_sem_mudanca(servidor, monkeypatch):
    monkeypatch.setattr(config, "CRM_WEBHOOK_URL", f"{servidor}/webhook/leads")
    e = _estado()
    cliente.sincronizar(e, montar_resumo(e))
    assert cliente.sincronizar(e, montar_resumo(e)) is None


def test_upsert_sem_duplicar_e_historico(servidor, monkeypatch):
    monkeypatch.setattr(config, "CRM_WEBHOOK_URL", f"{servidor}/webhook/leads")
    e = _estado()
    cliente.sincronizar(e, montar_resumo(e))
    cliente.sincronizar(e, montar_resumo(e), evento=cliente.EVENTO_RESUMO)
    c = TestClient(app)
    assert len(c.get("/leads").json()) == 1
    assert [x["evento"] for x in c.get("/leads/LEAD-CRM").json()["eventos"]] == [
        "lead_qualificado", "resumo_gerado"]


def test_falha_de_rede_vai_para_fila_e_reenvia(servidor, monkeypatch):
    monkeypatch.setattr(config, "CRM_WEBHOOK_URL", f"http://127.0.0.1:{_porta_livre()}/webhook/leads")
    e = _estado()
    r = cliente.sincronizar(e, montar_resumo(e))
    assert r["status"] == "pendente"
    assert config.CRM_PENDENTES.read_text(encoding="utf-8").strip()
    monkeypatch.setattr(config, "CRM_WEBHOOK_URL", f"{servidor}/webhook/leads")
    assert cliente.reenviar_pendentes() == {"enviados": 1, "pendentes": 0}


def test_token_obrigatorio_quando_configurado(monkeypatch):
    monkeypatch.setattr(config, "CRM_WEBHOOK_TOKEN", "segredo")
    c = TestClient(app)
    payload = {"lead_id": "X", "evento": "lead_atualizado"}
    assert c.post("/webhook/leads", json=payload).status_code == 401
    ok = c.post("/webhook/leads", json=payload, headers={"Authorization": "Bearer segredo"})
    assert ok.status_code == 200


def test_painel_html_lista_leads():
    c = TestClient(app)
    c.post("/webhook/leads", json={"lead_id": "L1", "prioridade": "morno", "score": 50, "evento": "x"})
    r = c.get("/")
    assert r.status_code == 200 and "L1" in r.text and "morno" in r.text


def test_agente_envia_eventos_ao_crm_sem_duplicar(servidor, monkeypatch):
    """Fluxo real: processar_mensagem -> webhook -> CRM simulado (memória em RAM)."""
    from src.agente.sdr import processar_mensagem

    monkeypatch.setattr(config, "CRM_WEBHOOK_URL", f"{servidor}/webhook/leads")
    r0 = processar_mensagem("L-E2E", "Oi, tudo bem?")
    assert r0.get("crm") is None  # saudação: nada a enviar
    r1 = processar_mensagem("L-E2E", "Quero comprar apartamento na zona sul.")
    assert r1["crm"]["evento"] == cliente.EVENTO_ATUALIZADO  # intenção identificada
    r2 = processar_mensagem("L-E2E", "2 quartos, até 500 mil, é urgente.")
    assert r2["crm"]["evento"] == cliente.EVENTO_QUALIFICADO
    r3 = processar_mensagem("L-E2E", "Obrigado!")
    assert r3.get("crm") is None or r3["crm"]["evento"] == cliente.EVENTO_ATUALIZADO
    eventos = [e["evento"] for e in TestClient(app).get("/leads/L-E2E").json()["eventos"]]
    assert eventos.count(cliente.EVENTO_QUALIFICADO) == 1
    assert len(TestClient(app).get("/leads").json()) == 1
