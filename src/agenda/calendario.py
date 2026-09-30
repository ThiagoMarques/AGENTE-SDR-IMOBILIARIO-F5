"""Agenda do corretor: Google Agenda (Gmail) e Outlook (Outlook.com / Microsoft 365).

Três níveis, do mais simples ao mais integrado:
1. Links "adicionar à agenda" (Google e Outlook) e arquivo .ics — sem credencial,
   funcionam para qualquer lead, em qualquer cliente de e-mail.
2. Evento criado na agenda do corretor via API (Google Calendar / Microsoft Graph),
   com convite enviado ao lead quando ele informa o e-mail.
3. Consulta de horários ocupados, para o agente só oferecer janelas livres.

Mesmo desenho do CRM: um adapter por provedor e falha de rede nunca derruba o
atendimento (o agendamento fica registrado e os links continuam valendo).
"""
from __future__ import annotations

import json
import os
import re
import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Protocol
from urllib.parse import quote, urlencode
from zoneinfo import ZoneInfo

import requests

import config

GOOGLE_TOKEN_URL = "https://oauth2.googleapis.com/token"
GOOGLE_API = "https://www.googleapis.com/calendar/v3"
GOOGLE_ESCOPOS = (
    "https://www.googleapis.com/auth/calendar.events "
    "https://www.googleapis.com/auth/calendar.freebusy"
)
MS_API = "https://graph.microsoft.com/v1.0"
MS_ESCOPOS = "offline_access Calendars.ReadWrite"


def fuso() -> ZoneInfo:
    return ZoneInfo(config.AGENDA_TZ)


def ms_token_url() -> str:
    return f"https://login.microsoftonline.com/{config.MS_TENANT}/oauth2/v2.0/token"


class ErroAgenda(Exception):
    pass


_ERROS_REDE = (ErroAgenda, requests.RequestException, KeyError, ValueError, TypeError)


@dataclass
class Evento:
    titulo: str
    inicio: datetime
    fim: datetime
    descricao: str = ""
    local: str = ""
    convidados: list[str] = field(default_factory=list)
    uid: str = field(default_factory=lambda: f"{uuid.uuid4()}@agente-sdr")


def _utc(dt: datetime) -> datetime:
    return dt.astimezone(timezone.utc)


def _basico_utc(dt: datetime) -> str:
    return _utc(dt).strftime("%Y%m%dT%H%M%SZ")


def _parse_iso(valor: str) -> datetime:
    """Aceita '...Z' (Google) e a fração de 7 dígitos sem fuso do Graph (já em UTC)."""
    texto = re.sub(r"(\.\d{6})\d+", r"\1", valor.replace("Z", "+00:00"))
    dt = datetime.fromisoformat(texto)
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


# ---------------------------------------------------------------- nível 1

def link_google(ev: Evento) -> str:
    params = {
        "action": "TEMPLATE",
        "text": ev.titulo,
        "dates": f"{_basico_utc(ev.inicio)}/{_basico_utc(ev.fim)}",
        "details": ev.descricao,
        "location": ev.local,
        "ctz": config.AGENDA_TZ,
    }
    return "https://calendar.google.com/calendar/render?" + urlencode(params, quote_via=quote)


def link_outlook(ev: Evento, *, corporativo: bool = False) -> str:
    base = "https://outlook.office.com" if corporativo else "https://outlook.live.com"
    params = {
        "path": "/calendar/action/compose",
        "rru": "addevent",
        "subject": ev.titulo,
        "startdt": ev.inicio.isoformat(),
        "enddt": ev.fim.isoformat(),
        "body": ev.descricao,
        "location": ev.local,
    }
    return f"{base}/calendar/0/deeplink/compose?" + urlencode(params, quote_via=quote)


def links(ev: Evento) -> dict[str, str]:
    return {
        "google": link_google(ev),
        "outlook": link_outlook(ev),
        "outlook_365": link_outlook(ev, corporativo=True),
    }


def _ics_texto(texto: str) -> str:
    return (
        texto.replace("\\", "\\\\")
        .replace(";", "\\;")
        .replace(",", "\\,")
        .replace("\r\n", "\\n")
        .replace("\n", "\\n")
    )


def _dobrar(linha: str) -> str:
    """RFC 5545: no máximo 75 octetos por linha; a continuação começa com espaço."""
    partes, atual = [], ""
    for ch in linha:
        if len((atual + ch).encode("utf-8")) > 75:
            partes.append(atual)
            atual = " " + ch
        else:
            atual += ch
    partes.append(atual)
    return "\r\n".join(partes)


def gerar_ics(ev: Evento) -> str:
    linhas = [
        "BEGIN:VCALENDAR",
        "VERSION:2.0",
        "PRODID:-//Agente SDR Imobiliario//PT-BR",
        "CALSCALE:GREGORIAN",
        "METHOD:PUBLISH",
        "BEGIN:VEVENT",
        f"UID:{ev.uid}",
        f"DTSTAMP:{_basico_utc(datetime.now(timezone.utc))}",
        f"DTSTART:{_basico_utc(ev.inicio)}",
        f"DTEND:{_basico_utc(ev.fim)}",
        f"SUMMARY:{_ics_texto(ev.titulo)}",
    ]
    if ev.descricao:
        linhas.append(f"DESCRIPTION:{_ics_texto(ev.descricao)}")
    if ev.local:
        linhas.append(f"LOCATION:{_ics_texto(ev.local)}")
    linhas += [
        "BEGIN:VALARM",
        "ACTION:DISPLAY",
        "DESCRIPTION:Lembrete da visita",
        "TRIGGER:-PT1H",
        "END:VALARM",
        "END:VEVENT",
        "END:VCALENDAR",
    ]
    return "\r\n".join(_dobrar(l) for l in linhas) + "\r\n"


# ---------------------------------------------------------------- tokens OAuth

def _ler_tokens() -> dict[str, Any]:
    try:
        return json.loads(config.AGENDA_TOKENS.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def salvar_refresh_token(provedor: str, refresh_token: str) -> None:
    dados = _ler_tokens()
    dados[provedor] = {
        "refresh_token": refresh_token,
        "atualizado_em": datetime.now(timezone.utc).isoformat(),
    }
    config.AGENDA_TOKENS.parent.mkdir(parents=True, exist_ok=True)
    config.AGENDA_TOKENS.write_text(json.dumps(dados, indent=2), encoding="utf-8")
    try:
        os.chmod(config.AGENDA_TOKENS, 0o600)
    except OSError:
        pass


def refresh_token(provedor: str) -> str:
    """Token salvo pelo --agenda-auth tem precedência sobre o .env (Microsoft rotaciona)."""
    salvo = (_ler_tokens().get(provedor) or {}).get("refresh_token")
    padrao = config.GOOGLE_REFRESH_TOKEN if provedor == "google" else config.MS_REFRESH_TOKEN
    return salvo or padrao


# ---------------------------------------------------------------- níveis 2 e 3

class ProvedorAgenda(Protocol):
    nome: str

    def criar(self, ev: Evento) -> dict[str, Any]: ...

    def adicionar_convidados(self, evento_id: str, emails: list[str]) -> None: ...

    def cancelar(self, evento_id: str) -> None: ...

    def ocupados(self, inicio: datetime, fim: datetime) -> list[tuple[datetime, datetime]]: ...


_ACCESS_TOKENS: dict[str, tuple[str, float]] = {}


class _ProvedorOAuth:
    nome = ""

    def _renovar(self) -> tuple[str, float]:
        raise NotImplementedError

    def _token(self) -> str:
        token, expira = _ACCESS_TOKENS.get(self.nome, ("", 0.0))
        if not token or time.time() > expira - 60:
            token, duracao = self._renovar()
            _ACCESS_TOKENS[self.nome] = (token, time.time() + duracao)
        return token

    def _req(
        self,
        metodo: str,
        url: str,
        *,
        headers: dict[str, str] | None = None,
        **kwargs: Any,
    ) -> dict[str, Any]:
        cab = {"Authorization": f"Bearer {self._token()}", **(headers or {})}
        resp = requests.request(metodo, url, headers=cab, timeout=config.AGENDA_TIMEOUT, **kwargs)
        if resp.status_code >= 400:
            raise ErroAgenda(f"{self.nome} HTTP {resp.status_code}: {resp.text[:200]}")
        return resp.json() if resp.content else {}


def _post_token(url: str, dados: dict[str, str], provedor: str) -> dict[str, Any]:
    resp = requests.post(url, data=dados, timeout=config.AGENDA_TIMEOUT)
    if resp.status_code >= 400:
        raise ErroAgenda(f"{provedor} token HTTP {resp.status_code}: {resp.text[:200]}")
    return resp.json()


class GoogleAgenda(_ProvedorOAuth):
    nome = "google"

    def _renovar(self) -> tuple[str, float]:
        d = _post_token(
            GOOGLE_TOKEN_URL,
            {
                "client_id": config.GOOGLE_CLIENT_ID,
                "client_secret": config.GOOGLE_CLIENT_SECRET,
                "refresh_token": refresh_token("google"),
                "grant_type": "refresh_token",
            },
            self.nome,
        )
        return d["access_token"], float(d.get("expires_in", 3600))

    def _eventos(self, evento_id: str = "") -> str:
        cal = quote(config.GOOGLE_CALENDAR_ID, safe="")
        return f"{GOOGLE_API}/calendars/{cal}/events" + (f"/{quote(evento_id, safe='')}" if evento_id else "")

    def criar(self, ev: Evento) -> dict[str, Any]:
        corpo = {
            "summary": ev.titulo,
            "description": ev.descricao,
            "location": ev.local,
            "start": {"dateTime": ev.inicio.isoformat(), "timeZone": config.AGENDA_TZ},
            "end": {"dateTime": ev.fim.isoformat(), "timeZone": config.AGENDA_TZ},
            "attendees": [{"email": e} for e in ev.convidados],
            "reminders": {"useDefault": True},
        }
        d = self._req("POST", self._eventos(), params={"sendUpdates": "all"}, json=corpo)
        return {"id": d.get("id"), "link": d.get("htmlLink")}

    def adicionar_convidados(self, evento_id: str, emails: list[str]) -> None:
        atuais = self._req("GET", self._eventos(evento_id)).get("attendees") or []
        conhecidos = {str(a.get("email", "")).lower() for a in atuais}
        novos = atuais + [{"email": e} for e in emails if e.lower() not in conhecidos]
        self._req("PATCH", self._eventos(evento_id), params={"sendUpdates": "all"}, json={"attendees": novos})

    def cancelar(self, evento_id: str) -> None:
        self._req("DELETE", self._eventos(evento_id), params={"sendUpdates": "all"})

    def ocupados(self, inicio: datetime, fim: datetime) -> list[tuple[datetime, datetime]]:
        d = self._req(
            "POST",
            f"{GOOGLE_API}/freeBusy",
            json={
                "timeMin": _utc(inicio).isoformat(),
                "timeMax": _utc(fim).isoformat(),
                "items": [{"id": config.GOOGLE_CALENDAR_ID}],
            },
        )
        cal = (d.get("calendars") or {}).get(config.GOOGLE_CALENDAR_ID) or {}
        return [(_parse_iso(b["start"]), _parse_iso(b["end"])) for b in cal.get("busy") or []]


class OutlookAgenda(_ProvedorOAuth):
    nome = "outlook"

    def _renovar(self) -> tuple[str, float]:
        dados = {
            "client_id": config.MS_CLIENT_ID,
            "grant_type": "refresh_token",
            "refresh_token": refresh_token("outlook"),
            "scope": MS_ESCOPOS,
        }
        if config.MS_CLIENT_SECRET:
            dados["client_secret"] = config.MS_CLIENT_SECRET
        d = _post_token(ms_token_url(), dados, self.nome)
        if d.get("refresh_token"):
            salvar_refresh_token("outlook", d["refresh_token"])
        return d["access_token"], float(d.get("expires_in", 3600))

    @staticmethod
    def _dt(dt: datetime) -> dict[str, str]:
        return {"dateTime": _utc(dt).strftime("%Y-%m-%dT%H:%M:%S"), "timeZone": "UTC"}

    @staticmethod
    def _convidado(email: str) -> dict[str, Any]:
        return {"emailAddress": {"address": email}, "type": "required"}

    def criar(self, ev: Evento) -> dict[str, Any]:
        corpo = {
            "subject": ev.titulo,
            "body": {"contentType": "text", "content": ev.descricao},
            "start": self._dt(ev.inicio),
            "end": self._dt(ev.fim),
            "location": {"displayName": ev.local},
            "attendees": [self._convidado(e) for e in ev.convidados],
            "isReminderOn": True,
            "reminderMinutesBeforeStart": 60,
        }
        d = self._req("POST", f"{MS_API}/me/events", json=corpo)
        return {"id": d.get("id"), "link": d.get("webLink")}

    def adicionar_convidados(self, evento_id: str, emails: list[str]) -> None:
        url = f"{MS_API}/me/events/{quote(evento_id, safe='')}"
        atuais = self._req("GET", url, params={"$select": "attendees"}).get("attendees") or []
        conhecidos = {str((a.get("emailAddress") or {}).get("address", "")).lower() for a in atuais}
        novos = atuais + [self._convidado(e) for e in emails if e.lower() not in conhecidos]
        self._req("PATCH", url, json={"attendees": novos})

    def cancelar(self, evento_id: str) -> None:
        # No calendário do organizador, apagar a reunião envia o cancelamento aos convidados.
        self._req("DELETE", f"{MS_API}/me/events/{quote(evento_id, safe='')}")

    def ocupados(self, inicio: datetime, fim: datetime) -> list[tuple[datetime, datetime]]:
        d = self._req(
            "GET",
            f"{MS_API}/me/calendarView",
            headers={"Prefer": 'outlook.timezone="UTC"'},
            params={
                "startDateTime": _utc(inicio).isoformat(),
                "endDateTime": _utc(fim).isoformat(),
                "$select": "start,end,showAs",
                "$top": "100",
            },
        )
        return [
            (_parse_iso(e["start"]["dateTime"]), _parse_iso(e["end"]["dateTime"]))
            for e in d.get("value") or []
            if e.get("showAs") not in ("free", "workingElsewhere")
        ]


def provedores_configurados() -> list[ProvedorAgenda]:
    provedores: list[ProvedorAgenda] = []
    if config.GOOGLE_CLIENT_ID and config.GOOGLE_CLIENT_SECRET and refresh_token("google"):
        provedores.append(GoogleAgenda())
    if config.MS_CLIENT_ID and refresh_token("outlook"):
        provedores.append(OutlookAgenda())
    return provedores


def status() -> dict[str, bool]:
    nomes = {p.nome for p in provedores_configurados()}
    return {"google": "google" in nomes, "outlook": "outlook" in nomes}


def _provedor(nome: str) -> ProvedorAgenda | None:
    return next((p for p in provedores_configurados() if p.nome == nome), None)


def criar_nos_provedores(ev: Evento) -> list[dict[str, Any]]:
    """Cria o evento em cada agenda configurada. Nunca levanta exceção."""
    resultados = []
    for p in provedores_configurados():
        try:
            r = p.criar(ev)
            resultados.append({"provedor": p.nome, "status": "criado", "id": r.get("id"), "link": r.get("link")})
        except _ERROS_REDE as exc:
            resultados.append({"provedor": p.nome, "status": "erro", "erro": str(exc)[:200]})
    return resultados


def convidar(calendarios: list[dict[str, Any]], emails: list[str]) -> list[dict[str, Any]]:
    for c in calendarios:
        p = _provedor(str(c.get("provedor")))
        if c.get("status") != "criado" or not c.get("id") or p is None:
            continue
        try:
            p.adicionar_convidados(str(c["id"]), emails)
            c["convidados"] = sorted(set((c.get("convidados") or []) + emails))
        except _ERROS_REDE as exc:
            c["erro_convite"] = str(exc)[:200]
    return calendarios


def cancelar_nos_provedores(calendarios: list[dict[str, Any]]) -> list[dict[str, Any]]:
    for c in calendarios:
        p = _provedor(str(c.get("provedor")))
        if c.get("status") != "criado" or not c.get("id") or p is None:
            continue
        try:
            p.cancelar(str(c["id"]))
            c["status"] = "cancelado"
        except _ERROS_REDE as exc:
            c["erro_cancelamento"] = str(exc)[:200]
    return calendarios


def horarios_ocupados(inicio: datetime, fim: datetime) -> list[tuple[datetime, datetime]]:
    ocupados: list[tuple[datetime, datetime]] = []
    for p in provedores_configurados():
        try:
            ocupados += p.ocupados(inicio, fim)
        except _ERROS_REDE:
            continue
    return ocupados
