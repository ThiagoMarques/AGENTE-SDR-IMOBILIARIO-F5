"""Agendamento de visitas/reuniões: horários livres, leitura da escolha do lead e registro.

O evento vai para a agenda do corretor (Google/Outlook, se conectados) e o lead
recebe links "adicionar à agenda" + .ics. Sem credenciais, o agendamento continua
registrado no banco e os links funcionam normalmente.
"""
from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from typing import Any

import config
from src.agenda import calendario as cal
from src.agenda import email_convite
from src.imoveis.catalogo_br import CATALOGO_BR

FORMATO = "%d/%m/%Y %H:%M"
HORAS_PADRAO = (10, 14, 16)
EXPEDIENTE = (8, 19)  # primeira e última hora de início aceitas
ANTECEDENCIA_MIN = timedelta(minutes=30)

_DIAS_SEMANA = {"segunda": 0, "terca": 1, "quarta": 2, "quinta": 3, "sexta": 4, "sabado": 5, "domingo": 6}
_NOMES_DIA = ("segunda", "terça", "quarta", "quinta", "sexta", "sábado", "domingo")
_ORDINAIS = {
    "primeiro": 0, "primeira": 0, "1o": 0, "1a": 0, "opcao 1": 0,
    "segundo": 1, "segunda opcao": 1, "2o": 1, "2a": 1, "opcao 2": 1,
    "terceiro": 2, "terceira": 2, "3o": 2, "3a": 2, "opcao 3": 2,
    "ultimo": -1, "ultima": -1,
}
_PALAVRAS_IMOVEL = ("imovel", "apartamento", "apto", "casa", "cobertura", "studio")
_RECUSA = (
    "nenhum", "nenhuma", "nao posso", "nao consigo", "nao da", "nao vai dar",
    "outro dia", "outro horario", "outros horarios", "outra data",
)
_CANCELAR = ("cancelar", "cancela", "desmarcar", "desmarca", "nao vou poder ir", "nao vou mais")
_REMARCAR = ("remarcar", "remarca", "reagendar", "mudar o horario", "trocar o horario", "mudar a visita", "mudar a data", "trocar a data")
_STATUS_ATIVOS = ("agendado",)


def _norm(texto: str) -> str:
    sem_acento = unicodedata.normalize("NFKD", texto.lower()).encode("ascii", "ignore").decode()
    return re.sub(r"\s+", " ", sem_acento).strip()


def agora() -> datetime:
    return datetime.now(cal.fuso())


def formatar(dt: datetime) -> str:
    return dt.astimezone(cal.fuso()).strftime(FORMATO)


def formatar_humano(dt: datetime) -> str:
    local = dt.astimezone(cal.fuso())
    hora = f"{local.hour}h" + (f"{local.minute:02d}" if local.minute else "")
    return f"{_NOMES_DIA[local.weekday()]}, {local:%d/%m} às {hora}"


def formatar_proposta(dt: datetime) -> str:
    """'quarta, 30/09/2026 às 10:00' — legível e reconhecido por horarios_no_texto."""
    local = dt.astimezone(cal.fuso())
    return f"{_NOMES_DIA[local.weekday()]}, {local:%d/%m/%Y} às {local:%H:%M}"


def rotulo_dia(d: date) -> str:
    nome = _NOMES_DIA[d.weekday()]
    artigo = "no" if nome in ("sábado", "domingo") else "na"
    return f"{artigo} {nome} ({d:%d/%m})"


def parse_horario(texto: str) -> datetime | None:
    try:
        return datetime.strptime(texto.strip(), FORMATO).replace(tzinfo=cal.fuso())
    except (ValueError, AttributeError):
        return None


def horarios_no_texto(texto: str) -> list[str]:
    """Horários 'dd/mm/aaaa hh:mm' (ou 'dd/mm/aaaa às hh:mm') que o agente citou numa mensagem."""
    achados = re.findall(r"(\d{2}/\d{2}/\d{4})(?:,? às)? (\d{2}:\d{2})", texto or "")
    return list(dict.fromkeys(f"{d} {h}" for d, h in achados))


def _duracao() -> timedelta:
    return timedelta(minutes=config.AGENDA_DURACAO_MIN)


def _conflita(inicio: datetime, fim: datetime, ocupados: list[tuple[datetime, datetime]]) -> bool:
    return any(inicio < o_fim and o_ini < fim for o_ini, o_fim in ocupados)


def sugerir_horarios(
    qtd: int = 3,
    *,
    dia: date | None = None,
    periodo: str | None = None,
    evitar: list[str] | None = None,
    referencia: datetime | None = None,
) -> list[str]:
    """Janelas livres a partir de amanhã (ou no dia pedido), pulando domingo e horários ocupados."""
    ref = referencia or agora()
    tz = cal.fuso()
    if dia:
        inicio_busca = datetime(dia.year, dia.month, dia.day, tzinfo=tz)
        dias = 1
    else:
        inicio_busca = (ref + timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)
        dias = 7
    fim_busca = inicio_busca + timedelta(days=dias)
    ocupados = cal.horarios_ocupados(inicio_busca, fim_busca)

    horas = list(HORAS_PADRAO)
    if dia:
        horas = [9, 10, 11, 14, 15, 16, 17]
    if periodo == "manha":
        horas = [h for h in horas if h < 12] or [9, 10, 11]
    elif periodo in ("tarde", "noite"):
        horas = [h for h in horas if h >= 12] or [14, 16]

    evitar_set = set(evitar or [])
    slots: list[str] = []
    atual = inicio_busca
    while atual < fim_busca and len(slots) < qtd:
        if atual.weekday() != 6:
            for hora in horas:
                ini = atual.replace(hour=hora)
                texto = formatar(ini)
                if ini < ref + ANTECEDENCIA_MIN or texto in evitar_set:
                    continue
                if _conflita(ini, ini + _duracao(), ocupados):
                    continue
                slots.append(texto)
                if len(slots) >= qtd:
                    break
        atual += timedelta(days=1)
    return slots


# ---------------------------------------------------------------- leitura da escolha

@dataclass
class Escolha:
    inicio: datetime | None = None
    dia: date | None = None
    periodo: str | None = None
    recusou: bool = False
    invalido: str = ""
    explicita: bool = False  # data e hora ditas pelo lead ("amanhã às 10"), sem depender de oferta


def _proximo_dia_semana(ref: date, alvo: int) -> date:
    delta = (alvo - ref.weekday()) % 7
    return ref + timedelta(days=delta or 7)


def _datas(t: str, ref: datetime) -> list[tuple[int, date]]:
    hoje = ref.date()
    achados: list[tuple[int, date]] = []
    for m in re.finditer(r"\b(depois de amanha|amanha|hoje)\b", t):
        offset = {"hoje": 0, "amanha": 1, "depois de amanha": 2}[m.group(1)]
        achados.append((m.start(), hoje + timedelta(days=offset)))
    for m in re.finditer(r"\b(segunda|terca|quarta|quinta|sexta|sabado|domingo)(?:[- ]feira)?\b(?! (?:opcao|op))", t):
        achados.append((m.start(), _proximo_dia_semana(hoje, _DIAS_SEMANA[m.group(1)])))
    for m in re.finditer(r"\b(\d{1,2})/(\d{1,2})(?:/(\d{2,4}))?\b", t):
        dia, mes = int(m.group(1)), int(m.group(2))
        ano = int(m.group(3)) if m.group(3) else hoje.year
        ano += 2000 if ano < 100 else 0
        try:
            d = date(ano, mes, dia)
        except ValueError:
            continue
        if not m.group(3) and d < hoje:
            d = d.replace(year=d.year + 1)
        achados.append((m.start(), d))
    for m in re.finditer(r"\bdia (\d{1,2})\b(?!/)", t):
        dia = int(m.group(1))
        mes, ano = hoje.month, hoje.year
        for _ in range(2):
            try:
                d = date(ano, mes, dia)
            except ValueError:
                d = None
            if d and d >= hoje:
                achados.append((m.start(), d))
                break
            mes, ano = (1, ano + 1) if mes == 12 else (mes + 1, ano)
    return achados


_NAO_HORA = (
    r"(?!\s*(?:quartos?|dorms?|mil|%|anos?|dias?|m2|metros|vagas?|banheiros?|suites?|opc|pessoas?|minutos?)"
    r"|\s+(?:a|ou|e)\s+\d|[/\d:.,])"
)


def _horas(t: str, com_ofertas: bool = True) -> list[tuple[int, int, int]]:
    achados: list[tuple[int, int, int]] = []
    ocupado: list[range] = []

    def _add(m: re.Match[str], h: int, mi: int) -> None:
        if any(m.start() in r for r in ocupado):
            return
        ocupado.append(range(m.start(), m.end()))
        achados.append((m.start(), h, mi))

    for m in re.finditer(r"\bmeio[- ]dia\b", t):
        _add(m, 12, 0)
    for m in re.finditer(r"\b(\d{1,2})(?:\s*(?:h|hs|horas?))?\s+da\s+(manha|tarde|noite)\b", t):
        h = int(m.group(1))
        _add(m, h + 12 if m.group(2) != "manha" and h < 12 else h, 0)
    for m in re.finditer(r"\b(\d{1,2})(?::|h)(\d{2})\b", t):
        _add(m, int(m.group(1)), int(m.group(2)))
    for m in re.finditer(r"\b(\d{1,2})\s*(?:h|hs|horas?)\b", t):
        _add(m, int(m.group(1)), 0)
    # "o de 14" só faz sentido respondendo a uma lista de horários
    prefixos = r"as|a partir das|pelas|umas|das|de" if com_ofertas else r"as|a partir das|pelas|umas"
    for m in re.finditer(rf"\b(?:{prefixos})\s+(\d{{1,2}})\b" + _NAO_HORA, t):
        _add(m, int(m.group(1)), 0)

    normalizados = []
    for pos, h, mi in achados:
        if 1 <= h < EXPEDIENTE[0] - 1 and mi == 0:
            h += 12  # "às 2" = 14h no horário comercial
        if 0 <= h <= 23 and 0 <= mi <= 59:
            normalizados.append((pos, h, mi))
    return normalizados


def _periodo(t: str) -> str | None:
    for chave in ("manha", "tarde", "noite"):
        if re.search(rf"\b(?:de|a|da|pela|na) {chave}\b", t):
            return chave
    return None


def _ordinal(t: str, ofertados: list[str]) -> str | None:
    if not ofertados or any(p in t for p in _PALAVRAS_IMOVEL):
        return None
    for chave in sorted(_ORDINAIS, key=len, reverse=True):
        if re.search(rf"\b{re.escape(chave)}\b", t):
            idx = _ORDINAIS[chave]
            if -len(ofertados) <= idx < len(ofertados):
                return ofertados[idx]
    return None


def validar_horario(dt: datetime, referencia: datetime | None = None) -> str:
    return _validar(dt, referencia or agora())


def _validar(dt: datetime, ref: datetime) -> str:
    if dt < ref + ANTECEDENCIA_MIN:
        return "passado"
    if dt.weekday() == 6:
        return "domingo"
    if not (EXPEDIENTE[0] <= dt.hour <= EXPEDIENTE[1]):
        return "fora_expediente"
    return ""


def interpretar_escolha(
    texto: str,
    ofertados: list[str] | None = None,
    referencia: datetime | None = None,
) -> Escolha | None:
    """Lê 'amanhã às 10', 'o segundo', 'quinta 15h', '30/09 14:00'... None se não houver escolha."""
    ref = referencia or agora()
    tz = cal.fuso()
    t = _norm(texto)
    ofertas = [o for o in (ofertados or []) if parse_horario(o)]
    datas = _datas(t, ref)
    horas = _horas(t, com_ofertas=bool(ofertas))
    periodo = _periodo(t)

    dia = max(datas)[1] if datas else None
    hora = max(horas)[1:] if horas else None

    inicio: datetime | None = None
    if dia and hora:
        inicio = datetime(dia.year, dia.month, dia.day, hora[0], hora[1], tzinfo=tz)
    elif hora:
        mesma_hora = [o for o in ofertas if parse_horario(o).hour == hora[0]]  # type: ignore[union-attr]
        if mesma_hora:
            inicio = parse_horario(mesma_hora[0])
        else:
            base = parse_horario(ofertas[0]).date() if ofertas else (ref + timedelta(days=1)).date()  # type: ignore[union-attr]
            inicio = datetime(base.year, base.month, base.day, hora[0], hora[1], tzinfo=tz)
    elif dia:
        do_dia = [o for o in ofertas if parse_horario(o).date() == dia]  # type: ignore[union-attr]
        if periodo == "manha":
            do_dia = [o for o in do_dia if parse_horario(o).hour < 12]  # type: ignore[union-attr]
        elif periodo:
            do_dia = [o for o in do_dia if parse_horario(o).hour >= 12]  # type: ignore[union-attr]
        if do_dia:
            inicio = parse_horario(do_dia[0])
        else:
            return Escolha(dia=dia, periodo=periodo, invalido="domingo" if dia.weekday() == 6 else "")
    else:
        escolhido = _ordinal(t, ofertas)
        if escolhido:
            inicio = parse_horario(escolhido)
        elif periodo and ofertas:
            filtrados = [o for o in ofertas if (parse_horario(o).hour < 12) == (periodo == "manha")]  # type: ignore[union-attr]
            if filtrados:
                inicio = parse_horario(filtrados[0])
            else:
                return Escolha(periodo=periodo)

    if inicio is None:
        return Escolha(recusou=True) if any(r in t for r in _RECUSA) else None
    return Escolha(inicio=inicio, invalido=_validar(inicio, ref), explicita=bool(dia and hora))


def pede_cancelamento(texto: str) -> bool:
    t = _norm(texto)
    return any(p in t for p in _CANCELAR)


def pede_remarcacao(texto: str) -> bool:
    t = _norm(texto)
    return any(p in t for p in _REMARCAR)


def extrair_email(texto: str) -> str | None:
    m = re.search(r"[\w.+-]+@[\w-]+(?:\.[\w-]+)+", texto or "")
    return m.group(0).lower().rstrip(".") if m else None


# ---------------------------------------------------------------- registro

def obter_imovel(imovel_id: str | None) -> dict[str, Any] | None:
    if not imovel_id:
        return None
    return next((i for i in CATALOGO_BR if i.get("id") == imovel_id), None)


def agendamento_ativo(estado: dict[str, Any]) -> dict[str, Any] | None:
    for ag in reversed(estado.get("agendamentos") or []):
        if ag.get("status", "agendado") in _STATUS_ATIVOS:
            return ag
    return None


def inicio_do(ag: dict[str, Any]) -> datetime | None:
    if ag.get("inicio"):
        try:
            dt = datetime.fromisoformat(str(ag["inicio"]))
            return dt if dt.tzinfo else dt.replace(tzinfo=cal.fuso())
        except ValueError:
            pass
    return parse_horario(str(ag.get("horario") or ""))


def _local(imovel: dict[str, Any] | None) -> str:
    if not imovel:
        return "A combinar com o corretor"
    return f"{imovel.get('endereco')} — {imovel.get('cidade')}/{imovel.get('estado')}"


def _titulo_lead(tipo: str, imovel: dict[str, Any] | None) -> str:
    if tipo == "visita" and imovel:
        return f"Visita: {imovel.get('titulo')} ({config.AGENDA_IMOBILIARIA})"
    return f"Conversa com corretor ({config.AGENDA_IMOBILIARIA})"


def _descricao_lead(imovel: dict[str, Any] | None) -> str:
    linhas = [f"Agendado pelo assistente da {config.AGENDA_IMOBILIARIA}."]
    if imovel:
        linhas.append(f"Imóvel: {imovel.get('id')} — {imovel.get('titulo')}")
    if config.AGENDA_CORRETOR_EMAIL:
        linhas.append(f"Contato do corretor: {config.AGENDA_CORRETOR_EMAIL}")
    linhas.append("Imprevisto? É só responder no chat para remarcar.")
    return "\n".join(linhas)


def _descricao_corretor(estado: dict[str, Any], imovel: dict[str, Any] | None) -> str:
    """Vai para o evento do corretor, que também chega ao lead convidado: só dados do próprio lead."""
    perfil = estado.get("perfil") or {}
    campos = ("intencao", "regiao", "quartos", "faixa_preco", "ticket", "urgencia", "email")
    resumo = ", ".join(f"{c}={perfil[c]}" for c in campos if perfil.get(c) not in (None, ""))
    nome = f" — {perfil['nome']}" if perfil.get("nome") else ""
    linhas = [f"Lead: {estado.get('lead_id')}{nome}"]
    if imovel:
        linhas.append(f"Imóvel: {imovel.get('id')} — {imovel.get('titulo')}")
    if resumo:
        linhas.append(f"Perfil informado: {resumo}")
    linhas.append("Resumo completo no painel do agente SDR.")
    return "\n".join(linhas)


def evento_do_agendamento(ag: dict[str, Any], estado: dict[str, Any] | None = None) -> cal.Evento:
    """Evento do ponto de vista do lead (links e .ics). Com `estado`, versão do corretor."""
    inicio = inicio_do(ag) or agora()
    detalhes = ag.get("detalhes") or {}
    imovel = obter_imovel(ag.get("imovel_id"))
    tipo = str(ag.get("tipo") or "visita")
    duracao = timedelta(minutes=int(detalhes.get("duracao_min") or config.AGENDA_DURACAO_MIN))
    ev = cal.Evento(
        titulo=_titulo_lead(tipo, imovel),
        inicio=inicio,
        fim=inicio + duracao,
        descricao=_descricao_corretor(estado, imovel) if estado is not None else _descricao_lead(imovel),
        local=_local(imovel),
        convidados=list(detalhes.get("convidados") or []),
    )
    if detalhes.get("uid"):
        ev.uid = str(detalhes["uid"])
    return ev


def registrar_agendamento(
    estado: dict[str, Any],
    *,
    horario: str,
    tipo: str = "reuniao",
    imovel_id: str | None = None,
    inicio: datetime | None = None,
    detalhes: dict[str, Any] | None = None,
) -> dict[str, Any]:
    item: dict[str, Any] = {
        "tipo": tipo,
        "horario": horario,
        "status": "agendado",
        "imovel_id": imovel_id,
        "inicio": (inicio or parse_horario(horario) or agora()).isoformat(),
        "detalhes": detalhes or {},
    }
    estado.setdefault("agendamentos", []).append(item)
    return item


def agendar(
    estado: dict[str, Any],
    inicio: datetime,
    *,
    tipo: str = "visita",
    imovel_id: str | None = None,
    email: str | None = None,
) -> dict[str, Any]:
    """Registra e cria o evento nas agendas conectadas (convidando o lead, se houver e-mail)."""
    imovel = obter_imovel(imovel_id)
    if tipo == "visita" and not imovel:
        tipo = "reuniao"
    ev = cal.Evento(
        titulo=_titulo_lead(tipo, imovel),
        inicio=inicio,
        fim=inicio + _duracao(),
        descricao=_descricao_corretor(estado, imovel),
        local=_local(imovel),
        convidados=[email] if email else [],
    )
    detalhes = {
        "uid": ev.uid,
        "duracao_min": config.AGENDA_DURACAO_MIN,
        "convidados": ev.convidados,
        "calendarios": cal.criar_nos_provedores(ev),
    }
    item = registrar_agendamento(
        estado,
        horario=formatar(inicio),
        tipo=tipo,
        imovel_id=imovel["id"] if imovel else None,
        inicio=inicio,
        detalhes=detalhes,
    )
    enviar_convite_email(estado, item)
    return item


def _agenda_ja_convidou(detalhes: dict[str, Any]) -> bool:
    return any(
        c.get("status") == "criado" and not c.get("erro_convite")
        for c in detalhes.get("calendarios") or []
    )


def convite_enviado(ag: dict[str, Any]) -> bool:
    """O lead recebeu convite (pela agenda do corretor ou por e-mail transacional)?"""
    detalhes = ag.get("detalhes") or {}
    if not detalhes.get("convidados"):
        return False
    return _agenda_ja_convidou(detalhes) or (detalhes.get("email_convite") or {}).get("status") == "enviado"


def enviar_convite_email(estado: dict[str, Any], ag: dict[str, Any], *, metodo: str = "REQUEST") -> None:
    """E-mail com .ics de convite (ou cancelamento). Pula se a agenda do corretor já convidou."""
    detalhes = ag.setdefault("detalhes", {})
    convidados = list(detalhes.get("convidados") or [])
    if not convidados or not email_convite.configurado():
        return
    if metodo == "REQUEST" and _agenda_ja_convidou(detalhes):
        return
    if metodo == "CANCEL" and (detalhes.get("email_convite") or {}).get("status") != "enviado":
        return
    nome = (estado.get("perfil") or {}).get("nome")
    sequencia = int(detalhes.get("sequencia") or 0) + (1 if metodo == "CANCEL" else 0)
    ev = evento_do_agendamento(ag)
    ics = cal.gerar_ics(
        ev,
        metodo=metodo,
        organizador=config.AGENDA_CORRETOR_EMAIL or email_convite.remetente_email(),
        nomes={convidados[0]: nome} if nome else None,
        sequencia=sequencia,
    )
    assunto, html_corpo, texto = email_convite.montar(
        nome=nome,
        titulo=ev.titulo,
        quando=formatar_humano(ev.inicio),
        local=ev.local,
        links=cal.links(ev),
        cancelado=metodo == "CANCEL",
    )
    r = email_convite.enviar(convidados, assunto=assunto, html_corpo=html_corpo, texto=texto, ics=ics, metodo=metodo)
    detalhes["email_convite"] = {**r, "metodo": metodo, "em": datetime.now(timezone.utc).isoformat()}
    detalhes["sequencia"] = sequencia


def cancelar(estado: dict[str, Any], *, status: str = "cancelado") -> dict[str, Any] | None:
    ag = agendamento_ativo(estado)
    if not ag:
        return None
    detalhes = ag.setdefault("detalhes", {})
    detalhes["calendarios"] = cal.cancelar_nos_provedores(list(detalhes.get("calendarios") or []))
    enviar_convite_email(estado, ag, metodo="CANCEL")
    ag["status"] = status
    return ag


def remarcar(estado: dict[str, Any], inicio: datetime) -> dict[str, Any]:
    anterior = cancelar(estado, status="remarcado") or {}
    convidados = (anterior.get("detalhes") or {}).get("convidados") or []
    return agendar(
        estado,
        inicio,
        tipo=str(anterior.get("tipo") or "visita"),
        imovel_id=anterior.get("imovel_id"),
        email=convidados[0] if convidados else (estado.get("perfil") or {}).get("email"),
    )


def convidar_lead(estado: dict[str, Any], email: str) -> dict[str, Any] | None:
    ag = agendamento_ativo(estado)
    if not ag:
        return None
    detalhes = ag.setdefault("detalhes", {})
    convidados = list(detalhes.get("convidados") or [])
    if email in convidados:
        return ag
    detalhes["convidados"] = convidados + [email]
    detalhes["calendarios"] = cal.convidar(list(detalhes.get("calendarios") or []), [email])
    enviar_convite_email(estado, ag)
    return ag


def publico(ag: dict[str, Any], lead_id: str, indice: int) -> dict[str, Any]:
    """Agendamento pronto para a API/front: links Google/Outlook e caminho do .ics."""
    detalhes = ag.get("detalhes") or {}
    ev = evento_do_agendamento(ag)
    links = cal.links(ev)
    links["ics"] = f"/leads/{lead_id}/agendamentos/{indice}/convite.ics"
    imovel = obter_imovel(ag.get("imovel_id"))
    return {
        "indice": indice,
        "tipo": ag.get("tipo"),
        "horario": ag.get("horario"),
        "inicio": ag.get("inicio"),
        "quando": formatar_humano(ev.inicio),
        "status": ag.get("status", "agendado"),
        "imovel_id": ag.get("imovel_id"),
        "imovel_titulo": imovel.get("titulo") if imovel else None,
        "local": ev.local,
        "convidados": detalhes.get("convidados") or [],
        "convite_enviado": convite_enviado(ag),
        "calendarios": [
            {k: c.get(k) for k in ("provedor", "status", "link")}
            for c in detalhes.get("calendarios") or []
        ],
        "links": links,
    }


def publicos(estado: dict[str, Any]) -> list[dict[str, Any]]:
    lead_id = str(estado.get("lead_id") or "")
    return [publico(ag, lead_id, i) for i, ag in enumerate(estado.get("agendamentos") or [])]
