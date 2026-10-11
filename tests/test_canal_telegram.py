"""Canal Telegram (demonstração educativa): bot falso, sem rede."""
from datetime import datetime

import pytest

from src.agenda import calendario as cal
from src.agenda import scheduler
from src.canais import telegram
from src.memoria import conversa as memoria

REF = datetime(2026, 9, 29, 15, 0, tzinfo=cal.fuso())  # terça-feira
CHAT = 4242


@pytest.fixture(autouse=True)
def relogio_fixo(monkeypatch):
    monkeypatch.setattr(scheduler, "agora", lambda: REF)


class BotFalso(telegram.Telegram):
    def __init__(self):
        super().__init__("TOKEN-SECRETO")
        self.chamadas: list[tuple[str, dict, dict | None]] = []

    def _chamar(self, metodo, payload=None, *, arquivos=None, timeout=10.0):
        self.chamadas.append((metodo, payload or {}, arquivos))
        return True

    def enviados(self, metodo="sendMessage"):
        return [p for m, p, _ in self.chamadas if m == metodo]


def texto(chat=CHAT, msg="", tipo="private"):
    return {"update_id": 1, "message": {"chat": {"id": chat, "type": tipo}, "text": msg}}


def clique(dado, chat=CHAT):
    return {"update_id": 2, "callback_query": {"id": "cb-1", "data": dado, "message": {"chat": {"id": chat, "type": "private"}}}}


def test_mensagem_vira_lead_do_agente_com_prefixo_tg():
    bot = BotFalso()
    telegram.tratar(texto(msg="Quero comprar apartamento em Moema"), bot)

    [enviada] = bot.enviados()
    assert enviada["chat_id"] == CHAT and "como posso te chamar" in enviada["text"].lower()
    assert memoria.carregar("TG-4242")["perfil"]["intencao"] == "compra"


def test_start_avisa_que_e_demonstracao_e_cumprimenta():
    bot = BotFalso()
    telegram.tratar(texto(msg="/start"), bot)

    aviso, saudacao = bot.enviados()
    assert "fins educativos" in aviso["text"]
    assert saudacao["text"]


def test_horarios_viram_botoes_e_o_clique_agenda_com_ics():
    bot = BotFalso()
    for msg in ("Quero comprar apartamento em Moema", "Ana", "3 quartos, até 1,5 milhão, urgente essa semana"):
        telegram.tratar(texto(msg=msg), bot)

    oferta = bot.enviados()[-1]
    botoes = [linha[0] for linha in oferta["reply_markup"]["inline_keyboard"]]
    assert botoes[0] == {"text": "quarta, 30/09 às 10h", "callback_data": "30/09/2026 10:00"}
    assert len(botoes) == 3

    bot.chamadas.clear()
    telegram.tratar(clique(botoes[1]["callback_data"]), bot)

    assert bot.chamadas[0][0] == "answerCallbackQuery"
    textos = [p["text"] for p in bot.enviados()]
    assert textos[0].startswith("Fechado, Ana!") and "30/09 às 14h" in textos[0]
    atalhos = bot.enviados()[1]["reply_markup"]["inline_keyboard"]
    assert [b[0]["text"] for b in atalhos] == ["Google Agenda", "Outlook"]

    [(_, payload, arquivos)] = [c for c in bot.chamadas if c[0] == "sendDocument"]
    nome, conteudo, _ = arquivos["document"]
    assert payload["chat_id"] == str(CHAT) and nome == "visita.ics"
    assert b"BEGIN:VCALENDAR" in conteudo and b"DTSTART:20260930T170000Z" in conteudo


def test_proposta_de_um_horario_vira_botao_de_reservar():
    bot = BotFalso()
    for msg in ("Quero comprar apartamento em Moema", "Ana", "3 quartos, até 1,5 milhão, urgente essa semana",
                "ana@exemplo.com"):
        telegram.tratar(texto(msg=msg), bot)

    [[botao]] = bot.enviados()[-1]["reply_markup"]["inline_keyboard"]
    assert botao == {"text": "Reservar quarta, 30/09 às 10h", "callback_data": "30/09/2026 10:00"}

    bot.chamadas.clear()
    telegram.tratar(clique(botao["callback_data"]), bot)
    assert bot.enviados()[0]["text"].startswith("Fechado, Ana! Visita marcada para quarta, 30/09 às 10h.")
    assert len(bot.enviados("sendDocument")) == 1


def test_convite_nao_e_reenviado_se_a_visita_nao_mudou():
    bot = BotFalso()
    for msg in ("Quero comprar apartamento em Moema", "Ana", "3 quartos, até 1,5 milhão, urgente essa semana"):
        telegram.tratar(texto(msg=msg), bot)
    telegram.tratar(clique("30/09/2026 10:00"), bot)
    bot.chamadas.clear()

    telegram.tratar(texto(msg="aceita pet?"), bot)
    assert bot.enviados("sendDocument") == []


def test_mensagem_sem_texto_pede_texto_e_nao_chama_o_agente():
    bot = BotFalso()
    telegram.tratar({"update_id": 3, "message": {"chat": {"id": CHAT, "type": "private"}, "sticker": {}}}, bot)

    [enviada] = bot.enviados()
    assert enviada["text"] == telegram.SO_TEXTO
    assert memoria.carregar("TG-4242")["mensagens"] == []


def test_grupo_e_ignorado():
    bot = BotFalso()
    telegram.tratar(texto(msg="Quero alugar", tipo="group"), bot)
    assert bot.chamadas == []


def test_texto_longo_e_dividido_e_botoes_vao_na_ultima_parte():
    bot = BotFalso()
    longo = "\n\n".join(["a" * 3000, "b" * 3000])
    bot.enviar_texto(CHAT, longo, botoes=[[{"text": "x", "callback_data": "x"}]])

    primeira, segunda = bot.enviados()
    assert primeira["text"] == "a" * 3000 and "reply_markup" not in primeira
    assert segunda["text"] == "b" * 3000 and "reply_markup" in segunda
    assert all(len(p) <= telegram.LIMITE_TEXTO for p in telegram.dividir("c" * 9000))


def test_erro_de_rede_nao_expoe_o_token(monkeypatch):
    def falha(*args, **kwargs):
        raise telegram.requests.ConnectionError("falhou https://api.telegram.org/botTOKEN-SECRETO/getMe")

    monkeypatch.setattr(telegram.requests, "post", falha)
    with pytest.raises(telegram.ErroTelegram) as exc:
        telegram.Telegram("TOKEN-SECRETO").quem_sou()
    assert "TOKEN-SECRETO" not in str(exc.value)
