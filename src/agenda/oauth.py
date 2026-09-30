"""Autorização única da agenda do corretor (python main.py --agenda-auth google|outlook).

Google: OAuth "app para computador" com redirect loopback + PKCE.
Microsoft: device code flow (cliente público), sem precisar de servidor HTTP.
O refresh token vai para dados/agenda_tokens.json (fora do git).
"""
from __future__ import annotations

import base64
import hashlib
import http.server
import secrets
import threading
import time
import webbrowser
from urllib.parse import parse_qs, urlencode, urlparse

import requests

import config
from src.agenda.calendario import (
    GOOGLE_ESCOPOS,
    GOOGLE_TOKEN_URL,
    MS_ESCOPOS,
    ErroAgenda,
    ms_token_url,
    salvar_refresh_token,
)

GOOGLE_AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"


def _pkce() -> tuple[str, str]:
    verifier = secrets.token_urlsafe(64)
    challenge = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).rstrip(b"=").decode()
    return verifier, challenge


def autorizar_google(timeout_s: int = 300) -> None:
    if not (config.GOOGLE_CLIENT_ID and config.GOOGLE_CLIENT_SECRET):
        raise ErroAgenda("Defina GOOGLE_CLIENT_ID e GOOGLE_CLIENT_SECRET no .env.")

    recebido: dict[str, str] = {}

    class _Handler(http.server.BaseHTTPRequestHandler):
        def do_GET(self) -> None:  # noqa: N802
            qs = parse_qs(urlparse(self.path).query)
            recebido.update({k: v[0] for k, v in qs.items()})
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.end_headers()
            self.wfile.write("<h3>Agenda autorizada. Pode fechar esta aba.</h3>".encode())

        def log_message(self, *args: object) -> None:
            pass

    servidor = http.server.HTTPServer(("127.0.0.1", 0), _Handler)
    redirect = f"http://127.0.0.1:{servidor.server_port}"
    verifier, challenge = _pkce()
    estado = secrets.token_urlsafe(16)
    url = GOOGLE_AUTH_URL + "?" + urlencode(
        {
            "client_id": config.GOOGLE_CLIENT_ID,
            "redirect_uri": redirect,
            "response_type": "code",
            "scope": GOOGLE_ESCOPOS,
            "access_type": "offline",
            "prompt": "consent",
            "code_challenge": challenge,
            "code_challenge_method": "S256",
            "state": estado,
        }
    )

    thread = threading.Thread(target=servidor.handle_request, daemon=True)
    thread.start()
    print("Abrindo o navegador para autorizar a Google Agenda...\nSe não abrir, acesse:\n" + url)
    webbrowser.open(url)
    thread.join(timeout_s)
    servidor.server_close()

    if recebido.get("state") != estado or "code" not in recebido:
        raise ErroAgenda(f"Autorização Google não concluída: {recebido.get('error', 'sem resposta')}")

    resp = requests.post(
        GOOGLE_TOKEN_URL,
        data={
            "client_id": config.GOOGLE_CLIENT_ID,
            "client_secret": config.GOOGLE_CLIENT_SECRET,
            "code": recebido["code"],
            "code_verifier": verifier,
            "grant_type": "authorization_code",
            "redirect_uri": redirect,
        },
        timeout=config.AGENDA_TIMEOUT,
    )
    dados = resp.json()
    if resp.status_code >= 400 or not dados.get("refresh_token"):
        raise ErroAgenda(f"Google não devolveu refresh token: {dados}")
    salvar_refresh_token("google", dados["refresh_token"])
    print(f"Google Agenda conectada. Token salvo em {config.AGENDA_TOKENS}.")


def autorizar_outlook() -> None:
    if not config.MS_CLIENT_ID:
        raise ErroAgenda("Defina MS_CLIENT_ID no .env (app registrado no Microsoft Entra).")

    base = f"https://login.microsoftonline.com/{config.MS_TENANT}/oauth2/v2.0"
    resp = requests.post(
        f"{base}/devicecode",
        data={"client_id": config.MS_CLIENT_ID, "scope": MS_ESCOPOS},
        timeout=config.AGENDA_TIMEOUT,
    )
    fluxo = resp.json()
    if resp.status_code >= 400 or "device_code" not in fluxo:
        raise ErroAgenda(f"Falha ao iniciar device code: {fluxo}")
    print(fluxo.get("message") or f"Acesse {fluxo['verification_uri']} e digite {fluxo['user_code']}")

    intervalo = int(fluxo.get("interval", 5))
    limite = time.time() + int(fluxo.get("expires_in", 900))
    while time.time() < limite:
        time.sleep(intervalo)
        tok = requests.post(
            ms_token_url(),
            data={
                "client_id": config.MS_CLIENT_ID,
                "grant_type": "urn:ietf:params:oauth:grant-type:device_code",
                "device_code": fluxo["device_code"],
            },
            timeout=config.AGENDA_TIMEOUT,
        ).json()
        erro = tok.get("error")
        if erro == "authorization_pending":
            continue
        if erro == "slow_down":
            intervalo += 5
            continue
        if erro:
            raise ErroAgenda(f"Autorização Microsoft falhou: {tok.get('error_description', erro)}")
        if not tok.get("refresh_token"):
            raise ErroAgenda("Microsoft não devolveu refresh token (confira o escopo offline_access).")
        salvar_refresh_token("outlook", tok["refresh_token"])
        print(f"Outlook conectado. Token salvo em {config.AGENDA_TOKENS}.")
        return
    raise ErroAgenda("Código expirou antes da autorização.")
