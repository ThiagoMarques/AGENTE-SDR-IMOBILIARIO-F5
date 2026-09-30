"""Agendamento pelo chat + integração Google Agenda / Outlook (sem rede)."""
from datetime import datetime, timedelta, timezone
from urllib.parse import parse_qs, urlparse

import pytest
from fastapi.testclient import TestClient

import config
from src.agenda import calendario as cal
from src.agenda import scheduler
from src.agente.sdr import processar_mensagem
from src.dashboard.metricas import montar_dashboard

TZ = cal.fuso()
REF = datetime(2026, 9, 29, 15, 0, tzinfo=TZ)  # terça-feira
OFERTADOS = ["30/09/2026 10:00", "30/09/2026 14:00", "30/09/2026 16:00"]


@pytest.fixture(autouse=True)
def relogio_fixo(monkeypatch):
    monkeypatch.setattr(scheduler, "agora", lambda: REF)


class ProvedorFake:
    nome = "google"

    def __init__(self, ocupados=None, falhar=False):
        self._ocupados = ocupados or []
        self.falhar = falhar
        self.criados, self.convites, self.cancelados = [], [], []

    def criar(self, ev):
        if self.falhar:
            raise cal.ErroAgenda("google HTTP 500")
        self.criados.append(ev)
        return {"id": f"evt-{len(self.criados)}", "link": "https://calendar.google.com/event?eid=x"}

    def adicionar_convidados(self, evento_id, emails):
        self.convites.append((evento_id, emails))

    def cancelar(self, evento_id):
        self.cancelados.append(evento_id)

    def ocupados(self, inicio, fim):
        return self._ocupados


@pytest.fixture
def provedor(monkeypatch):
    fake = ProvedorFake()
    monkeypatch.setattr(cal, "provedores_configurados", lambda: [fake])
    return fake


def _dt(dia, mes, hora, minuto=0):
    return datetime(2026, mes, dia, hora, minuto, tzinfo=TZ)


# ---------------------------------------------------------------- leitura da escolha

@pytest.mark.parametrize(
    "texto,esperado",
    [
        ("pode ser amanhã às 10", _dt(30, 9, 10)),
        ("o segundo", _dt(30, 9, 14)),
        ("pode ser o último", _dt(30, 9, 16)),
        ("quinta 15h", _dt(1, 10, 15)),
        ("30/09 14:00", _dt(30, 9, 14)),
        ("às 2 da tarde", _dt(30, 9, 14)),
        ("prefiro à tarde", _dt(30, 9, 14)),
        ("sexta 10h30", _dt(2, 10, 10, 30)),
        ("amanhã meio-dia", _dt(30, 9, 12)),
        ("pode ser o de 16", _dt(30, 9, 16)),
        ("dia 2 às 11", _dt(2, 10, 11)),
        ("não posso amanhã, pode ser quinta às 9h", _dt(1, 10, 9)),
    ],
)
def test_interpreta_horario_escolhido(texto, esperado):
    e = scheduler.interpretar_escolha(texto, OFERTADOS, REF)
    assert e is not None and e.inicio == esperado and not e.invalido


@pytest.mark.parametrize(
    "texto",
    ["2 quartos até 900 mil", "de 2 a 3 quartos", "quero 3 quartos em Moema", "ticket de 400 mil, 6% ao ano"],
)
def test_sem_falso_positivo_em_dados_do_imovel(texto):
    assert scheduler.interpretar_escolha(texto, OFERTADOS, REF) is None


def test_so_o_dia_pede_horarios_daquele_dia():
    e = scheduler.interpretar_escolha("quinta", OFERTADOS, REF)
    assert e.inicio is None and e.dia == _dt(1, 10, 0).date()


@pytest.mark.parametrize(
    "texto,motivo",
    [("domingo 10h", "domingo"), ("amanhã às 22h", "fora_expediente"), ("hoje às 10", "passado")],
)
def test_horarios_invalidos(texto, motivo):
    assert scheduler.interpretar_escolha(texto, OFERTADOS, REF).invalido == motivo


def test_recusa():
    assert scheduler.interpretar_escolha("nenhum desses", OFERTADOS, REF).recusou


# ---------------------------------------------------------------- horários livres

def test_sugere_a_partir_de_amanha_e_pula_domingo():
    sabado = datetime(2026, 10, 3, 9, 0, tzinfo=TZ)
    assert scheduler.sugerir_horarios(3, referencia=sabado) == [
        "05/10/2026 10:00", "05/10/2026 14:00", "05/10/2026 16:00"]


def test_sugestao_respeita_agenda_ocupada_do_corretor(monkeypatch):
    ocupado = [(_dt(30, 9, 9, 30), _dt(30, 9, 10, 30))]
    monkeypatch.setattr(cal, "provedores_configurados", lambda: [ProvedorFake(ocupados=ocupado)])
    assert scheduler.sugerir_horarios(3)[0] == "30/09/2026 14:00"


# ---------------------------------------------------------------- links e .ics

def _evento():
    return cal.Evento(
        titulo="Visita: Apto 3 dorms, Moema; vista",
        inicio=_dt(30, 9, 10),
        fim=_dt(30, 9, 11),
        descricao="Linha 1\nLinha 2 com texto bem longo " + "x" * 120,
        local="Av. Ibirapuera, 2900 — Moema",
    )


def test_link_google_em_utc_com_fuso():
    q = parse_qs(urlparse(cal.link_google(_evento())).query)
    assert q["action"] == ["TEMPLATE"]
    assert q["dates"] == ["20260930T130000Z/20260930T140000Z"]
    assert q["ctz"] == ["America/Sao_Paulo"]


def test_links_outlook_pessoal_e_365():
    links = cal.links(_evento())
    assert links["outlook"].startswith("https://outlook.live.com/calendar/0/deeplink/compose?")
    assert links["outlook_365"].startswith("https://outlook.office.com/")
    q = parse_qs(urlparse(links["outlook"]).query)
    assert q["startdt"] == ["2026-09-30T10:00:00-03:00"] and q["rru"] == ["addevent"]


def test_ics_rfc5545():
    ics = cal.gerar_ics(_evento())
    assert ics.startswith("BEGIN:VCALENDAR\r\n") and ics.endswith("END:VCALENDAR\r\n")
    assert "DTSTART:20260930T130000Z" in ics and "BEGIN:VALARM" in ics
    assert "SUMMARY:Visita: Apto 3 dorms\\, Moema\\; vista" in ics
    assert "Linha 1\\nLinha 2" in ics
    assert all(len(l.encode()) <= 75 for l in ics.split("\r\n"))


# ---------------------------------------------------------------- provedores (HTTP mockado)

class Resp:
    def __init__(self, status=200, dados=None):
        self.status_code = status
        self._dados = dados
        self.content = b"x" if dados is not None else b""
        self.text = str(dados)

    def json(self):
        return self._dados


def test_google_cria_evento_com_convite(monkeypatch):
    monkeypatch.setattr(config, "GOOGLE_CLIENT_ID", "cid")
    monkeypatch.setattr(config, "GOOGLE_CLIENT_SECRET", "sec")
    cal.salvar_refresh_token("google", "rt-arquivo")
    chamadas = []

    def post(url, data=None, timeout=None):
        chamadas.append(("TOKEN", url, data))
        return Resp(200, {"access_token": "at", "expires_in": 3600})

    def request(metodo, url, headers=None, timeout=None, **kw):
        chamadas.append((metodo, url, kw, headers))
        return Resp(200, {"id": "g1", "htmlLink": "https://calendar.google.com/e/g1"})

    monkeypatch.setattr(cal.requests, "post", post)
    monkeypatch.setattr(cal.requests, "request", request)

    assert [p.nome for p in cal.provedores_configurados()] == ["google"]
    ev = _evento()
    ev.convidados = ["ana@exemplo.com"]
    [r] = cal.criar_nos_provedores(ev)
    assert r == {"provedor": "google", "status": "criado", "id": "g1", "link": "https://calendar.google.com/e/g1"}
    assert chamadas[0][2]["refresh_token"] == "rt-arquivo"
    metodo, url, kw, headers = chamadas[1]
    assert metodo == "POST" and url.endswith("/calendars/primary/events")
    assert kw["params"] == {"sendUpdates": "all"} and headers["Authorization"] == "Bearer at"
    assert kw["json"]["attendees"] == [{"email": "ana@exemplo.com"}]
    assert kw["json"]["start"]["timeZone"] == "America/Sao_Paulo"


def test_outlook_salva_refresh_token_rotacionado_e_usa_utc(monkeypatch):
    monkeypatch.setattr(config, "MS_CLIENT_ID", "app")
    monkeypatch.setattr(config, "MS_REFRESH_TOKEN", "rt-env")
    enviados = {}

    monkeypatch.setattr(
        cal.requests, "post",
        lambda url, data=None, timeout=None: Resp(200, {"access_token": "at", "refresh_token": "rt-novo"}),
    )

    def request(metodo, url, headers=None, timeout=None, **kw):
        enviados.update(metodo=metodo, url=url, **kw)
        return Resp(201, {"id": "o1", "webLink": "https://outlook.live.com/o1"})

    monkeypatch.setattr(cal.requests, "request", request)
    [r] = cal.criar_nos_provedores(_evento())
    assert r["status"] == "criado" and r["provedor"] == "outlook"
    assert enviados["url"] == "https://graph.microsoft.com/v1.0/me/events"
    assert enviados["json"]["start"] == {"dateTime": "2026-09-30T13:00:00", "timeZone": "UTC"}
    assert cal.refresh_token("outlook") == "rt-novo"


def test_outlook_ocupados_ignora_livre(monkeypatch):
    monkeypatch.setattr(config, "MS_CLIENT_ID", "app")
    monkeypatch.setattr(config, "MS_REFRESH_TOKEN", "rt")
    monkeypatch.setattr(cal.requests, "post", lambda *a, **k: Resp(200, {"access_token": "at"}))
    itens = [
        {"showAs": "busy", "start": {"dateTime": "2026-09-30T13:00:00.0000000"}, "end": {"dateTime": "2026-09-30T14:00:00.0000000"}},
        {"showAs": "free", "start": {"dateTime": "2026-09-30T17:00:00.0000000"}, "end": {"dateTime": "2026-09-30T18:00:00.0000000"}},
    ]
    monkeypatch.setattr(cal.requests, "request", lambda *a, **k: Resp(200, {"value": itens}))
    ocupados = cal.horarios_ocupados(_dt(30, 9, 0), _dt(1, 10, 0))
    assert ocupados == [(datetime(2026, 9, 30, 13, tzinfo=timezone.utc), datetime(2026, 9, 30, 14, tzinfo=timezone.utc))]


def test_falha_do_provedor_nao_impede_agendamento(monkeypatch):
    monkeypatch.setattr(cal, "provedores_configurados", lambda: [ProvedorFake(falhar=True)])
    estado = {"lead_id": "L", "perfil": {}, "agendamentos": []}
    ag = scheduler.agendar(estado, _dt(30, 9, 10), imovel_id="BR-SP-002")
    assert ag["status"] == "agendado" and ag["tipo"] == "visita"
    assert ag["detalhes"]["calendarios"][0]["status"] == "erro"


def test_sem_credenciais_so_links():
    assert cal.status() == {"google": False, "outlook": False}
    assert cal.provedores_configurados() == []


# ---------------------------------------------------------------- fluxo no chat

def _qualificar(lead):
    processar_mensagem(lead, "Quero comprar apartamento em Moema")
    return processar_mensagem(lead, "3 quartos, até 1,5 milhão, urgente essa semana")


def test_lead_escolhe_horario_no_chat_e_dashboard_conta(provedor):
    r = _qualificar("AG-1")
    assert "• 30/09/2026 10:00" in r["resposta"]
    assert montar_dashboard()["agendamentos"] == 0

    r = processar_mensagem("AG-1", "pode ser amanhã às 10")
    assert "Visita marcada para quarta, 30/09 às 10h" in r["resposta"]
    ag = r["agendamento"]
    assert ag["status"] == "agendado" and ag["imovel_id"] == "BR-SP-002"
    assert ag["links"]["ics"] == "/leads/AG-1/agendamentos/0/convite.ics"
    assert ag["calendarios"][0]["status"] == "criado"
    assert provedor.criados[0].inicio == _dt(30, 9, 10)
    assert montar_dashboard()["agendamentos"] == 1


def test_email_depois_do_agendamento_vira_convite(provedor):
    _qualificar("AG-2")
    processar_mensagem("AG-2", "o segundo")
    r = processar_mensagem("AG-2", "meu email é Ana@Exemplo.com")
    assert "ana@exemplo.com" in r["resposta"] and "convite" in r["resposta"]
    assert r["perfil"]["email"] == "ana@exemplo.com"
    assert r["agendamento"]["convidados"] == ["ana@exemplo.com"]
    assert provedor.convites == [("evt-1", ["ana@exemplo.com"])]


def test_remarcar_e_cancelar(provedor):
    _qualificar("AG-3")
    processar_mensagem("AG-3", "pode ser amanhã às 10")

    r = processar_mensagem("AG-3", "preciso remarcar")
    assert "30/09/2026 10:00" not in r["resposta"] and "•" in r["resposta"]
    r = processar_mensagem("AG-3", "quinta às 15h")
    assert r["resposta"].startswith("Remarcado!") and r["agendamento"]["quando"] == "quinta, 01/10 às 15h"
    assert provedor.cancelados == ["evt-1"]
    assert montar_dashboard()["agendamentos"] == 1

    r = processar_mensagem("AG-3", "quero cancelar a visita")
    assert "cancelei" in r["resposta"] and r["agendamento"] is None
    assert montar_dashboard()["agendamentos"] == 0


def test_nao_reoferece_horarios_com_visita_marcada():
    _qualificar("AG-4")
    processar_mensagem("AG-4", "o primeiro")
    r = processar_mensagem("AG-4", "tem vaga de garagem?")
    assert "•" not in r["resposta"]


def test_horario_ocupado_no_calendario_oferece_alternativas(monkeypatch):
    fake = ProvedorFake()
    monkeypatch.setattr(cal, "provedores_configurados", lambda: [fake])
    _qualificar("AG-5")
    fake._ocupados = [(_dt(30, 9, 14), _dt(30, 9, 15))]
    r = processar_mensagem("AG-5", "às 14h")
    assert "compromisso" in r["resposta"] and r["agendamento"] is None


def test_data_e_hora_explicitas_agendam_sem_oferta_previa():
    r = processar_mensagem("AG-6", "Quero agendar uma visita amanhã às 10h")
    assert r["agendamento"] and r["agendamento"]["quando"] == "quarta, 30/09 às 10h"


def test_numero_solto_nao_vira_horario_sem_oferta():
    assert scheduler.interpretar_escolha("orçamento de 15", [], REF) is None


def test_llm_que_fala_de_visita_sem_horarios_recebe_a_lista(monkeypatch):
    """Regressão: o GPT perguntava 'quer agendar?' sem horários e depois 'confirmava' sem gravar."""
    from src.agente import sdr

    monkeypatch.setattr(sdr, "_resposta_llm", lambda *a, **k: "Achei um apto em Moema. Quer agendar uma visita?")
    r = _qualificar("AG-7")
    assert "• 30/09/2026 10:00" in r["resposta"]
    r = processar_mensagem("AG-7", "pode ser amanhã às 10")
    assert r["agendamento"] is not None and montar_dashboard()["agendamentos"] == 1


# ---------------------------------------------------------------- API

def test_api_agendar_e_baixar_ics():
    from api.app import app

    c = TestClient(app)
    r = c.post("/leads/API-1/agendar", json={"horario": "30/09/2026 14:00", "imovel_id": "BR-SP-002"})
    assert r.status_code == 200
    ag = r.json()["agendamento"]
    assert ag["quando"] == "quarta, 30/09 às 14h" and ag["tipo"] == "visita"

    ics = c.get(ag["links"]["ics"])
    assert ics.status_code == 200 and ics.headers["content-type"].startswith("text/calendar")
    assert "attachment" in ics.headers["content-disposition"]
    assert "DTSTART:20260930T170000Z" in ics.text

    assert c.get("/leads/API-1/agendamentos/9/convite.ics").status_code == 404
    assert c.post("/leads/API-1/agendar", json={"horario": "amanhã"}).status_code == 422
    assert c.get("/dashboard").json()["agendamentos"] == 1
