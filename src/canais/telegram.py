"""Canal Telegram — demonstração com fins educativos.

Mostra que o agente não depende do canal: cada mensagem recebida pelo bot vira
uma chamada a processar_mensagem, a mesma do chat web, e o lead aparece na
inbox e no dashboard do corretor como TG-<chat_id>. As mensagens chegam por
long polling (getUpdates), então o bot roda na máquina local sem URL pública.
Os horários de visita viram botões e a visita marcada segue com o .ics e os
atalhos de agenda.

O WhatsApp entra pelo mesmo caminho: muda só o formato da mensagem recebida
(webhook da WhatsApp Cloud API da Meta ou do Twilio) e a chamada de envio.
Lá valem regras que o Telegram não tem: texto livre só até 24 h depois da
última mensagem do lead (o follow-up fora da janela exige modelo aprovado),
verificação da empresa na Meta e webhook público com HTTPS.
"""
from __future__ import annotations

import time
from typing import Any

import requests

import config

API = "https://api.telegram.org/bot{token}/{metodo}"
LIMITE_TEXTO = 4096
ESPERA_POLLING = 30

AVISO_DEMO = (
    "Este é um canal de demonstração do Tech Challenge FIAP, com fins educativos. "
    "Os imóveis são fictícios."
)
SO_TEXTO = "Por aqui eu só consigo ler texto. Me conta por escrito o que você procura?"


class ErroTelegram(RuntimeError):
    pass


def lead_id(chat_id: int | str) -> str:
    return f"TG-{chat_id}"


def dividir(texto: str, limite: int = LIMITE_TEXTO) -> list[str]:
    """Quebra por parágrafo para respeitar o limite de caracteres por mensagem."""
    partes: list[str] = []
    atual = ""
    for paragrafo in texto.split("\n\n"):
        candidato = f"{atual}\n\n{paragrafo}" if atual else paragrafo
        if len(candidato) <= limite:
            atual = candidato
            continue
        if atual:
            partes.append(atual)
        while len(paragrafo) > limite:
            partes.append(paragrafo[:limite])
            paragrafo = paragrafo[limite:]
        atual = paragrafo
    if atual:
        partes.append(atual)
    return partes or [""]


class Telegram:
    """Cliente mínimo da Bot API (só o que o canal usa)."""

    def __init__(self, token: str) -> None:
        self.token = token

    def _chamar(
        self,
        metodo: str,
        payload: dict[str, Any] | None = None,
        *,
        arquivos: dict[str, Any] | None = None,
        timeout: float = 10.0,
    ) -> Any:
        url = API.format(token=self.token, metodo=metodo)
        try:
            if arquivos:
                resp = requests.post(url, data=payload or {}, files=arquivos, timeout=timeout)
            else:
                resp = requests.post(url, json=payload or {}, timeout=timeout)
            corpo = resp.json()
        except (requests.RequestException, ValueError) as exc:
            # O token faz parte da URL e não pode aparecer em log.
            raise ErroTelegram(str(exc).replace(self.token, "***")) from exc
        if not corpo.get("ok"):
            raise ErroTelegram(str(corpo.get("description") or f"HTTP {resp.status_code}"))
        return corpo.get("result")

    def quem_sou(self) -> dict[str, Any]:
        return self._chamar("getMe")

    def atualizacoes(self, offset: int | None) -> list[dict[str, Any]]:
        payload: dict[str, Any] = {
            "timeout": ESPERA_POLLING,
            "allowed_updates": ["message", "callback_query"],
        }
        if offset is not None:
            payload["offset"] = offset
        return self._chamar("getUpdates", payload, timeout=ESPERA_POLLING + 5)

    def enviar_texto(
        self,
        chat_id: int | str,
        texto: str,
        *,
        botoes: list[list[dict[str, str]]] | None = None,
    ) -> None:
        partes = dividir(texto)
        for i, parte in enumerate(partes):
            payload: dict[str, Any] = {"chat_id": chat_id, "text": parte}
            if botoes and i == len(partes) - 1:
                payload["reply_markup"] = {"inline_keyboard": botoes}
            self._chamar("sendMessage", payload)

    def enviar_arquivo(self, chat_id: int | str, nome: str, conteudo: bytes, legenda: str = "") -> None:
        self._chamar(
            "sendDocument",
            {"chat_id": str(chat_id), "caption": legenda},
            arquivos={"document": (nome, conteudo, "text/calendar")},
            timeout=20.0,
        )

    def responder_botao(self, callback_id: str) -> None:
        self._chamar("answerCallbackQuery", {"callback_query_id": callback_id})

    def digitando(self, chat_id: int | str) -> None:
        self._chamar("sendChatAction", {"chat_id": chat_id, "action": "typing"})


def botoes_de_horario(resposta: str) -> list[list[dict[str, str]]]:
    """Um botão por horário oferecido; o clique devolve o horário como mensagem do lead."""
    from src.agenda.scheduler import formatar_humano, horarios_no_texto, parse_horario

    horarios = horarios_no_texto(resposta)
    botoes = []
    for horario in horarios:
        inicio = parse_horario(horario)
        rotulo = formatar_humano(inicio) if inicio else horario
        if len(horarios) == 1:
            rotulo = f"Reservar {rotulo}"
        botoes.append([{"text": rotulo, "callback_data": horario}])
    return botoes


def _visita_ativa(lead: str) -> dict[str, Any] | None:
    from src.agenda.scheduler import agendamento_ativo
    from src.memoria import conversa as memoria

    return agendamento_ativo(memoria.carregar(lead))


def _chave(ag: dict[str, Any] | None) -> tuple[Any, ...] | None:
    return (ag.get("inicio") or ag.get("horario"), ag.get("imovel_id")) if ag else None


def _enviar_convite(bot: Telegram, chat_id: int | str, ag: dict[str, Any]) -> None:
    from src.agenda import calendario as cal
    from src.agenda.scheduler import evento_do_agendamento

    ev = evento_do_agendamento(ag)
    links = cal.links(ev)
    bot.enviar_texto(
        chat_id,
        "Atalhos para salvar a visita na sua agenda:",
        botoes=[
            [{"text": "Google Agenda", "url": links["google"]}],
            [{"text": "Outlook", "url": links["outlook"]}],
        ],
    )
    bot.enviar_arquivo(chat_id, "visita.ics", cal.gerar_ics(ev).encode("utf-8"), "Convite da visita (.ics)")


def tratar(atualizacao: dict[str, Any], bot: Telegram) -> None:
    """Leva uma mensagem (ou clique em botão) ao agente e devolve a resposta no chat."""
    from src.agente.sdr import processar_mensagem

    clique = atualizacao.get("callback_query")
    if clique:
        bot.responder_botao(clique["id"])
        mensagem = clique.get("message") or {}
        texto = str(clique.get("data") or "")
    else:
        mensagem = atualizacao.get("message") or {}
        texto = (mensagem.get("text") or "").strip()

    chat = mensagem.get("chat") or {}
    if chat.get("id") is None or chat.get("type", "private") != "private":
        return
    chat_id = chat["id"]
    if not texto:
        bot.enviar_texto(chat_id, SO_TEXTO)
        return
    if texto.startswith("/start"):
        bot.enviar_texto(chat_id, AVISO_DEMO)
        texto = "Oi"

    lead = lead_id(chat_id)
    antes = _chave(_visita_ativa(lead))
    bot.digitando(chat_id)
    saida = processar_mensagem(lead, texto)
    resposta = saida["resposta"]
    bot.enviar_texto(chat_id, resposta, botoes=botoes_de_horario(resposta) or None)

    visita = _visita_ativa(lead)
    if visita and _chave(visita) != antes:
        _enviar_convite(bot, chat_id, visita)


def rodar(token: str | None = None) -> None:
    token = token or config.TELEGRAM_BOT_TOKEN
    if not token:
        raise SystemExit("Defina TELEGRAM_BOT_TOKEN no .env (crie o bot com o @BotFather no Telegram).")

    from src.db.session import init_db

    init_db()
    bot = Telegram(token)
    eu = bot.quem_sou()
    print(f"Bot @{eu.get('username')} ouvindo mensagens (fins educativos). Ctrl+C para parar.")

    offset: int | None = None
    while True:
        try:
            atualizacoes = bot.atualizacoes(offset)
        except ErroTelegram as exc:
            print(f"Falha ao buscar mensagens: {exc}. Nova tentativa em 5 s.")
            time.sleep(5)
            continue
        for atualizacao in atualizacoes:
            offset = int(atualizacao["update_id"]) + 1
            try:
                tratar(atualizacao, bot)
            except Exception as exc:  # uma mensagem com erro não derruba o bot
                print(f"Erro ao tratar a atualização {atualizacao.get('update_id')}: {exc}")
