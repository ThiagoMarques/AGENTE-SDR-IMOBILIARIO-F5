"""Captura de nome/e-mail no chat, agendamento em um toque e convite por e-mail (sem rede)."""
import base64
from datetime import datetime

import pytest

import config
from src.agenda import calendario as cal
from src.agenda import email_convite, scheduler
from src.agente.sdr import processar_mensagem
from src.dashboard.metricas import montar_dashboard
from src.qualificacao.contato import afirmativo, extrair_nome, negativo, sugerir_correcao_email

TZ = cal.fuso()
REF = datetime(2026, 9, 29, 15, 0, tzinfo=TZ)  # terça-feira
PEDIU_NOME = "Oi! Como posso te chamar?"


@pytest.fixture(autouse=True)
def relogio_fixo(monkeypatch):
    monkeypatch.setattr(scheduler, "agora", lambda: REF)


class Resp:
    def __init__(self, status=200, dados=None, headers=None):
        self.status_code = status
        self._dados = dados
        self.content = b"x" if dados is not None else b""
        self.text = str(dados)
        self.headers = headers or {}

    def json(self):
        return self._dados


@pytest.fixture
def resend(monkeypatch):
    monkeypatch.setattr(config, "RESEND_API_KEY", "re_teste")
    monkeypatch.setattr(config, "EMAIL_FROM", "Imobiliária Demo <visitas@demo.com.br>")
    enviados = []

    def post(url, headers=None, json=None, timeout=None):
        enviados.append({"url": url, "headers": headers, "json": json})
        return Resp(200, {"id": f"msg-{len(enviados)}"})

    monkeypatch.setattr(email_convite.requests, "post", post)
    return enviados


def _ics(envio):
    return base64.b64decode(envio["json"]["attachments"][0]["content"]).decode()


# ---------------------------------------------------------------- nome, e-mail, sim/não

@pytest.mark.parametrize(
    "texto,ultima,esperado",
    [
        ("meu nome é ana souza", "", "Ana Souza"),
        ("Oi, me chamo João e quero comprar", "", "João"),
        ("pode me chamar de Bia", "", "Bia"),
        ("Oi, sou a Maria da Silva", "", "Maria da Silva"),
        ("Carlos", PEDIU_NOME, "Carlos"),
        ("é o Pedro", PEDIU_NOME, "Pedro"),
        ("Ana, quero comprar", PEDIU_NOME, "Ana"),
    ],
)
def test_extrai_nome(texto, ultima, esperado):
    rejeitar = lambda t: "comprar" in t.lower()  # noqa: E731
    assert extrair_nome(texto, ultima, rejeitar) == esperado


@pytest.mark.parametrize(
    "texto,ultima",
    [
        ("Carlos", "Quantos quartos você precisa?"),  # ninguém perguntou o nome
        ("sou a favor de casa", ""),  # 'sou a' sem nome próprio
        ("3 quartos", PEDIU_NOME),
        ("sim", PEDIU_NOME),
    ],
)
def test_nao_inventa_nome(texto, ultima):
    assert extrair_nome(texto, ultima) is None


def test_sugere_correcao_de_dominio():
    assert sugerir_correcao_email("ana@gmial.com") == "ana@gmail.com"
    assert sugerir_correcao_email("ana@hotmal.com") == "ana@hotmail.com"
    assert sugerir_correcao_email("ana@gmail.com") is None
    assert sugerir_correcao_email("ana@construtora-xyz.com.br") is None


def test_sim_e_nao():
    assert afirmativo("Sim!") and afirmativo("pode ser") and afirmativo("isso mesmo")
    assert negativo("não") and negativo("Nao, errei")
    assert not afirmativo("simulação de financiamento") and not negativo("nada disso ainda")


# ---------------------------------------------------------------- .ics e envio

def _evento():
    return cal.Evento(
        titulo="Visita: Apto Moema",
        inicio=datetime(2026, 9, 30, 10, tzinfo=TZ),
        fim=datetime(2026, 9, 30, 11, tzinfo=TZ),
        convidados=["ana@exemplo.com"],
        uid="uid-1@sdr",
    )


def test_ics_request_e_cancel():
    req = cal.gerar_ics(_evento(), metodo="REQUEST", organizador="corretor@demo.com", nomes={"ana@exemplo.com": "Ana"})
    assert "METHOD:REQUEST" in req and "STATUS:CONFIRMED" in req and "SEQUENCE:0" in req
    assert "ORGANIZER;CN=" in req and "mailto:corretor@demo.com" in req
    assert 'ATTENDEE;CN="Ana";ROLE=REQ-PARTICIPANT;PARTSTAT=NEEDS-ACTION;RSVP=TRUE:mailto:ana@exemplo.com' in req.replace("\r\n ", "")

    cancel = cal.gerar_ics(_evento(), metodo="CANCEL", organizador="corretor@demo.com", sequencia=1)
    assert "METHOD:CANCEL" in cancel and "STATUS:CANCELLED" in cancel and "SEQUENCE:1" in cancel
    assert "UID:uid-1@sdr" in cancel and "BEGIN:VALARM" not in cancel


def test_resend_envia_convite_com_ics(resend):
    r = email_convite.enviar(["ana@exemplo.com"], assunto="A", html_corpo="<p>x</p>", texto="x", ics="BEGIN:VCALENDAR", metodo="REQUEST")
    assert r == {"status": "enviado", "provedor": "resend", "id": "msg-1"}
    envio = resend[0]
    assert envio["url"] == email_convite.RESEND_URL and envio["headers"]["Authorization"] == "Bearer re_teste"
    anexo = envio["json"]["attachments"][0]
    assert anexo["content_type"] == 'text/calendar; charset="utf-8"; method=REQUEST'
    assert _ics(envio) == "BEGIN:VCALENDAR"


def test_sendgrid_formato_e_id_no_header(monkeypatch):
    monkeypatch.setattr(config, "SENDGRID_API_KEY", "SG.x")
    monkeypatch.setattr(config, "EMAIL_FROM", "Imobiliária Demo <visitas@demo.com.br>")
    capturado = {}

    def post(url, headers=None, json=None, timeout=None):
        capturado.update(url=url, json=json)
        return Resp(202, None, {"X-Message-Id": "sg-1"})

    monkeypatch.setattr(email_convite.requests, "post", post)
    r = email_convite.enviar(["ana@exemplo.com"], assunto="A", html_corpo="<p>x</p>", texto="x", ics="ICS", metodo="CANCEL")
    assert r == {"status": "enviado", "provedor": "sendgrid", "id": "sg-1"}
    corpo = capturado["json"]
    assert capturado["url"] == email_convite.SENDGRID_URL
    assert corpo["from"] == {"email": "visitas@demo.com.br", "name": "Imobiliária Demo"}
    assert corpo["personalizations"] == [{"to": [{"email": "ana@exemplo.com"}]}]
    assert corpo["attachments"][0]["type"].endswith("method=CANCEL")


def test_falha_no_envio_nao_levanta(monkeypatch, resend):
    monkeypatch.setattr(email_convite.requests, "post", lambda *a, **k: Resp(403, {"message": "domain not verified"}))
    r = email_convite.enviar(["x@y.com"], assunto="A", html_corpo="", texto="", ics="", metodo="REQUEST")
    assert r["status"] == "erro" and "403" in r["erro"]


def test_sem_configuracao_nao_envia():
    assert not email_convite.configurado()
    assert email_convite.enviar(["x@y.com"], assunto="A", html_corpo="", texto="", ics="", metodo="REQUEST") == {"status": "desabilitado"}


# ---------------------------------------------------------------- fluxo completo no chat

def test_fluxo_nome_email_com_erro_de_digitacao_e_um_toque(resend):
    r = processar_mensagem("CAP-1", "Quero comprar apartamento em Moema")
    assert "como posso te chamar" in r["resposta"].lower()

    r = processar_mensagem("CAP-1", "Ana")
    assert r["perfil"]["nome"] == "Ana" and "Prazer, Ana" in r["resposta"]

    r = processar_mensagem("CAP-1", "3 quartos, até 1,5 milhão, urgente essa semana")
    assert "• 30/09/2026 10:00" in r["resposta"] and "e-mail" in r["resposta"]

    r = processar_mensagem("CAP-1", "ana@gmial.com")
    assert "seu e-mail é ana@gmail.com?" in r["resposta"] and "email" not in r["perfil"]

    r = processar_mensagem("CAP-1", "sim")
    assert r["perfil"]["email"] == "ana@gmail.com"
    assert "Posso reservar a visita para quarta, 30/09/2026 às 10:00?" in r["resposta"]
    assert r["agendamento"] is None and resend == []

    r = processar_mensagem("CAP-1", "sim")
    ag = r["agendamento"]
    assert r["resposta"].startswith("Fechado, Ana!") and "convite vai chegar em ana@gmail.com" in r["resposta"]
    assert ag["quando"] == "quarta, 30/09 às 10h" and ag["convite_enviado"] is True

    [envio] = resend
    assert envio["json"]["to"] == ["ana@gmail.com"] and envio["json"]["subject"].startswith("Convite:")
    ics = _ics(envio).replace("\r\n ", "")
    assert "METHOD:REQUEST" in ics and 'CN="Ana"' in ics and "DTSTART:20260930T130000Z" in ics
    assert "Olá, Ana!" in envio["json"]["text"]

    assert montar_dashboard()["captura"] == {"com_nome": 1, "com_email": 1, "convites_enviados": 1}


def test_email_depois_dos_horarios_vira_proposta_de_um_toque(resend):
    processar_mensagem("CAP-6", "Quero comprar apartamento em Moema")
    processar_mensagem("CAP-6", "3 quartos, até 1,5 milhão, urgente essa semana")
    r = processar_mensagem("CAP-6", "meu email é leo@exemplo.com")
    assert r["resposta"].startswith("Anotei seu e-mail. Posso reservar a visita para quarta, 30/09/2026 às 10:00?")
    assert "14:00" not in r["resposta"]

    r = processar_mensagem("CAP-6", "sim")
    assert r["agendamento"] and r["agendamento"]["quando"] == "quarta, 30/09 às 10h"
    assert len(resend) == 1


def test_nao_no_email_sugerido_pede_de_novo_e_aceita_o_redigitado(resend):
    processar_mensagem("CAP-2", "Quero comprar apartamento em Moema")
    processar_mensagem("CAP-2", "ana@gmial.com")
    r = processar_mensagem("CAP-2", "não")
    assert "e-mail certinho" in r["resposta"] and "email" not in r["perfil"]
    r = processar_mensagem("CAP-2", "ana@gmial.com")
    assert r["perfil"]["email"] == "ana@gmial.com"


def test_email_junto_com_horario_agenda_e_envia(resend):
    processar_mensagem("CAP-3", "Quero comprar apartamento em Moema")
    processar_mensagem("CAP-3", "3 quartos, até 1,5 milhão, urgente essa semana")
    r = processar_mensagem("CAP-3", "o segundo, meu email é bia@exemplo.com")
    assert r["agendamento"]["quando"] == "quarta, 30/09 às 14h"
    assert len(resend) == 1 and resend[0]["json"]["to"] == ["bia@exemplo.com"]


def test_nao_duplica_convite_quando_a_agenda_do_corretor_ja_convidou(monkeypatch, resend):
    class Provedor:
        nome = "google"

        def criar(self, ev):
            return {"id": "g1", "link": None}

        def cancelar(self, evento_id):
            pass

        def ocupados(self, inicio, fim):
            return []

    monkeypatch.setattr(cal, "provedores_configurados", lambda: [Provedor()])
    estado = {"lead_id": "CAP-4", "perfil": {"email": "ana@exemplo.com"}, "agendamentos": []}
    ag = scheduler.agendar(estado, datetime(2026, 9, 30, 10, tzinfo=TZ), email="ana@exemplo.com")
    assert resend == [] and scheduler.convite_enviado(ag)


def test_cancelar_e_remarcar_mandam_cancelamento_do_convite(resend):
    estado = {"lead_id": "CAP-5", "perfil": {"email": "ana@exemplo.com"}, "agendamentos": []}
    scheduler.agendar(estado, datetime(2026, 9, 30, 10, tzinfo=TZ), email="ana@exemplo.com")
    scheduler.remarcar(estado, datetime(2026, 10, 1, 15, tzinfo=TZ))
    metodos = [e["json"]["attachments"][0]["content_type"].rsplit("=", 1)[1] for e in resend]
    assert metodos == ["REQUEST", "CANCEL", "REQUEST"]
    assert resend[1]["json"]["subject"].startswith("Cancelado:")
    assert "SEQUENCE:1" in _ics(resend[1])
