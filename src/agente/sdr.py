"""Agente SDR imobiliário orientado a estado e mensagens humanas.

Esta versão evita tratar a conversa como um formulário rígido.

Características:
- usuário pode responder fora de ordem;
- pode fornecer vários dados na mesma mensagem;
- pode corrigir dados anteriores;
- pode mudar de ideia;
- tolera erros de digitação em intenção e região;
- perguntas fora de escopo não apagam o contexto;
- dúvidas imobiliárias não quebram a qualificação;
- captura nome e e-mail e agenda/remarca/cancela visitas pelo chat;
- LLM é opcional: Python controla estado, fluxo e busca.
"""

from __future__ import annotations

import re
from datetime import timedelta
from typing import Any

import config
from src.agenda.calendario import horarios_ocupados
from src.agenda.scheduler import (
    ADIA_AGENDA,
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
from src.crm.cliente import (
    EVENTO_AGENDADO,
    EVENTO_CANCELADO,
    EVENTO_REMARCADO,
    sincronizar as sincronizar_crm,
)
from src.imoveis.catalogo import buscar_resultado, formatar_imovel
from src.memoria import conversa as memoria
from src.qualificacao.contato import afirmativo, extrair_nome, negativo, sugerir_correcao_email, vocativo
from src.qualificacao.fluxo_conversa import (
    pergunta_para,
    proximo_campo,
    qualificacao_concluida,
)
from src.qualificacao.interpretador import (
    extrair_dados_deterministicos,
    interpretar_mensagem,
    mensagem_fora_de_escopo,
    normalizar_texto,
    reconciliar_perfil,
)
from src.qualificacao.lead import score_estado
from src.resumo.corretor import montar_resumo


def _so_saudacao(texto: str) -> bool:
    t = normalizar_texto(texto)
    t = re.sub(r"[!?.…,]+", "", t).strip()

    return t in {
        "oi",
        "ola",
        "oie",
        "hey",
        "hello",
        "bom dia",
        "boa tarde",
        "boa noite",
        "eai",
        "e ai",
        "tudo bem",
        "tudo bom",
    }


def _descrever_quartos(q: int) -> str:
    if q == 0:
        return "no estilo studio/kitnet"
    return f"{q} quarto" + ("s" if q != 1 else "")


def _quer_agendar(texto: str) -> bool:
    t = normalizar_texto(texto)
    if ADIA_AGENDA.search(t):
        return False

    return any(
        termo in t
        for termo in (
            "agendar",
            "agendamento",
            "marcar",
            "visita",
            "reuniao",
            "horario",
            "pode ser o",
            "quero ver o imovel",
            "quero ver o apartamento",
            "falar com corretor",
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

        if abs(mil - round(mil)) < 1e-9:
            return f"R$ {int(round(mil))} mil"

    return f"R$ {v:,.0f}".replace(",", ".")


def _label_intencao(intencao: str) -> str:
    return {
        "compra": "comprar",
        "aluguel": "alugar",
        "investimento": "investir",
    }.get(intencao, intencao)


def _controle(estado: dict[str, Any]) -> dict[str, Any]:
    return estado.setdefault(
        "controle_sdr",
        {
            "campo_aguardando": None,
            "ultimo_campo_preenchido": None,
        },
    )


def _primeira_interacao(estado: dict[str, Any]) -> bool:
    """True se ainda não houve resposta do agente nesta conversa."""
    return not any(m.get("papel") == "agente" for m in (estado.get("mensagens") or []))


def _campo_principal_alterado(
    alteracoes: dict[str, tuple[Any, Any]],
) -> str | None:
    prioridade = (
        "intencao",
        "regiao",
        "faixa_preco",
        "ticket",
        "quartos",
        "urgencia",
        "perfil",
        "retorno_esperado",
        "tipo_imovel",
    )

    encontrados = [
        campo
        for campo in prioridade
        if campo in alteracoes
        and not campo.endswith("_flexivel")
    ]

    return encontrados[-1] if encontrados else None


def _descricao_alteracoes(
    alteracoes: dict[str, tuple[Any, Any]],
) -> list[str]:
    partes: list[str] = []

    if "intencao" in alteracoes:
        _, novo = alteracoes["intencao"]

        if novo:
            partes.append(f"buscar para {_label_intencao(str(novo))}")

    if "regiao" in alteracoes:
        _, novo = alteracoes["regiao"]

        if novo:
            partes.append(f"região {str(novo).title()}")
        elif alteracoes.get("regiao_flexivel"):
            partes.append("região flexível")

    if "faixa_preco" in alteracoes:
        _, novo = alteracoes["faixa_preco"]

        if novo is not None:
            partes.append(f"até {_fmt_moeda(float(novo))}")
        elif alteracoes.get("faixa_preco_flexivel"):
            partes.append("valor flexível")

    if "ticket" in alteracoes:
        _, novo = alteracoes["ticket"]

        if novo is not None:
            partes.append(f"ticket de {_fmt_moeda(float(novo))}")

    if "quartos" in alteracoes:
        _, novo = alteracoes["quartos"]

        if novo is not None:
            partes.append(_descrever_quartos(int(novo)))
        elif alteracoes.get("quartos_flexivel"):
            partes.append("quantidade de quartos flexível")

    if "urgencia" in alteracoes:
        _, novo = alteracoes["urgencia"]
        mapa = {
            "alta": "prazo curto",
            "media": "prazo médio",
            "baixa": "sem pressa",
            "indefinida": "prazo ainda em aberto",
        }

        if novo:
            partes.append(mapa.get(str(novo), str(novo)))

    if "tipo_imovel" in alteracoes:
        _, novo = alteracoes["tipo_imovel"]

        if novo:
            partes.append(str(novo))

    if "perfil" in alteracoes:
        _, novo = alteracoes["perfil"]

        if novo:
            partes.append(f"foco em {novo}")

    if "retorno_esperado" in alteracoes:
        _, novo = alteracoes["retorno_esperado"]

        if novo:
            partes.append(f"retorno esperado de {str(novo).replace('% a.a.', '% ao ano')}")

    return partes


_ABERTURAS_ANOTEI = ("Perfeito, anotei", "Show, anotado", "Beleza, anotei", "Ótimo, anotado")
_ABERTURAS_ATUALIZEI = ("Certo, atualizei", "Pronto, atualizei", "Feito, atualizei")


def _ack_alteracoes(
    alteracoes: dict[str, tuple[Any, Any]],
    *,
    correcao: bool,
    variacao: int = 0,
) -> str | None:
    descricoes = _descricao_alteracoes(alteracoes)

    if not descricoes:
        return None

    houve_substituicao = any(
        antigo not in (None, "", False)
        and novo != antigo
        for campo, (antigo, novo) in alteracoes.items()
        if not campo.endswith("_flexivel")
    )

    # Variar a abertura evita o "Perfeito, anotei" idêntico a cada mensagem.
    opcoes = _ABERTURAS_ATUALIZEI if (correcao or houve_substituicao) else _ABERTURAS_ANOTEI
    prefixo = opcoes[variacao % len(opcoes)]

    if len(descricoes) == 1:
        return f"{prefixo}: {descricoes[0]}."

    return (
        f"{prefixo}: "
        + ", ".join(descricoes[:-1])
        + f" e {descricoes[-1]}."
    )


def _resposta_fora_escopo(
    *,
    proxima_pergunta: str | None,
) -> str:
    base = (
        "Por aqui eu consigo te ajudar com compra, aluguel, investimento "
        "e visitas a imóveis."
    )

    if proxima_pergunta:
        return f"{base} Voltando à sua busca: {proxima_pergunta}"

    return f"{base} Se quiser, me diga o que você quer ajustar na busca."


def _resposta_duvida_imobiliaria(
    mensagem: str,
    *,
    proxima_pergunta: str | None,
) -> str | None:
    """Responde dúvidas comuns sem inventar características de imóveis.

    None quando o tema não é conhecido: a mensagem segue o fluxo normal
    ("tem algo em Moema até 1 milhão?" é busca, não dúvida).
    """
    t = normalizar_texto(mensagem)

    if "itbi" in t:
        resposta = (
            "O ITBI é o imposto municipal pago na compra do imóvel. Fica em torno de 2% a 3% "
            "do valor, conforme a cidade, e é pago antes da escritura."
        )

    elif any(x in t for x in ("escritura", "cartorio", "registro", "documentacao")):
        resposta = (
            "Na compra, além do valor do imóvel, entram a escritura e o registro em cartório, "
            "que somam algo perto de 1% a 2%. O corretor te passa a lista de documentos certinha."
        )

    elif "fgts" in t:
        resposta = (
            "Dá pra usar o FGTS na entrada ou para amortizar o financiamento, desde que seja "
            "o seu primeiro imóvel residencial na cidade e ele se enquadre nas regras do programa."
        )

    elif any(x in t for x in ("financi", "entrada", "juros")):
        resposta = (
            "Dá sim. Em geral os bancos pedem uma entrada de uns 20% e financiam o resto; "
            "a taxa e o prazo dependem da sua análise de crédito."
        )

    elif any(x in t for x in ("fiador", "caucao", "seguro fianca")):
        resposta = (
            "No aluguel, as garantias mais comuns são fiador, caução (normalmente até 3 aluguéis) "
            "ou seguro-fiança. Cada proprietário aceita uma ou mais delas."
        )

    elif any(x in t for x in ("rentabilidade", "rendimento", "retorno", "valoriza")):
        resposta = (
            "Para aluguel residencial, a rentabilidade costuma ficar entre 4% e 6% ao ano sobre "
            "o valor do imóvel, sem contar a valorização. Varia bastante por bairro."
        )

    elif any(x in t for x in ("garagem", "vaga", "pet", "cachorro", "gato", "elevador")):
        resposta = (
            "Isso muda de imóvel pra imóvel. Quando eu te mostrar as opções, "
            "confirmo esse ponto em cada uma."
        )

    elif any(x in t for x in ("condominio", "iptu")):
        resposta = (
            "Condomínio e IPTU variam bastante de um imóvel pro outro. "
            "Assim que eu te mostrar as opções, te passo os valores de cada uma."
        )

    else:
        return None

    if proxima_pergunta:
        resposta += f"\n\nE me conta: {proxima_pergunta[0].lower()}{proxima_pergunta[1:]}"

    return resposta


# ---------------------------------------------------------------- agenda e contato

def _lista_horarios(horarios: list[str]) -> str:
    return "\n".join(f"• {h}" for h in horarios)


_PEDE_EMAIL = (
    "Se quiser, já me passa seu e-mail que eu te mando o convite da visita "
    "(uso só para isso e para o contato do corretor)."
)


def _oferecer_agenda(
    horarios: list[str],
    *,
    pedir_email: bool = False,
    apos_opcoes: bool = False,
) -> str:
    if not horarios:
        return (
            "Já tenho o essencial da sua busca. "
            "Posso te conectar com um corretor para combinar a visita."
        )

    abertura = (
        "Se quiser, já marco uma visita a alguma delas com um corretor."
        if apos_opcoes
        else "Já tenho o essencial da sua busca. Podemos combinar uma visita ou conversa com um corretor."
    )
    linhas = [
        abertura,
        "Tenho estes horários:",
        _lista_horarios(horarios),
        "Qual funciona melhor para você? Se preferir outro dia/horário, me fala.",
    ]

    if pedir_email:
        linhas.append(_PEDE_EMAIL)

    return "\n".join(linhas)


_ID_IMOVEL = re.compile(r"\bBR-[A-Z]{2}-\d{3}\b", re.IGNORECASE)

_MOTIVO_HORARIO_INVALIDO = {
    "passado": "Esse horário já passou (ou está muito em cima).",
    "domingo": "Domingo não temos corretor de plantão.",
    "fora_expediente": "As visitas acontecem entre 8h e 19h.",
}


def _falas_agente(estado: dict[str, Any]) -> list[str]:
    """Falas do agente, da mais recente para a mais antiga."""
    return [
        str(m.get("texto") or "")
        for m in reversed(estado.get("mensagens") or [])
        if m.get("papel") == "agente"
    ]


def _ultima_fala_agente(estado: dict[str, Any]) -> str:
    falas = _falas_agente(estado)
    return falas[0] if falas else ""


def _horarios_ofertados(estado: dict[str, Any], *, falas: int) -> list[str]:
    """Horários das últimas `falas` do agente: o lead pode tirar uma dúvida antes de escolher."""
    for fala in _falas_agente(estado)[:falas]:
        proposto = _horario_proposto(fala)
        if proposto:
            return [proposto]
        horarios = horarios_no_texto(fala)
        if horarios:
            return horarios
    return []


def _tipo_agendamento(texto: str) -> str:
    t = texto.lower()
    termos = ("reunião", "reuniao", "conversa", "ligação", "ligacao", "online", "videochamada", "call")
    return "reuniao" if any(p in t for p in termos) else "visita"


def _imovel_do_contexto(estado: dict[str, Any], texto: str) -> str | None:
    m = _ID_IMOVEL.search(texto)
    sugeridos = list(estado.get("imoveis_sugeridos") or [])
    recentes = [m.get("texto") or "" for m in (estado.get("mensagens") or [])[-6:] if m.get("papel") == "lead"]
    # "quero ver a de Pinheiros": o bairro ou a rua citados escolhem entre as opções mostradas.
    citados = []
    for t in (normalizar_texto(x) for x in [texto, *reversed(recentes)]):
        for imovel_id in sugeridos:
            imovel = obter_imovel(imovel_id) or {}
            nomes = (imovel.get("bairro"), imovel.get("regiao"), str(imovel.get("endereco") or "").split(",")[0])
            if any(n and re.search(rf"\b{re.escape(normalizar_texto(str(n)))}\b", t) for n in nomes):
                citados.append(imovel_id)
        if citados:
            break
    candidatos = ([m.group(0).upper()] if m else []) + citados[:1] + sugeridos
    return next((c for c in candidatos if obter_imovel(c)), None)


def _primeiro_nome(estado: dict[str, Any]) -> str:
    return vocativo(str((estado.get("perfil") or {}).get("nome") or "").strip())


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
    dados = extrair_dados_deterministicos(
        texto, {}, campo_aguardando=None, ultimo_campo_preenchido=None
    )
    return bool(dados) or _so_saudacao(texto) or _quer_agendar(texto)


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
            prazer = f"Prazer, {vocativo(nome)}! " if nome else ""
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
    # Com visita marcada, só vale a última fala: senão um "sim" remarcaria pela oferta antiga.
    ofertados = _horarios_ofertados(estado, falas=1 if ativo else 2)

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


def _visita_marcada(estado: dict[str, Any]) -> str:
    ativo = agendamento_ativo(estado)
    inicio = inicio_do(ativo) if ativo else None
    return formatar_humano(inicio) if inicio else ""


def _oferta_de_visita(estado: dict[str, Any], *, apos_opcoes: bool) -> str:
    """Horários livres do corretor; com e-mail em mãos, propõe um só e reserva no "sim"."""
    perfil = estado.get("perfil") or {}
    if perfil.get("email"):
        horarios = sugerir_horarios(1)
        if horarios:
            return _proposta_um_toque(estado, horarios[0])
    return _oferecer_agenda(
        sugerir_horarios(3),
        pedir_email=not perfil.get("email"),
        apos_opcoes=apos_opcoes,
    )


# ---------------------------------------------------------------- busca

def _buscar_por_perfil(
    perfil: dict[str, Any],
) -> dict[str, Any]:
    regiao = None if perfil.get("regiao_flexivel") else perfil.get("regiao")
    quartos = None if perfil.get("quartos_flexivel") else perfil.get("quartos")

    if perfil.get("faixa_preco_flexivel") or perfil.get("ticket_flexivel"):
        preco_max = None
    else:
        preco_max = perfil.get("faixa_preco") or perfil.get("ticket")

    return buscar_resultado(
        intencao=perfil.get("intencao"),
        regiao=regiao,
        quartos_min=int(quartos) if quartos is not None else None,
        preco_max=float(preco_max) if preco_max is not None else None,
    )


_FECHO_RESULTADO = "Quer ver alguma dessas, ajustar algum ponto da busca ou marcar uma visita?"


def _resposta_resultado(
    perfil: dict[str, Any],
    resultado: dict[str, Any],
    *,
    fecho: str = _FECHO_RESULTADO,
) -> tuple[str, list[dict[str, Any]], bool, str, str]:
    sugestoes = resultado.get("imoveis") or []
    match = str(resultado.get("match") or "vazio")
    motivo = str(resultado.get("motivo") or "")

    if sugestoes:
        partes: list[str] = []

        if match == "aproximado":
            partes.append(_frase_aproximacao(motivo, len(sugestoes[:3])))
        else:
            partes.append("Encontrei estas opções para o seu perfil:")

        for imovel in sugestoes[:3]:
            partes.append(formatar_imovel(imovel))

        partes.append(fecho)

        return "\n\n".join(partes), sugestoes, True, match, motivo

    return (
        _resposta_sem_resultado(perfil, resultado.get("pistas") or {}),
        [],
        False,
        "vazio",
        motivo,
    )


def _no_lugar(regiao: str) -> str:
    """'na Zona Sul', 'no Centro', 'em Moema'."""
    r = regiao.strip().lower()
    nome = regiao.strip().title()
    if r.startswith(("zona ", "asa ", "vila ")):
        return f"na {nome}"
    if r in {"centro", "lago sul", "lago norte", "brooklin", "itaim bibi"}:
        return f"no {nome}"
    return f"em {nome}"


def _lista_com_e(itens: list[str]) -> str:
    return itens[0] if len(itens) == 1 else ", ".join(itens[:-1]) + f" e {itens[-1]}"


def _frase_aproximacao(motivo: str, quantidade: int) -> str:
    """'está em X; tem 1 quarto' (fragmentos do catálogo) -> frase de corretor."""
    abertura = (
        "Não achei exatamente o que você pediu, mas tenho "
        + ("uma opção bem próxima." if quantidade == 1 else "opções bem próximas.")
    )
    pedacos = [p.strip() for p in (motivo or "").split(";") if p.strip()]
    if not pedacos:
        return abertura
    texto = _lista_com_e(pedacos)
    if re.match(r"(está|fica|tem|é) ", texto):
        sujeito = "Ela" if quantidade == 1 else "A primeira"
        return f"{abertura} {sujeito} {texto}."
    return f"{abertura} {texto[0].upper()}{texto[1:]}."


def _resposta_sem_resultado(perfil: dict[str, Any], pistas: dict[str, Any]) -> str:
    """Diz em palavras simples o que não achou e sugere o ajuste com mais chance de dar certo."""
    regiao = None if perfil.get("regiao_flexivel") else perfil.get("regiao")
    quartos = None if perfil.get("quartos_flexivel") else perfil.get("quartos")
    preco = perfil.get("faixa_preco") or perfil.get("ticket")

    pedido = []
    if quartos is not None:
        pedido.append(f"com {_descrever_quartos(int(quartos))}" if quartos else _descrever_quartos(0))
    if regiao:
        pedido.append(_no_lugar(str(regiao)))
    if preco:
        pedido.append(f"até {_fmt_moeda(float(preco))}")
    abertura = f"Não encontrei nada {' '.join(pedido)} por enquanto." if pedido else "Não encontrei o que você procura por enquanto."

    menor = pistas.get("menor_preco_regiao")
    outras = [o["nome"] for o in pistas.get("outras_regioes") or []]

    if perfil.get("regiao_flexivel"):
        abertura = f"Procurei em todas as regiões que atendo e não encontrei nada {' '.join(pedido)}." if pedido else (
            "Procurei em todas as regiões que atendo e não encontrei o que você procura."
        )
        if menor and preco and menor > float(preco):
            return f"{abertura} O mais em conta que tenho hoje sai por {_fmt_moeda(menor)}. Quer que eu busque até esse valor?"
        return f"{abertura} Vamos ajustar o valor ou a quantidade de quartos?"

    if regiao and menor and preco and menor > float(preco):
        texto = f"{abertura} Por lá, o mais em conta que tenho hoje sai por {_fmt_moeda(menor)}."
        if outras:
            return f"{texto} Dentro do seu valor, tenho opções {_lista_com_e([_no_lugar(o) for o in outras])}. Quer que eu procure por lá?"
        return f"{texto} Dá pra aumentar um pouco o valor, ou prefere que eu olhe outra região?"

    if outras:
        return f"{abertura} Dentro do seu valor, tenho opções {_lista_com_e([_no_lugar(o) for o in outras])}. Quer que eu procure por lá?"

    if regiao:
        return f"{abertura} Vamos ajustar a região ou o valor?"
    return f"{abertura} Vamos ajustar o valor ou a quantidade de quartos?"


_DEIXO_PRO_CORRETOR = "Essa eu deixo pro corretor te responder, pra não te passar nada errado."

_INTERROGATIVAS = re.compile(r"^(?:como|quanto|quanta|quantos|quantas|qual|quais|quando|onde|por ?que|o que|tem|posso|da pra|e se)\b")


def _parece_pergunta(mensagem: str) -> bool:
    return "?" in mensagem or bool(_INTERROGATIVAS.match(normalizar_texto(mensagem)))


# "Tem mais opções?" é sobre a busca, que o agente responde; não é dúvida pro corretor.
_SOBRE_OPCOES = re.compile(
    r"\b(?:opc\w*|alternativ\w*)\b|\b(?:mais|outr[ao]s?)\s+(?:imove\w*|apartament\w*|aptos?|casas?)\b"
)

_ESPERA_AVISO = re.compile(
    r"\b(?:me avis[ae]|avisa (?:ai|quando)|vou esperar|vou aguardar|aguardo|fico no aguardo|"
    r"quando (?:tiver|aparecer|surgir)|se (?:tiver|aparecer|surgir) algo)\b"
)

_EXEMPLOS = {
    "intencao": "\"comprar\", \"alugar\" ou \"investir\"",
    "regiao": "\"Zona Sul\", \"Moema\" ou \"Asa Norte\"",
    "faixa_preco": "\"até 800 mil\" ou \"3 mil por mês\"",
    "quartos": "\"2 quartos\"",
    "urgencia": "\"urgente\", \"uns 6 meses\" ou \"sem pressa\"",
    "ticket": "\"500 mil\"",
    "perfil": "\"renda\" ou \"valorização\"",
    "retorno_esperado": "\"6% ao ano\"",
}


def _falas_recentes_agente(estado: dict[str, Any], n: int) -> list[str]:
    falas = [str(m.get("texto") or "") for m in estado.get("mensagens") or [] if m.get("papel") != "lead"]
    return falas[-n:]


def _ultima_fala_agente(estado: dict[str, Any]) -> str:
    return next(iter(_falas_recentes_agente(estado, 1)), "")


def _insistir_sem_resultado(
    perfil: dict[str, Any],
    controle: dict[str, Any],
    mensagem: str,
    *,
    pediu_outra_regiao: bool = False,
) -> str:
    """Resposta sem dado novo depois de uma busca vazia: cada insistência avança, nunca repete."""
    usadas = controle.setdefault("insistencias_vazia", [])
    vazia = controle.get("ultima_busca_vazia")
    preco = controle.get("preco_sugerido") if vazia else None
    regiao = None if perfil.get("regiao_flexivel") else perfil.get("regiao")

    if _ESPERA_AVISO.search(normalizar_texto(mensagem)):
        if controle.get("avisar_novidades"):
            return "Fechado! Qualquer novidade a gente te chama. Até mais!"
        controle["avisar_novidades"] = True
        return (
            "Combinado! Deixo anotado pro corretor te avisar assim que aparecer algo nesse perfil. "
            "Se quiser mudar a busca antes disso, é só me falar."
        )

    if vazia and pediu_outra_regiao and perfil.get("regiao_flexivel") and "todas" not in usadas:
        usadas.append("todas")
        texto = "Já procurei em todas as regiões que atendo, então mudar de região não vai trazer opção nova."
        if preco:
            controle["oferta_preco"] = preco
            return f"{texto} O que destrava a busca é o valor: a partir de {_fmt_moeda(float(preco))} já tenho opção. Quer que eu busque até esse valor?"
        return f"{texto} Prefere ajustar o valor ou a quantidade de quartos?"

    if not vazia and "mesmas" not in usadas:
        chave = "mesmas"
    elif not usadas and preco and not negativo(mensagem):
        chave = "preco"
    elif "mudar" not in usadas:
        chave = "mudar"
    else:
        chave = "fecho" if usadas[-1] != "fecho" else "fecho2"
    usadas.append(chave)

    if chave == "mesmas":
        return (
            "Por enquanto, essas que te mandei são as opções mais próximas do que você pediu. "
            "Quer marcar uma visita a alguma delas, ou prefere que eu ajuste o valor, a região ou os quartos?"
        )
    if chave == "preco":
        controle["oferta_preco"] = preco
        lugar = f" {_no_lugar(str(regiao))}" if regiao else ""
        return f"Uma ideia: subindo o valor para {_fmt_moeda(float(preco))}, já tenho opção{lugar}. Quer que eu te mostre?"
    if chave == "mudar":
        return "Pra eu achar algo pra você, me diz o que prefere mudar: o valor, a região ou a quantidade de quartos."
    if chave == "fecho":
        return (
            "Tudo bem! Quando quiser, é só me dizer um novo valor, região ou número de quartos "
            "que eu busco de novo pra você."
        )
    return "Tô por aqui! Se mudar alguma coisa na busca, me avisa que eu procuro na hora."


def _finalizar(
    *,
    estado: dict[str, Any],
    lead_id: str,
    resposta: str,
    qual_antes: dict[str, Any],
    imoveis: list[dict[str, Any]] | None = None,
    exibir_imoveis: bool = False,
    match_busca: str = "nao_realizada",
    motivo_busca: str = "",
    fora_de_escopo: bool = False,
    usou_llm: bool = False,
    evento: str | None = None,
    nome_novo: str = "",
    pedir_nome: bool = False,
) -> dict[str, Any]:
    primeiro = vocativo(nome_novo)
    if primeiro and primeiro not in resposta:
        resposta = f"Prazer, {primeiro}! {resposta}"
    resposta = _pedir_nome_se_primeira(resposta, estado.get("perfil") or {}, primeira=pedir_nome)

    memoria.adicionar_mensagem(estado, "agente", resposta)

    qual = score_estado(estado)
    resumo = montar_resumo(estado)

    if evento:
        crm = sincronizar_crm(estado, resumo, evento=evento)
    else:
        crm = sincronizar_crm(estado, resumo, qual_antes=qual_antes)

    memoria.salvar(estado)

    return {
        "lead_id": lead_id,
        "resposta": resposta,
        "perfil": estado.get("perfil") or {},
        "qualificacao": qual,
        "imoveis": imoveis or [],
        "exibir_imoveis": exibir_imoveis,
        "match_busca": match_busca,
        "motivo_busca": motivo_busca,
        "agendamento": _agendamento_publico(estado),
        "resumo_corretor": resumo,
        "usou_llm": usou_llm,
        "crm": crm,
        "fora_de_escopo": fora_de_escopo,
    }


def processar_mensagem(
    lead_id: str,
    mensagem: str,
) -> dict[str, Any]:
    estado = memoria.carregar(lead_id)
    estado.setdefault("perfil", {})

    perfil_antes = dict(estado.get("perfil") or {})
    primeira = _primeira_interacao(estado)
    qual_antes = score_estado(estado)
    controle = _controle(estado)

    campo_aguardando = controle.get("campo_aguardando")
    ultimo_campo = controle.get("ultimo_campo_preenchido")

    memoria.adicionar_mensagem(estado, "lead", mensagem)

    # Nome/e-mail e escolha de horário vêm antes da qualificação:
    # "o segundo" ou "sim" não são dados do perfil.
    agenda, email_novo, nome_novo = _tratar_contato(estado, mensagem)
    if agenda is None:
        agenda = _tratar_agenda(estado, mensagem, email_novo)
    if agenda:
        return _finalizar(
            estado=estado,
            lead_id=lead_id,
            resposta=agenda["resposta"],
            qual_antes=qual_antes,
            evento=agenda["evento"],
            nome_novo=nome_novo or "",
        )

    nome_novo = nome_novo or ""
    perfil_base = dict(estado.get("perfil") or {})

    # Saudação pura: não manda ao catálogo nem inventa intenção.
    if _so_saudacao(mensagem) and not perfil_antes:
        controle["campo_aguardando"] = "intencao"

        resposta = (
            "Oi! Sou o assistente da imobiliária. "
            "Te ajudo a encontrar o imóvel ideal e, se fizer sentido, "
            "também posso encaminhar uma visita com um corretor.\n\n"
            "Você está buscando comprar, alugar ou investir?"
        )

        return _finalizar(
            estado=estado,
            lead_id=lead_id,
            resposta=resposta,
            qual_antes=qual_antes,
            pedir_nome=primeira,
        )

    interpretacao = interpretar_mensagem(
        mensagem,
        perfil_base,
        campo_aguardando=campo_aguardando,
        ultimo_campo_preenchido=ultimo_campo,
    )

    categoria = interpretacao.get("categoria") or "outro"
    correcao = bool(interpretacao.get("correcao"))
    dados = interpretacao.get("dados") or {}
    usou_llm = bool(interpretacao.get("usou_llm"))

    # "sim"/"não" para "tenho opções em X, quer que eu procure por lá?"
    # ou para "subindo o valor para R$ Y, já tenho opção. Quer que eu te mostre?"
    sugeridas = controle.pop("regioes_sugeridas", None) or []
    oferta_preco = controle.pop("oferta_preco", None)
    if oferta_preco and not dados and afirmativo(mensagem):
        campo_preco = "ticket" if perfil_base.get("intencao") == "investimento" else "faixa_preco"
        dados = {campo_preco: float(oferta_preco)}
        categoria = "dados"
    elif sugeridas and dados.get("regiao_flexivel") and not dados.get("regiao"):
        dados = {**dados, "regiao": sugeridas[0]["regiao"], "regiao_flexivel": False}
    elif sugeridas and not dados:
        if afirmativo(mensagem):
            dados = {"regiao": sugeridas[0]["regiao"], "regiao_flexivel": False}
            categoria = "dados"
        elif negativo(mensagem):
            return _finalizar(
                estado=estado,
                lead_id=lead_id,
                resposta="Sem problema. Prefere ajustar o valor ou a quantidade de quartos?",
                qual_antes=qual_antes,
                usou_llm=usou_llm,
            )

    # Fora de escopo: preserva 100% do perfil e da etapa.
    if categoria == "fora_escopo" and not dados and not (email_novo or nome_novo):
        proxima = pergunta_para(proximo_campo(perfil_base))
        resposta = _resposta_fora_escopo(
            proxima_pergunta=proxima,
        )

        return _finalizar(
            estado=estado,
            lead_id=lead_id,
            resposta=resposta,
            qual_antes=qual_antes,
            fora_de_escopo=True,
            usou_llm=usou_llm,
        )

    perfil, alteracoes = reconciliar_perfil(
        perfil_base,
        dados,
    )

    estado["perfil"] = perfil

    # "quero alugar na Asa Norte... e vai chover amanhã?": usa os dados e reconhece o resto.
    ressalva = "Sobre o resto eu fico devendo, mas da sua busca eu cuido! " if (
        alteracoes and mensagem_fora_de_escopo(mensagem)
    ) else ""

    ultimo_alterado = _campo_principal_alterado(alteracoes)

    if ultimo_alterado:
        controle["ultimo_campo_preenchido"] = ultimo_alterado

    # A cada mensagem recalculamos do zero o que falta.
    # Não importa qual era a pergunta anterior se o usuário trouxe outra informação.
    proximo = proximo_campo(perfil)
    controle["campo_aguardando"] = proximo

    # Dúvida imobiliária no meio do fluxo:
    # responde e retoma o próximo campo sem perder qualquer dado fornecido junto.
    pergunta_sem_tema = False
    if categoria == "duvida_imobiliaria":
        pergunta = pergunta_para(proximo)
        resposta = _resposta_duvida_imobiliaria(
            mensagem,
            proxima_pergunta=pergunta,
        )
        if resposta and any(resposta.split("\n\n")[0] in f for f in _falas_recentes_agente(estado, 3)):
            resposta = None  # já explicou isso agora há pouco; repetir soa robótico
        if resposta is None:
            pergunta_sem_tema = (
                not alteracoes
                and _parece_pergunta(mensagem)
                and not _SOBRE_OPCOES.search(normalizar_texto(mensagem))
            )
            categoria = "dados" if alteracoes else "outro"
        else:
            ack = _ack_alteracoes(alteracoes, correcao=correcao, variacao=len(estado["mensagens"]) // 2)
            if ack:
                resposta = f"{ack}\n\n{resposta}"

    if categoria == "duvida_imobiliaria":
        return _finalizar(
            estado=estado,
            lead_id=lead_id,
            resposta=resposta,
            qual_antes=qual_antes,
            usou_llm=usou_llm,
            nome_novo=nome_novo,
        )

    # Ainda qualificando.
    if proximo:
        ack = _ack_alteracoes(
            alteracoes,
            correcao=correcao,
            variacao=len(estado["mensagens"]) // 2,
        )

        pergunta = pergunta_para(proximo) or "Pode me contar um pouco mais sobre sua busca?"

        if ack:
            resposta = f"{ressalva}{ack}\n\n{pergunta}"
        elif email_novo:
            resposta = f"Anotei seu e-mail. {pergunta}"
        elif proximo == "retorno_esperado" and (
            prazo := re.search(r"\b(\d+)\s*anos?\b", normalizar_texto(mensagem))
        ):
            resposta = (
                f"Entendi, pensando num prazo de {prazo.group(1)} anos. "
                "E de retorno, quanto você espera? Por exemplo, 6% ao ano."
            )
        elif _quer_agendar(mensagem) and categoria == "outro":
            resposta = f"Consigo marcar, sim! Antes, só preciso saber: {pergunta[0].lower()}{pergunta[1:]}"
        elif pergunta_sem_tema and not _ultima_fala_agente(estado).startswith(_DEIXO_PRO_CORRETOR):
            resposta = f"{_DEIXO_PRO_CORRETOR} {pergunta}"
        elif categoria == "outro" and not nome_novo:
            if _ultima_fala_agente(estado).startswith("Desculpa, não entendi bem.") and proximo in _EXEMPLOS:
                resposta = f"{pergunta} Pode responder do seu jeito, por exemplo: {_EXEMPLOS[proximo]}."
            else:
                resposta = f"Desculpa, não entendi bem. {pergunta}"
        else:
            resposta = pergunta

        return _finalizar(
            estado=estado,
            lead_id=lead_id,
            resposta=resposta,
            qual_antes=qual_antes,
            usou_llm=usou_llm,
            nome_novo=nome_novo,
            pedir_nome=primeira,
        )

    # Qualificação completa.
    controle["campo_aguardando"] = None
    agendado = _visita_marcada(estado)

    # Se a busca mudou na mesma mensagem, mostra o resultado primeiro; a oferta de visita vem no fecho.
    if _quer_agendar(mensagem) and not alteracoes:
        if agendado:
            resposta = (
                f"Sua visita já está marcada para {agendado}. "
                "Se quiser mudar, me diga o novo dia e horário."
            )
        else:
            resposta = _oferta_de_visita(estado, apos_opcoes=False)

        return _finalizar(
            estado=estado,
            lead_id=lead_id,
            resposta=resposta,
            qual_antes=qual_antes,
            usou_llm=usou_llm,
            nome_novo=nome_novo,
        )

    # Sem dado novo, a busca daria o mesmo resultado: em vez de repetir, avança a conversa.
    if not alteracoes and (controle.get("ultima_busca_vazia") or controle.get("ultimos_ids")):
        resposta = _insistir_sem_resultado(
            perfil,
            controle,
            mensagem,
            pediu_outra_regiao=bool(dados.get("regiao_flexivel")),
        )
        if pergunta_sem_tema and not resposta.startswith("Já procurei"):
            resposta = f"{_DEIXO_PRO_CORRETOR} {resposta}"
        return _finalizar(
            estado=estado,
            lead_id=lead_id,
            resposta=resposta,
            qual_antes=qual_antes,
            usou_llm=usou_llm,
        )

    # "não gostei"/"não" após a busca não deve repetir a mesma busca sem sentido.
    t = normalizar_texto(mensagem)

    if not alteracoes and t in {
        "nao",
        "nao gostei",
        "nenhuma",
        "nenhum",
        "quero outra",
        "outra opcao",
    }:
        resposta = (
            "Sem problema. O que você prefere mudar: região, valor ou quantidade de quartos?"
        )

        return _finalizar(
            estado=estado,
            lead_id=lead_id,
            resposta=resposta,
            qual_antes=qual_antes,
            usou_llm=usou_llm,
        )

    if agendado:
        fecho = f"Sua visita segue marcada para {agendado}. Quer ver mais alguma opção até lá?"
    elif score_estado(estado).get("pronto_para_agendar") and not ADIA_AGENDA.search(normalizar_texto(mensagem)):
        fecho = _oferta_de_visita(estado, apos_opcoes=True)
    else:
        fecho = _FECHO_RESULTADO

    # Só aqui o catálogo é consultado.
    resultado = _buscar_por_perfil(perfil)

    resposta, sugestoes, mostrar, match, motivo = _resposta_resultado(
        perfil,
        resultado,
        fecho=fecho,
    )

    controle["ultima_busca_vazia"] = match == "vazio"
    controle["insistencias_vazia"] = []
    controle["ultimos_ids"] = [im.get("id") for im in sugestoes if im.get("id")] if mostrar else []
    if match == "vazio":
        pistas = resultado.get("pistas") or {}
        controle["regioes_sugeridas"] = pistas.get("outras_regioes") or []
        preco_atual = perfil.get("faixa_preco") or perfil.get("ticket")
        menor = pistas.get("menor_preco_regiao")
        controle["preco_sugerido"] = menor if menor and preco_atual and menor > float(preco_atual) else None
        if perfil.get("regiao_flexivel") and controle["preco_sugerido"]:
            controle["oferta_preco"] = controle["preco_sugerido"]
            controle["insistencias_vazia"] = ["preco"]
    else:
        ack = _ack_alteracoes(alteracoes, correcao=correcao, variacao=len(estado["mensagens"]) // 2)
        if ack:
            resposta = f"{ack}\n\n{resposta}"
    resposta = f"{ressalva}{resposta}"

    estado["imoveis_sugeridos"] = [
        imovel.get("id")
        for imovel in sugestoes
        if imovel.get("id") is not None
    ]

    return _finalizar(
        estado=estado,
        lead_id=lead_id,
        resposta=resposta,
        qual_antes=qual_antes,
        imoveis=sugestoes if mostrar else [],
        exibir_imoveis=mostrar,
        match_busca=match,
        motivo_busca=motivo,
        usou_llm=usou_llm,
        nome_novo=nome_novo,
    )


def follow_up(lead_id: str) -> dict[str, Any]:
    """Retoma a conversa preservando o estado real do lead."""
    estado = memoria.carregar(lead_id)
    estado.setdefault("perfil", {})

    perfil = estado.get("perfil") or {}
    controle = _controle(estado)

    proximo = proximo_campo(perfil)
    controle["campo_aguardando"] = proximo
    agendado = _visita_marcada(estado)

    if agendado:
        texto = (
            f"Oi! Passando para lembrar que sua visita está marcada para {agendado}. "
            "Se precisar mudar, é só me avisar."
        )

    elif proximo:
        pergunta = pergunta_para(proximo) or "Quer continuar sua busca?"

        if perfil.get("intencao") or perfil.get("regiao"):
            texto = f"Oi! Retomando sua busca: {pergunta}"
        else:
            texto = f"Oi! Vamos continuar de onde paramos. {pergunta}"

    elif qualificacao_concluida(perfil):
        texto = (
            "Oi! Já tenho o essencial da sua busca. "
            "Se quiser, posso retomar as opções ou encaminhar uma visita com um corretor."
        )

    else:
        texto = "Oi! Quer continuar sua busca de imóvel?"

    memoria.adicionar_mensagem(
        estado,
        "agente",
        texto,
    )
    memoria.salvar(estado)

    return {
        "lead_id": lead_id,
        "resposta": texto,
        "qualificacao": score_estado(estado),
    }
