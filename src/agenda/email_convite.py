"""Convite de visita por e-mail via serviço transacional (Resend ou SendGrid).

Cobre o caso em que a agenda do corretor não está conectada (ou não convidou o
lead): o e-mail leva um .ics com METHOD:REQUEST, que Gmail e Outlook mostram
como convite com Sim/Não/Talvez e colocam na agenda do lead. Remarcação e
cancelamento mandam METHOD:CANCEL com o mesmo UID. Nunca levanta exceção.
"""
from __future__ import annotations

import base64
import html
from email.utils import parseaddr
from typing import Any

import requests

import config

RESEND_URL = "https://api.resend.com/emails"
SENDGRID_URL = "https://api.sendgrid.com/v3/mail/send"


def provedor() -> str | None:
    chaves = {"resend": config.RESEND_API_KEY, "sendgrid": config.SENDGRID_API_KEY}
    if config.EMAIL_PROVIDER:
        return config.EMAIL_PROVIDER if chaves.get(config.EMAIL_PROVIDER) else None
    return next((nome for nome, chave in chaves.items() if chave), None)


def configurado() -> bool:
    return bool(provedor() and config.EMAIL_FROM)


def remetente_email() -> str:
    return parseaddr(config.EMAIL_FROM)[1]


def montar(
    *,
    nome: str | None,
    titulo: str,
    quando: str,
    local: str,
    links: dict[str, str],
    cancelado: bool = False,
) -> tuple[str, str, str]:
    """(assunto, html, texto) só com informação voltada ao cliente."""
    saudacao = f"Olá, {nome.split()[0]}!" if nome else "Olá!"
    if cancelado:
        assunto = f"Cancelado: {titulo} ({quando})"
        texto = f"{saudacao}\n\nSua visita de {quando} foi cancelada. Quando quiser remarcar, é só responder no chat."
    else:
        assunto = f"Convite: {titulo} ({quando})"
        texto = (
            f"{saudacao}\n\nSua visita está marcada para {quando}.\nLocal: {local}\n\n"
            f"Adicionar à agenda:\nGoogle: {links.get('google', '')}\nOutlook: {links.get('outlook', '')}\n\n"
            "Imprevisto? É só responder no chat para remarcar."
        )
    texto += (
        f"\n\n—\n{config.AGENDA_IMOBILIARIA}. Você recebeu este e-mail porque pediu o "
        "agendamento no nosso chat; usamos seu contato só para esta visita."
    )
    corpo = "".join(f"<p>{html.escape(p).replace(chr(10), '<br>')}</p>" for p in texto.split("\n\n"))
    return assunto, f'<div style="font-family:Arial,sans-serif;font-size:14px;color:#1e293b">{corpo}</div>', texto


def enviar(
    para: list[str],
    *,
    assunto: str,
    html_corpo: str,
    texto: str,
    ics: str,
    metodo: str,
) -> dict[str, Any]:
    prov = provedor()
    if not prov or not config.EMAIL_FROM or not para:
        return {"status": "desabilitado"}
    anexo = base64.b64encode(ics.encode("utf-8")).decode()
    tipo = f'text/calendar; charset="utf-8"; method={metodo}'
    try:
        if prov == "resend":
            resp = requests.post(
                RESEND_URL,
                headers={"Authorization": f"Bearer {config.RESEND_API_KEY}"},
                json={
                    "from": config.EMAIL_FROM,
                    "to": para,
                    "subject": assunto,
                    "html": html_corpo,
                    "text": texto,
                    "attachments": [{"filename": "convite.ics", "content": anexo, "content_type": tipo}],
                },
                timeout=config.AGENDA_TIMEOUT,
            )
        else:
            nome, email = parseaddr(config.EMAIL_FROM)
            resp = requests.post(
                SENDGRID_URL,
                headers={"Authorization": f"Bearer {config.SENDGRID_API_KEY}"},
                json={
                    "personalizations": [{"to": [{"email": e} for e in para]}],
                    "from": {"email": email, **({"name": nome} if nome else {})},
                    "subject": assunto,
                    "content": [
                        {"type": "text/plain", "value": texto},
                        {"type": "text/html", "value": html_corpo},
                    ],
                    "attachments": [
                        {"content": anexo, "type": tipo, "filename": "convite.ics", "disposition": "attachment"}
                    ],
                },
                timeout=config.AGENDA_TIMEOUT,
            )
        if resp.status_code >= 400:
            return {"status": "erro", "provedor": prov, "erro": f"HTTP {resp.status_code}: {resp.text[:200]}"}
        dados = resp.json() if resp.content else {}
        return {"status": "enviado", "provedor": prov, "id": dados.get("id") or resp.headers.get("X-Message-Id")}
    except (requests.RequestException, ValueError) as exc:
        return {"status": "erro", "provedor": prov, "erro": str(exc)[:200]}
