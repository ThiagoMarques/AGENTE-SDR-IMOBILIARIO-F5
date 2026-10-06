"""Agente SDR: intenção, qualificação, busca de imóveis e resposta (LLM opcional)."""
from __future__ import annotations

import json
import re
from datetime import timedelta
from typing import Any

import config
from src.agenda.calendario import horarios_ocupados
from src.agenda.scheduler import (
    Escolha,
    agendamento_ativo,
    agendar,
    cancelar,
    convidar_lead,
    convite_enviado,
    extrair_email,
    formatar_humano,
    formatar_proposta,
    horarios_no_texto,
    inicio_do,
    interpretar_escolha,
    obter_imovel,
    parse_horario,
    pede_cancelamento,
    pede_remarcacao,
    publico,
    remarcar,
    rotulo_dia,
    sugerir_horarios,
    validar_horario,
)
from src.qualificacao.contato import afirmativo, extrair_nome, negativo, sugerir_correcao_email
from src.imoveis.catalogo import buscar_resultado, formatar_imovel
from src.memoria import conversa as memoria
from src.crm.cliente import (
    EVENTO_AGENDADO,
    EVENTO_CANCELADO,
    EVENTO_REMARCADO,
    sincronizar as sincronizar_crm,
)
from src.qualificacao.extracao_llm import extrair_perfil_llm, mesclar_perfil
from src.qualificacao.lead import campos_faltantes, proxima_pergunta, score_estado
from src.resumo.corretor import montar_resumo

_REGIOES = {
    "zona sul": "zona sul",
    "zona oeste": "zona oeste",
    "zona norte": "zona norte",
    "zona leste": "zona leste",
    "asa sul": "asa sul",
    "asa norte": "asa norte",
    "lago sul": "lago sul",
    "lago norte": "lago norte",
    "centro": "centro",
    "moema": "moema",
    "pinheiros": "pinheiros",
    "vila mariana": "vila mariana",
    "itaim": "itaim bibi",
    "brooklin": "brooklin",
    "jardins": "jardins",
}

# Temas fora do escopo SDR (evitar “anomalias” / respostas desalinhadas)
_FORA_ESCOPO = (
    "previsão do tempo",
    "previsao do tempo",
    "previsão",
    "previsao",
    "clima",
    "temperatura",
    "meteorolog",
    "futebol",
    "jogo do",
    "política",
    "politica",
    "eleição",
    "eleicao",
    "piada",
    "receita de",
    "horóscopo",
    "horoscopo",
    "bitcoin",
    "criptomoeda",
    "chatgpt",
    "quem é você",
    "quem e voce",
)

_IMOB_HINT = (
    "imóvel",
    "imovel",
    "apartamento",
    "apto",
    "casa",
    "cobertura",
    "alugar",
    "aluguel",
    "comprar",
    "compra",
    "investir",
    "investimento",
    "quarto",
    "quartos",
    "metragem",
    "visita",
    "corretor",
    "orçamento",
    "orcamento",
    "bairro",
    "região",
    "regiao",
)


def mensagem_fora_de_escopo(texto: str, perfil: dict[str, Any] | None = None) -> bool:
    """True quando a mensagem não é sobre imóveis / qualificação."""
    t = texto.lower().strip()
    if not t:
        return False
    if _so_saudacao(texto) or _quer_agendar(texto):
        return False
    # Respostas curtas de funil (números, mil, urgência)
    if re.fullmatch(r"[\d\s\.r$milatéateqtosquartos]*", t.replace("ú", "u")):
        return False
    if re.fullmatch(r"(curto|médio|medio|longo|alta|baixa|sem pressa)", t):
        return False
    if detectar_intencao(texto, perfil):
        return False
    if any(r in t for r in _REGIOES):
        return False
    if any(h in t for h in _IMOB_HINT):
        return False
    if any(p in t for p in _FORA_ESCOPO):
        return True
    # Pergunta genérica sem sinal imobiliário
    if "?" in t or t.startswith(("fale ", "me fala", "me diga", "o que ", "como ", "por que", "porque")):
        return True
    return False


def pode_sugerir_imoveis(perfil: dict[str, Any]) -> bool:
    """Só sugere catálogo com intenção + ao menos um filtro concreto."""
    if not perfil.get("intencao"):
        return False
    return (
        bool(perfil.get("regiao"))
        or perfil.get("quartos") is not None
        or perfil.get("faixa_preco") is not None
        or perfil.get("ticket") is not None
    )


def detectar_intencao(texto: str, perfil_atual: dict[str, Any] | None = None) -> str | None:
    t = texto.lower()
    if any(p in t for p in ("investir", "investimento", "renda", "yield", "retorno", "ticket")):
        return "investimento"
    if (perfil_atual or {}).get("intencao") == "investimento" and any(
        p in t for p in ("locação", "locacao", "aluguel", "%")
    ):
        return "investimento"
    if any(p in t for p in ("alugar", "aluguel", "locação", "locacao")):
        return "aluguel"
    # Verbos claros de compra
    if any(p in t for p in ("comprar", "compra", "aquisição", "aquisicao")):
        return "compra"
    # Tipo de imóvel sem verbo → assume compra (cenário típico do desafio)
    if any(p in t for p in ("apartamento", "casa", "cobertura", "imóvel", "imovel", "apto")):
        return "compra"
    return None


def _so_saudacao(texto: str) -> bool:
    t = texto.lower().strip()
    t = re.sub(r"[!?.…,]+", "", t).strip()
    return t in {
        "oi",
        "olá",
        "ola",
        "oie",
        "hey",
        "hello",
        "bom dia",
        "boa tarde",
        "boa noite",
        "eai",
        "e aí",
        "e ai",
        "tudo bem",
        "tudo bom",
    }


def _quer_agendar(texto: str) -> bool:
    t = texto.lower()
    return any(
        p in t
        for p in (
            "agendar",
            "agendamento",
            "marcar",
            "visita",
            "reunião",
            "reuniao",
            "horário",
            "horario",
            "pode ser o",
            "quero ver",
            "conhecer o imóvel",
            "conhecer o imovel",
        )
    )


def _fmt_moeda(valor: float) -> str:
    v = float(valor)
    if v >= 1_000_000:
        mi = v / 1_000_000
        if abs(mi - round(mi, 1)) < 1e-6:
            txt = f"{mi:.1f}".rstrip("0").rstrip(".").replace(".", ",")
            return f"R$ {txt} mi"
        return f"R$ {mi:.2f} mi".replace(".", ",")
    if v >= 1000:
        mil = v / 1000
        if abs(mil - round(mil)) < 1e-6:
            return f"R$ {int(round(mil))} mil"
        return f"R$ {v:,.0f}".replace(",", ".")
    return f"R$ {v:,.0f}".replace(",", ".")


def _label_intencao(intencao: str) -> str:
    return {
        "compra": "comprar",
        "aluguel": "alugar",
        "investimento": "investir",
    }.get(intencao, intencao)


def extrair_sinais(texto: str, perfil: dict[str, Any]) -> dict[str, Any]:
    """Heurísticas leves para enriquecer o perfil a partir da mensagem."""
    t = texto.lower().strip()
    novo = dict(perfil)
    faltantes = campos_faltantes(perfil)

    intencao = detectar_intencao(texto, perfil)
    if intencao:
        novo["intencao"] = intencao

    # Regiões (chaves mais longas primeiro)
    for chave, valor in sorted(_REGIOES.items(), key=lambda x: -len(x[0])):
        if chave in t:
            novo["regiao"] = valor
            break

    m_quartos = re.findall(r"(\d+)\s*(?:quartos?|dorms?|dormitórios?|dormitorios?)", t)
    if not m_quartos:
        m_range = re.search(r"(\d+)\s*ou\s*(\d+)\s*(?:quartos?|dorms?|dormitórios?|dormitorios?)?", t)
        if m_range:
            novo["quartos"] = min(int(m_range.group(1)), int(m_range.group(2)))
    else:
        nums = [int(x) for x in m_quartos]
        m_range = re.search(r"(\d+)\s*ou\s*(\d+)", t)
        if m_range and "ou" in t:
            novo["quartos"] = min(int(m_range.group(1)), int(m_range.group(2)))
        else:
            novo["quartos"] = nums[0]

    # Resposta curta só com número quando a próxima pergunta era quartos
    if "quartos" not in novo and "quartos" in faltantes:
        m_so_num = re.fullmatch(r"(\d+)\s*(?:q|qtos?)?", t)
        if m_so_num:
            novo["quartos"] = int(m_so_num.group(1))

    m_mi = re.search(r"(\d+(?:[.,]\d+)?)\s*(?:milh[aã]o|milh[oõ]es|mi)\b", t)
    m_mil = re.search(
        r"(?:até|ate|max(?:imo)?|no máximo|ticket(?:\s*de)?)\s*r?\$?\s*([\d\.]+)\s*mil\b",
        t,
    )
    if not m_mil:
        m_mil = re.search(r"([\d\.]+)\s*mil\b", t)
    if m_mi:
        novo["faixa_preco"] = float(m_mi.group(1).replace(",", ".")) * 1_000_000
        if "ticket" in t:
            novo["ticket"] = novo["faixa_preco"]
    elif m_mil:
        novo["faixa_preco"] = float(m_mil.group(1).replace(".", "")) * 1000
        if "ticket" in t:
            novo["ticket"] = novo["faixa_preco"]
    else:
        m_preco = re.search(
            r"(?:até|ate|max(?:imo)?|no máximo|ticket(?:\s*de)?)\s*r?\$?\s*([\d\.]+)",
            t,
        )
        if m_preco:
            valor = float(m_preco.group(1).replace(".", ""))
            novo["faixa_preco"] = valor
            if "ticket" in t:
                novo["ticket"] = valor

    # Orçamento curto: "800 mil", "até 500 mil", "500000"
    if "faixa_preco" not in novo and "faixa_preco" in faltantes:
        m_num = re.fullmatch(r"r?\$?\s*([\d\.]+)\s*(mil)?", t)
        if m_num:
            valor = float(m_num.group(1).replace(".", ""))
            if m_num.group(2):
                valor *= 1000
            novo["faixa_preco"] = valor

    if any(p in t for p in ("urgente", "essa semana", "o quanto antes", "agora", "curto prazo")):
        novo["urgencia"] = "alta"
    elif any(p in t for p in ("sem pressa", "só olhando", "pesquisando", "médio prazo", "medio prazo")):
        novo["urgencia"] = "baixa"
    elif "urgencia" in faltantes and re.fullmatch(r"(curto|médio|medio|longo)", t):
        mapa = {"curto": "alta", "médio": "media", "medio": "media", "longo": "baixa"}
        novo["urgencia"] = mapa.get(t, "media")

    m_ret = re.search(r"(\d+[.,]?\d*)\s*%", t)
    if m_ret and (novo.get("intencao") == "investimento" or "retorno" in t or "ao ano" in t):
        novo["retorno_esperado"] = m_ret.group(1).replace(",", ".") + "% a.a."

    if novo.get("intencao") == "investimento" and any(
        p in t for p in ("renda", "locação", "locacao", "aluguel")
    ):
        novo["perfil"] = "renda recorrente"

    return novo


def _novos_campos(antes: dict[str, Any], depois: dict[str, Any]) -> dict[str, Any]:
    out = {}
    for k, v in depois.items():
        if v is not None and v != "" and antes.get(k) != v:
            out[k] = v
    return out


def _frase_ack(novos: dict[str, Any]) -> str | None:
    if not novos:
        return None
    pedacos: list[str] = []
    if "intencao" in novos:
        pedacos.append(f"que você quer {_label_intencao(str(novos['intencao']))}")
    if "regiao" in novos:
        pedacos.append(f"foco em {novos['regiao']}")
    if "quartos" in novos:
        q = int(novos["quartos"])
        pedacos.append(f"{q} quarto" + ("s" if q != 1 else ""))
    if "faixa_preco" in novos:
        pedacos.append(f"orçamento até {_fmt_moeda(float(novos['faixa_preco']))}")
    if "urgencia" in novos:
        urg = str(novos["urgencia"])
        mapa = {"alta": "prazo mais curto", "media": "prazo médio", "baixa": "sem pressa"}
        pedacos.append(mapa.get(urg, f"urgência {urg}"))
    if "ticket" in novos and "faixa_preco" not in novos:
        pedacos.append(f"ticket de {_fmt_moeda(float(novos['ticket']))}")
    if "retorno_esperado" in novos:
        pedacos.append(f"retorno em torno de {novos['retorno_esperado']}")
    if "perfil" in novos:
        pedacos.append(f"perfil {novos['perfil']}")
    if not pedacos:
        return None
    if len(pedacos) == 1:
        return f"Perfeito, anotei {pedacos[0]}."
    return "Perfeito, anotei " + ", ".join(pedacos[:-1]) + f" e {pedacos[-1]}."


def _primeira_interacao(estado: dict[str, Any]) -> bool:
    """True se ainda não houve resposta do agente nesta conversa."""
    return not any(m.get("papel") == "agente" for m in (estado.get("mensagens") or []))


def _resposta_fora_de_escopo(*, primeira: bool) -> str:
    if primeira:
        return (
            "Oi! Eu ajudo com compra, aluguel e investimento em imóveis. "
            "Sobre outros assuntos (clima, esportes etc.) não consigo ajudar por aqui — "
            "mas se quiser, me diga o que você busca e em qual região."
        )
    return (
        "Nesse canal eu cuido só de imóveis (compra, aluguel ou investimento). "
        "Se quiser, a gente retoma: comprar, alugar ou investir — e em qual região?"
    )


def _lista_horarios(horarios: list[str]) -> str:
    return "\n".join(f"• {h}" for h in horarios)


_PEDE_EMAIL = (
    "Se quiser, já me passa seu e-mail que eu te mando o convite da visita "
    "(uso só para isso e para o contato do corretor)."
)


def _oferecer_agenda(
    sugestoes: list[dict[str, Any]],
    horarios: list[str] | None = None,
    *,
    pedir_email: bool = False,
) -> str:
    horarios = horarios if horarios is not None else sugerir_horarios(3)
    linhas = [
        "Acho que já tenho o essencial do seu perfil.",
        "Que tal marcarmos uma conversa rápida ou uma visita com um corretor?",
        "Horários que posso oferecer:",
        _lista_horarios(horarios),
        "Qual desses te encaixa melhor? Se preferir outro dia/horário, me fala.",
    ]
    if pedir_email:
        linhas.append(_PEDE_EMAIL)
    if sugestoes:
        linhas.insert(
            1,
            "Posso já alinhar a visita em cima das opções que separamos.",
        )
    return "\n".join(linhas)


_ID_IMOVEL = re.compile(r"\bBR-[A-Z]{2}-\d{3}\b", re.IGNORECASE)

_MOTIVO_HORARIO_INVALIDO = {
    "passado": "Esse horário já passou (ou está muito em cima).",
    "domingo": "Domingo não temos corretor de plantão.",
    "fora_expediente": "As visitas acontecem entre 8h e 19h.",
}


def _ultima_fala_agente(estado: dict[str, Any]) -> str:
    for m in reversed(estado.get("mensagens") or []):
        if m.get("papel") == "agente":
            return str(m.get("texto") or "")
    return ""


def _tipo_agendamento(texto: str) -> str:
    t = texto.lower()
    termos = ("reunião", "reuniao", "conversa", "ligação", "ligacao", "online", "videochamada", "call")
    return "reuniao" if any(p in t for p in termos) else "visita"


def _imovel_do_contexto(estado: dict[str, Any], texto: str) -> str | None:
    m = _ID_IMOVEL.search(texto)
    candidatos = ([m.group(0).upper()] if m else []) + list(estado.get("imoveis_sugeridos") or [])
    return next((c for c in candidatos if obter_imovel(c)), None)


def _primeiro_nome(estado: dict[str, Any]) -> str:
    nome = str((estado.get("perfil") or {}).get("nome") or "").strip()
    return nome.split()[0] if nome else ""


def _pedir_nome_se_primeira(resposta: str, perfil: dict[str, Any], *, primeira: bool) -> str:
    if not primeira or perfil.get("nome"):
        return resposta
    if any(p in resposta.lower() for p in ("te chamar", "seu nome", "se chama")):
        return resposta
    return f"{resposta}\n\nAh, e como posso te chamar?"


def _texto_confirmacao(
    ag: dict[str, Any], *, remarcado: bool, email: str | None, nome: str = ""
) -> str:
    inicio = inicio_do(ag)
    quando = formatar_humano(inicio) if inicio else str(ag.get("horario"))
    oque = "Visita" if ag.get("tipo") == "visita" else "Conversa com o corretor"
    vocativo = f", {nome}" if nome else ""
    partes = [f"{'Remarcado' if remarcado else 'Fechado'}{vocativo}! {oque} marcada para {quando}."]
    imovel = obter_imovel(ag.get("imovel_id"))
    if imovel:
        partes.append(f"Imóvel: {imovel.get('titulo')} — {imovel.get('endereco')}.")
    if email and convite_enviado(ag):
        partes.append(f"O convite vai chegar em {email}. Deixei aqui embaixo os atalhos da agenda também.")
    elif email:
        partes.append(f"Anotei seu e-mail ({email}). Deixei aqui embaixo os atalhos para salvar na agenda.")
    else:
        partes.append(
            "Deixei aqui embaixo os atalhos para salvar na sua agenda (Google, Outlook ou .ics). "
            "Se quiser receber o convite por e-mail, me passa seu e-mail."
        )
    partes.append("Se precisar mudar, é só me avisar.")
    return "\n\n".join(partes)


def _oferta(texto: str, horarios: list[str], fecho: str = "Qual fica melhor?") -> str:
    return f"{texto}\n{_lista_horarios(horarios)}\n{fecho}"


_CONFIRMA_EMAIL = re.compile(r"seu e-mail é ([\w.+-]+@[\w-]+(?:\.[\w-]+)+)\?")


def _parece_outra_resposta(texto: str) -> bool:
    """Evita tomar 'comprar' ou 'Pinheiros' por nome quando o agente fez duas perguntas."""
    return bool(extrair_sinais(texto, {})) or _so_saudacao(texto) or _quer_agendar(texto)


def _tratar_contato(estado: dict[str, Any], mensagem: str) -> tuple[dict[str, Any] | None, str | None, str | None]:
    """Captura nome e e-mail (com checagem de domínio digitado errado).

    Retorna (resposta pronta ou None, e-mail novo aceito, nome novo).
    """
    perfil = dict(estado.get("perfil") or {})
    ultima = _ultima_fala_agente(estado)
    nome = None
    if not perfil.get("nome"):
        nome = extrair_nome(mensagem, ultima, rejeitar=_parece_outra_resposta)
        if nome:
            perfil["nome"] = nome

    pendente = _CONFIRMA_EMAIL.search(ultima)
    email = extrair_email(mensagem)
    resposta = None
    if email and not pendente:
        ja_sugerido = any(
            f"(Você digitou {email}.)" in str(m.get("texto") or "")
            for m in estado.get("mensagens") or []
            if m.get("papel") == "agente"
        )
        sugestao = None if ja_sugerido else sugerir_correcao_email(email)
        if sugestao:
            prazer = f"Prazer, {nome.split()[0]}! " if nome else ""
            resposta = {
                "resposta": f"{prazer}Só pra confirmar: seu e-mail é {sugestao}? (Você digitou {email}.)",
                "evento": None,
            }
            email = None
    elif not email and pendente:
        if afirmativo(mensagem):
            email = pendente.group(1)
        elif negativo(mensagem):
            resposta = {"resposta": "Sem problema! Me passa o e-mail certinho?", "evento": None}

    if email and email != perfil.get("email"):
        perfil["email"] = email
    else:
        email = None
    estado["perfil"] = perfil
    return resposta, email, nome


_PROPOSTA = re.compile(r"Posso reservar a visita para [^,?]+, (\d{2}/\d{2}/\d{4}) às (\d{2}:\d{2})\?")


def _horario_proposto(texto: str) -> str | None:
    m = _PROPOSTA.search(texto or "")
    return f"{m.group(1)} {m.group(2)}" if m else None


def _proposta_um_toque(estado: dict[str, Any], horario: str) -> str:
    inicio = parse_horario(horario)
    nome = _primeiro_nome(estado)
    quando = formatar_proposta(inicio) if inicio else horario
    abertura = f"{nome}, já tenho seus dados." if nome else "Anotei seu e-mail."
    return (
        f"{abertura} Posso reservar a visita para {quando}? "
        "É só responder \"sim\" que eu já te mando o convite — ou me diga outro dia e horário."
    )


def _tratar_agenda(
    estado: dict[str, Any], mensagem: str, email: str | None = None
) -> dict[str, Any] | None:
    """Escolha/remarcação/cancelamento de visita. None = seguir o fluxo normal de qualificação."""
    perfil = estado.get("perfil") or {}
    ativo = agendamento_ativo(estado)
    ultima = _ultima_fala_agente(estado)
    proposto = _horario_proposto(ultima)
    ofertados = [proposto] if proposto else horarios_no_texto(ultima)

    if ativo and pede_cancelamento(mensagem):
        cancelar(estado)
        inicio = inicio_do(ativo)
        quando = formatar_humano(inicio) if inicio else ativo.get("horario")
        return {
            "resposta": f"Tudo certo, cancelei a visita de {quando}. Quando quiser remarcar, é só me chamar.",
            "evento": EVENTO_CANCELADO,
        }

    remarcacao = bool(ativo) and pede_remarcacao(mensagem)
    contexto = (
        bool(ofertados)
        or remarcacao
        or _quer_agendar(mensagem)
        or _quer_agendar(ultima)
    )
    escolha = interpretar_escolha(mensagem, ofertados)
    if escolha and not contexto and not escolha.explicita:
        escolha = None
    if escolha is None and ofertados:
        if afirmativo(mensagem) and len(ofertados) == 1:
            inicio_ofertado = parse_horario(ofertados[0])
            escolha = Escolha(inicio=inicio_ofertado, invalido=validar_horario(inicio_ofertado))
        elif afirmativo(mensagem) and not email:
            return {"resposta": _oferta("Ótimo! Qual desses fica melhor?", ofertados, "É só me dizer qual."), "evento": None}
        elif negativo(mensagem) and len(ofertados) == 1:
            escolha = Escolha(recusou=True)

    if email and ativo and not (escolha and escolha.inicio):
        convidar_lead(estado, email)
        extra = (
            " O convite da visita já está a caminho."
            if convite_enviado(ativo)
            else " O corretor confirma a visita por lá."
        )
        return {"resposta": f"Perfeito, anotei {email}.{extra}", "evento": None}

    if email and not ativo and escolha is None and (ofertados or contexto):
        proposta = sugerir_horarios(1)
        if proposta:
            return {"resposta": _proposta_um_toque(estado, proposta[0]), "evento": None}

    if escolha is None:
        if remarcacao and ativo:
            novos = sugerir_horarios(3, evitar=[str(ativo.get("horario"))])
            return {
                "resposta": _oferta(
                    "Claro, a gente remarca. Tenho estes horários:",
                    novos,
                    "Qual fica melhor? Se preferir, me diga dia e hora.",
                ),
                "evento": None,
            }
        return None

    if escolha.recusou:
        novos = sugerir_horarios(3, evitar=ofertados)
        return {
            "resposta": _oferta(
                "Sem problema! Outras opções:",
                novos,
                "Ou me diga um dia e horário que funcionem pra você.",
            ),
            "evento": None,
        }

    if escolha.invalido:
        dia = escolha.inicio.date() if escolha.inicio else escolha.dia
        novos = (sugerir_horarios(3, dia=dia) if escolha.invalido == "fora_expediente" and dia else []) or sugerir_horarios(3)
        motivo = _MOTIVO_HORARIO_INVALIDO.get(escolha.invalido, "Esse horário não dá.")
        return {"resposta": _oferta(f"{motivo} Posso te oferecer:", novos, "Algum desses funciona?"), "evento": None}

    if escolha.inicio is None:
        novos = sugerir_horarios(3, dia=escolha.dia, periodo=escolha.periodo)
        if novos:
            abertura = f"{rotulo_dia(escolha.dia).capitalize()} tenho:" if escolha.dia else "Nesse período tenho:"
            return {"resposta": _oferta(abertura, novos, "Qual prefere?"), "evento": None}
        novos = sugerir_horarios(3, periodo=escolha.periodo)
        return {"resposta": _oferta("Nesse dia não tenho horário livre. Que tal:", novos), "evento": None}

    inicio = escolha.inicio
    fim = inicio + timedelta(minutes=config.AGENDA_DURACAO_MIN)
    if any(o_ini < fim and inicio < o_fim for o_ini, o_fim in horarios_ocupados(inicio, fim)):
        novos = sugerir_horarios(3, dia=inicio.date()) or sugerir_horarios(3)
        return {
            "resposta": _oferta("Nesse horário o corretor já tem compromisso. Tenho livre:", novos),
            "evento": None,
        }

    email_lead = perfil.get("email")
    nome = _primeiro_nome(estado)

    if ativo:
        if inicio_do(ativo) == inicio:
            return {"resposta": _texto_confirmacao(ativo, remarcado=False, email=email_lead, nome=nome), "evento": None}
        ag = remarcar(estado, inicio)
        return {
            "resposta": _texto_confirmacao(ag, remarcado=True, email=email_lead, nome=nome),
            "evento": EVENTO_REMARCADO,
        }

    ag = agendar(
        estado,
        inicio,
        tipo=_tipo_agendamento(mensagem),
        imovel_id=_imovel_do_contexto(estado, mensagem),
        email=email_lead,
    )
    return {
        "resposta": _texto_confirmacao(ag, remarcado=False, email=email_lead, nome=nome),
        "evento": EVENTO_AGENDADO,
    }


def _agendamento_publico(estado: dict[str, Any]) -> dict[str, Any] | None:
    ativo = agendamento_ativo(estado)
    if not ativo:
        return None
    indice = (estado.get("agendamentos") or []).index(ativo)
    return publico(ativo, str(estado.get("lead_id") or ""), indice)


def _bloco_imoveis(
    sugestoes: list[dict[str, Any]],
    *,
    match: str,
    motivo: str,
    perfil: dict[str, Any],
) -> list[str]:
    """Frases diretas ao apresentar catálogo (exato vs próximo)."""
    if not sugestoes:
        return []
    partes: list[str] = []
    quartos = perfil.get("quartos")

    if match == "aproximado":
        if motivo:
            partes.append(f"Direto: {motivo}.")
        elif quartos is not None:
            partes.append(
                f"Não tenho imóvel com {quartos} quarto"
                + ("s" if int(quartos) != 1 else "")
                + " no estoque agora. O mais próximo que tenho:"
            )
        else:
            partes.append("Não achei o filtro exato. O mais próximo que tenho:")
    else:
        partes.append("Separei estas opções:")

    for im in sugestoes[:3]:
        partes.append(formatar_imovel(im))

    partes.append("Quer ver alguma dessas ou ajustar o filtro?")
    return partes


def _resposta_deterministica(
    mensagem: str,
    estado: dict[str, Any],
    qual: dict[str, Any],
    sugestoes: list[dict[str, Any]],
    *,
    perfil_antes: dict[str, Any],
    mostrar_imoveis: bool,
    match_busca: str = "exato",
    motivo_busca: str = "",
    horarios: list[str] | None = None,
    agendado: str = "",
    proposta: str = "",
) -> str:
    perfil = estado.get("perfil") or {}
    partes: list[str] = []
    primeira = _primeira_interacao(estado)
    saudacao = _so_saudacao(mensagem)

    if primeira:
        if saudacao:
            partes.append(
                "Oi! Sou o assistente da imobiliária. Te ajudo a achar o imóvel "
                "e, se fizer sentido, marco visita com um corretor."
            )
        else:
            partes.append("Oi! Vou te ajudar a encontrar o que você busca.")

    if perfil.get("nome") and not perfil_antes.get("nome"):
        partes.append(f"Prazer, {_primeiro_nome(estado)}!")

    novos = _novos_campos(perfil_antes, perfil)
    ack = _frase_ack(novos)
    if ack:
        partes.append(ack)

    pergunta = proxima_pergunta(perfil)

    if mostrar_imoveis and sugestoes:
        partes.extend(
            _bloco_imoveis(
                sugestoes,
                match=match_busca,
                motivo=motivo_busca,
                perfil=perfil,
            )
        )
    elif match_busca == "vazio" and pode_sugerir_imoveis(perfil):
        partes.append(
            "Não tenho imóvel com esse filtro no estoque agora. "
            "Me diga outra região ou quantidade de quartos que eu busco de novo."
        )

    if pergunta and not (mostrar_imoveis and sugestoes):
        partes.append(pergunta)
    elif agendado:
        partes.append(f"Sua visita segue marcada para {agendado}. Quer ver mais alguma opção até lá?")
    elif proposta:
        partes.append(proposta)
    elif qual.get("pronto_para_agendar") or _quer_agendar(mensagem):
        pedir_email = not perfil.get("email")
        if not (mostrar_imoveis and sugestoes):
            partes.append(_oferecer_agenda([], horarios, pedir_email=pedir_email))
        else:
            partes.append(_oferecer_agenda(sugestoes, horarios, pedir_email=pedir_email))
    elif not (mostrar_imoveis and sugestoes) and not pergunta:
        partes.append("Quer que eu ajuste a busca ou já te conecte com um corretor?")

    limpas: list[str] = []
    for p in partes:
        if not p:
            continue
        limpas.append(p)
    return "\n\n".join(limpas)


def _resposta_llm(
    mensagem: str,
    estado: dict[str, Any],
    sugestoes: list[dict[str, Any]],
    *,
    primeira: bool,
    fora_de_escopo: bool = False,
    pronto_para_agendar: bool = False,
    match_busca: str = "exato",
    motivo_busca: str = "",
    horarios: list[str] | None = None,
    agendado: str = "",
    nome_novo: str = "",
    busca_feita: bool = True,
) -> str | None:
    if not config.OPENAI_API_KEY:
        return None
    try:
        from openai import OpenAI

        client = OpenAI(api_key=config.OPENAI_API_KEY)
        if sugestoes:
            catalogo_txt = "\n".join(formatar_imovel(i) for i in sugestoes)
        elif busca_feita:
            catalogo_txt = "(lista vazia — NÃO invente imóveis)"
        else:
            proxima = proxima_pergunta(estado.get("perfil") or {})
            catalogo_txt = (
                "(ainda não busquei: faltam dados do lead. NÃO diga que não tem imóveis; "
                f"faça a próxima pergunta{': ' + proxima if proxima else ''})"
            )
        if sugestoes:
            fatos = []
            for i in sugestoes[:3]:
                fatos.append(
                    f"- id={i.get('id')} quartos={i.get('quartos')} "
                    f"regiao={i.get('regiao')} preco={i.get('preco')} "
                    f"motivo={i.get('match_motivo') or '-'}"
                )
            catalogo_txt += "\nFatos (use SOMENTE estes números):\n" + "\n".join(fatos)
        historico = (estado.get("mensagens") or [])[-6:]
        hist_txt = "\n".join(f"{m.get('papel')}: {m.get('texto')}" for m in historico)
        system = (
            "Você é um SDR imobiliário brasileiro no WhatsApp: direto, claro e humano.\n"
            "REGRAS DURAS:\n"
            "- Seja objetivo: 2–5 frases curtas. Sem enrolação.\n"
            "- UMA pergunta por vez.\n"
            "- NUNCA invente imóveis, quartos, preços, bairros ou tipologias.\n"
            "- Só cite números que aparecem na lista de imóveis/fatos fornecida.\n"
            "- Se a lista estiver vazia: diga que não tem esse filtro e peça outro "
            "(região ou quartos). NÃO sugira '7, 8 ou 9 quartos' se isso não estiver na lista.\n"
            "- Se match for aproximado: diga em 1 frase que não tem o exato, mostre "
            "o que TEM (só da lista) e pergunte se quer ver/ajustar.\n"
            "- Proibido jargão: match, lead score, perfil completo, estoque filtrado.\n"
            "- Não se apresente de novo se a conversa já começou.\n"
            "- Fora de escopo: recuse e volte para imóveis.\n"
            "- Horários: NUNCA invente. Se for oferecer visita, liste EXATAMENTE os horários "
            "livres fornecidos, um por linha, no formato '• dd/mm/aaaa hh:mm'.\n"
            "- Se já houver visita marcada, não ofereça novos horários; lembre a data e, se o "
            "lead quiser mudar, peça o novo dia/horário.\n"
            "- NUNCA diga que uma visita foi marcada, confirmada ou agendada se 'Visita já marcada' "
            "for 'não': quem confirma é o sistema, não você.\n"
            "- Se o Perfil tiver 'nome', trate o lead pelo primeiro nome (sem repetir toda hora). "
            "Se 'Nome recém-informado' vier preenchido, cumprimente: 'Prazer, <nome>!'.\n"
            "- Não peça nome nem e-mail: o sistema faz isso."
        )
        horarios_txt = _lista_horarios(horarios) if horarios else "(não oferecer agora)"
        user = (
            f"Primeira mensagem: {'sim' if primeira else 'não'}\n"
            f"Fora de escopo: {'sim' if fora_de_escopo else 'não'}\n"
            f"Pronto para agendar: {'sim' if pronto_para_agendar else 'não'}\n"
            f"Visita já marcada: {agendado or 'não'}\n"
            f"Nome recém-informado: {nome_novo or '(não)'}\n"
            f"Horários livres do corretor:\n{horarios_txt}\n"
            f"Tipo de busca: {match_busca}\n"
            f"Motivo: {motivo_busca or '(n/a)'}\n"
            f"Perfil: {json.dumps(estado.get('perfil') or {}, ensure_ascii=False)}\n"
            f"Histórico:\n{hist_txt}\n"
            f"Imóveis (única fonte de verdade):\n{catalogo_txt}\n\n"
            f"Mensagem do lead: {mensagem}"
        )
        resp = client.chat.completions.create(
            model=config.LLM_MODEL,
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            temperature=0.35,
        )
        return (resp.choices[0].message.content or "").strip() or None
    except Exception:
        return None


def processar_mensagem(lead_id: str, mensagem: str) -> dict[str, Any]:
    estado = memoria.carregar(lead_id)
    perfil_antes = dict(estado.get("perfil") or {})
    primeira = _primeira_interacao(estado)
    qual_antes = score_estado(estado)  # referência para decidir eventos de CRM

    memoria.adicionar_mensagem(estado, "lead", mensagem)

    agenda, email_novo, nome_novo = _tratar_contato(estado, mensagem)
    if agenda is None:
        agenda = _tratar_agenda(estado, mensagem, email_novo)
        primeiro = nome_novo.split()[0] if nome_novo else ""
        if agenda and primeiro and primeiro not in agenda["resposta"]:
            agenda["resposta"] = f"Prazer, {primeiro}! {agenda['resposta']}"
    if agenda:
        memoria.adicionar_mensagem(estado, "agente", agenda["resposta"])
        qual = score_estado(estado)
        resumo = montar_resumo(estado)
        if agenda["evento"]:
            crm = sincronizar_crm(estado, resumo, evento=agenda["evento"])
        else:
            crm = sincronizar_crm(estado, resumo, qual_antes=qual_antes)
        memoria.salvar(estado)
        return {
            "lead_id": lead_id,
            "resposta": agenda["resposta"],
            "perfil": estado.get("perfil") or {},
            "qualificacao": qual,
            "imoveis": [],
            "exibir_imoveis": False,
            "match_busca": "vazio",
            "motivo_busca": "",
            "agendamento": _agendamento_publico(estado),
            "resumo_corretor": resumo,
            "usou_llm": False,
            "crm": crm,
            "fora_de_escopo": False,
        }

    perfil_base = dict(estado.get("perfil") or {})
    fora = not (email_novo or nome_novo) and mensagem_fora_de_escopo(mensagem, perfil_base)
    if fora:
        # Não polui o perfil com sinais falsos; não busca catálogo
        perfil = perfil_base
        estado["perfil"] = perfil
        qual = score_estado(estado)
        sugestoes: list[dict[str, Any]] = []
        resposta_llm = _resposta_llm(
            mensagem,
            estado,
            sugestoes,
            primeira=primeira,
            fora_de_escopo=True,
        )
        usou_llm = bool(resposta_llm)
        resposta = resposta_llm or _resposta_fora_de_escopo(primeira=primeira)
        memoria.adicionar_mensagem(estado, "agente", resposta)
        memoria.salvar(estado)
        return {
            "lead_id": lead_id,
            "resposta": resposta,
            "perfil": perfil,
            "qualificacao": qual,
            "imoveis": [],
            "exibir_imoveis": False,
            "agendamento": _agendamento_publico(estado),
            "resumo_corretor": montar_resumo(estado),
            "usou_llm": usou_llm,
            "fora_de_escopo": True,
        }

    # Saudação pura: não força intenção; só conversa
    if _so_saudacao(mensagem) and not perfil_base.get("intencao"):
        perfil = dict(perfil_base)
        estado["perfil"] = perfil
        qual = score_estado(estado)
        resposta_llm = _resposta_llm(mensagem, estado, [], primeira=primeira)
        usou_llm = bool(resposta_llm)
        resposta = resposta_llm or _resposta_deterministica(
            mensagem,
            estado,
            qual,
            [],
            perfil_antes=perfil_antes,
            mostrar_imoveis=False,
        )
        resposta = _pedir_nome_se_primeira(resposta, perfil, primeira=primeira)
        memoria.adicionar_mensagem(estado, "agente", resposta)
        memoria.salvar(estado)
        return {
            "lead_id": lead_id,
            "resposta": resposta,
            "perfil": perfil,
            "qualificacao": qual,
            "imoveis": [],
            "exibir_imoveis": False,
            "agendamento": _agendamento_publico(estado),
            "resumo_corretor": montar_resumo(estado),
            "usou_llm": usou_llm,
            "fora_de_escopo": False,
        }

    perfil = extrair_sinais(mensagem, perfil_base)
    # LLM complementa/corrige a regex (se houver OPENAI_API_KEY); sem chave, nada muda.
    perfil = mesclar_perfil(
        perfil, extrair_perfil_llm(mensagem, perfil, estado.get("mensagens"))
    )
    estado["perfil"] = perfil
    if not nome_novo and perfil.get("nome") and not perfil_antes.get("nome"):
        nome_novo = str(perfil["nome"])
    qual = score_estado(estado)

    sugestoes: list[dict[str, Any]] = []
    match_busca = "vazio"
    motivo_busca = ""
    exibir = pode_sugerir_imoveis(perfil)
    if exibir:
        preco_max = perfil.get("faixa_preco") or perfil.get("ticket")
        quartos = perfil.get("quartos")
        resultado = buscar_resultado(
            intencao=perfil.get("intencao"),
            regiao=perfil.get("regiao"),
            quartos_min=int(quartos) if quartos is not None else None,
            preco_max=float(preco_max) if preco_max is not None else None,
        )
        sugestoes = resultado.get("imoveis") or []
        match_busca = str(resultado.get("match") or "vazio")
        motivo_busca = str(resultado.get("motivo") or "")
    estado["imoveis_sugeridos"] = [s["id"] for s in sugestoes]

    # Cards quando há filtro mínimo; inclui match aproximado (sugestões próximas)
    mostrar = exibir and bool(sugestoes) and (
        perfil.get("quartos") is not None
        or perfil.get("faixa_preco") is not None
        or match_busca == "aproximado"
    )

    ativo = agendamento_ativo(estado)
    inicio_ativo = inicio_do(ativo) if ativo else None
    agendado = formatar_humano(inicio_ativo) if inicio_ativo else ""
    oferecer = not agendado and (bool(qual.get("pronto_para_agendar")) or _quer_agendar(mensagem))
    tem_email = bool(perfil.get("email"))
    horarios = sugerir_horarios(1 if tem_email else 3) if oferecer else []
    # Com e-mail em mãos, um toque: propõe o primeiro horário livre e reserva no "sim".
    proposta = _proposta_um_toque(estado, horarios[0]) if tem_email and horarios else ""

    resposta_llm = _resposta_llm(
        mensagem,
        estado,
        sugestoes if mostrar else [],
        primeira=primeira,
        pronto_para_agendar=bool(qual.get("pronto_para_agendar")),
        match_busca=match_busca,
        motivo_busca=motivo_busca,
        horarios=[] if proposta else horarios,
        agendado=agendado,
        nome_novo=nome_novo or "",
        busca_feita=mostrar or (exibir and match_busca == "vazio"),
    )
    usou_llm = bool(resposta_llm)
    primeiro = nome_novo.split()[0] if nome_novo else ""
    if resposta_llm and primeiro and primeiro not in resposta_llm:
        resposta_llm = f"Prazer, {primeiro}! {resposta_llm}"
    if resposta_llm and proposta:
        # a proposta única substitui qualquer oferta que o LLM tenha escrito
        if horarios_no_texto(resposta_llm) or _quer_agendar(resposta_llm):
            resposta_llm = proposta
        else:
            resposta_llm += "\n\n" + proposta
    elif resposta_llm and horarios and _quer_agendar(resposta_llm):
        if not horarios_no_texto(resposta_llm):
            # o lead precisa ver horários concretos para conseguir escolher um
            resposta_llm += "\n\nHorários que posso oferecer:\n" + _lista_horarios(horarios)
        resposta_llm += "\n\n" + _PEDE_EMAIL
    resposta = resposta_llm or _resposta_deterministica(
        mensagem,
        estado,
        qual,
        sugestoes if mostrar else [],
        perfil_antes=perfil_antes,
        mostrar_imoveis=mostrar,
        match_busca=match_busca,
        motivo_busca=motivo_busca,
        horarios=horarios,
        agendado=agendado,
        proposta=proposta,
    )
    resposta = _pedir_nome_se_primeira(resposta, perfil, primeira=primeira)

    memoria.adicionar_mensagem(estado, "agente", resposta)
    resumo = montar_resumo(estado)
    # Envia ao CRM só se prioridade/prontidão mudou nesta mensagem
    crm = sincronizar_crm(estado, resumo, qual_antes=qual_antes)
    memoria.salvar(estado)

    return {
        "lead_id": lead_id,
        "resposta": resposta,
        "perfil": perfil,
        "qualificacao": qual,
        "imoveis": sugestoes if mostrar else [],
        "exibir_imoveis": mostrar,
        "match_busca": match_busca if mostrar else "vazio",
        "motivo_busca": motivo_busca if mostrar else "",
        "agendamento": _agendamento_publico(estado),
        "resumo_corretor": resumo,
        "usou_llm": usou_llm,
        "crm": crm,
        "fora_de_escopo": False,
    }


def follow_up(lead_id: str) -> dict[str, Any]:
    """Retoma conversa parada mantendo contexto (cenário 3 do desafio)."""
    estado = memoria.carregar(lead_id)
    perfil = estado.get("perfil") or {}
    qual = score_estado(estado)
    pergunta = proxima_pergunta(perfil)

    if estado.get("mensagens"):
        trechos = []
        if perfil.get("intencao"):
            trechos.append(_label_intencao(str(perfil["intencao"])))
        if perfil.get("regiao"):
            trechos.append(f"em {perfil['regiao']}")
        contexto = (" " + " ".join(trechos)) if trechos else ""
        texto = (
            f"Oi! Passando só para retomar nossa conversa{contexto}. "
            "Vi que paramos no meio e queria te ajudar a avançar sem pressa."
        )
    else:
        texto = (
            "Oi! Eu sou o assistente da imobiliária. "
            "Posso te ajudar a encontrar o imóvel certo — "
            "você busca comprar, alugar ou investir?"
        )

    ativo = agendamento_ativo(estado)
    inicio_ativo = inicio_do(ativo) if ativo else None
    if inicio_ativo:
        texto += f" Sua visita segue marcada para {formatar_humano(inicio_ativo)}."
    elif pergunta:
        texto += f" {pergunta}"
    elif qual.get("pronto_para_agendar"):
        texto += " Se fizer sentido, já posso te passar horários para uma visita."

    memoria.adicionar_mensagem(estado, "agente", texto)
    memoria.salvar(estado)
    return {"lead_id": lead_id, "resposta": texto, "qualificacao": qual}
