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
- LLM é opcional: Python controla estado, fluxo e busca.
"""

from __future__ import annotations

import re
from typing import Any

from src.agenda.scheduler import sugerir_horarios
from src.crm.cliente import sincronizar as sincronizar_crm
from src.imoveis.catalogo import buscar_resultado, formatar_imovel
from src.memoria import conversa as memoria
from src.qualificacao.fluxo_conversa import (
    pergunta_para,
    proximo_campo,
    qualificacao_concluida,
)
from src.qualificacao.interpretador import (
    interpretar_mensagem,
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


def _quer_agendar(texto: str) -> bool:
    t = normalizar_texto(texto)

    return any(
        termo in t
        for termo in (
            "agendar",
            "agendamento",
            "marcar visita",
            "quero visitar",
            "quero ver o imovel",
            "quero ver o apartamento",
            "reuniao",
            "falar com corretor",
            "conhecer o imovel",
        )
    )


def _fmt_moeda(valor: float) -> str:
    v = float(valor)

    if v >= 1_000_000:
        mi = v / 1_000_000
        txt = f"{mi:.1f}".rstrip("0").rstrip(".")
        return f"R$ {txt} mi"

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
            q = int(novo)
            partes.append(f"{q} quarto" + ("s" if q != 1 else ""))
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
            partes.append(f"retorno esperado de {novo}")

    return partes


def _ack_alteracoes(
    alteracoes: dict[str, tuple[Any, Any]],
    *,
    correcao: bool,
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

    prefixo = "Certo, atualizei" if (correcao or houve_substituicao) else "Perfeito, anotei"

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
) -> str:
    """Responde dúvidas comuns sem inventar características de imóveis."""
    t = normalizar_texto(mensagem)

    if "financi" in t:
        resposta = (
            "Sim, podemos considerar imóveis com possibilidade de financiamento, "
            "mas as condições dependem do imóvel e da análise da instituição financeira."
        )

    elif any(x in t for x in ("garagem", "vaga", "pet", "cachorro", "gato", "elevador")):
        resposta = (
            "Isso depende do imóvel específico. Quando eu tiver as opções da sua busca, "
            "essa característica precisa ser confirmada nos dados do imóvel."
        )

    elif any(x in t for x in ("condominio", "iptu")):
        resposta = (
            "Esse valor varia por imóvel. Eu só devo informar quando ele estiver disponível "
            "nos dados da opção apresentada."
        )

    elif any(x in t for x in ("visita", "corretor", "agendar")):
        resposta = (
            "Consigo encaminhar uma visita ou conversa com um corretor assim que tivermos "
            "o essencial da sua busca."
        )

    else:
        resposta = (
            "Posso te ajudar com essa dúvida dentro do contexto imobiliário. "
            "Quando ela depender de um imóvel específico, eu só confirmo usando os dados da opção."
        )

    if proxima_pergunta:
        resposta += f" Para seguir com a busca: {proxima_pergunta}"

    return resposta


def _oferecer_agenda() -> str:
    horarios = sugerir_horarios(3)

    if not horarios:
        return (
            "Já tenho o essencial da sua busca. "
            "Posso te conectar com um corretor para combinar a visita."
        )

    linhas = [
        "Já tenho o essencial da sua busca. Podemos combinar uma visita ou conversa com um corretor.",
        "Tenho estes horários:",
    ]

    for h in horarios:
        linhas.append(f"• {h}")

    linhas.append("Qual funciona melhor para você?")

    return "\n".join(linhas)


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


def _resposta_resultado(
    perfil: dict[str, Any],
    resultado: dict[str, Any],
) -> tuple[str, list[dict[str, Any]], bool, str, str]:
    sugestoes = resultado.get("imoveis") or []
    match = str(resultado.get("match") or "vazio")
    motivo = str(resultado.get("motivo") or "")

    if sugestoes:
        partes: list[str] = []

        if match == "aproximado":
            if motivo:
                partes.append(f"Não encontrei o filtro exato. {motivo}.")
            else:
                partes.append("Não encontrei o filtro exato, mas achei opções próximas.")
        else:
            partes.append("Encontrei estas opções para o seu perfil:")

        for imovel in sugestoes[:3]:
            partes.append(formatar_imovel(imovel))

        partes.append(
            "Quer ver alguma dessas, ajustar algum ponto da busca ou marcar uma visita?"
        )

        return "\n\n".join(partes), sugestoes, True, match, motivo

    return (
        "Não encontrei uma opção com esse conjunto de filtros agora. "
        "Podemos ajustar região, valor ou quantidade de quartos — o que você prefere mudar?",
        [],
        False,
        "vazio",
        motivo,
    )


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
) -> dict[str, Any]:
    memoria.adicionar_mensagem(estado, "agente", resposta)

    qual = score_estado(estado)
    resumo = montar_resumo(estado)

    crm = sincronizar_crm(
        estado,
        resumo,
        qual_antes=qual_antes,
    )

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
    qual_antes = score_estado(estado)
    controle = _controle(estado)

    campo_aguardando = controle.get("campo_aguardando")
    ultimo_campo = controle.get("ultimo_campo_preenchido")

    memoria.adicionar_mensagem(estado, "lead", mensagem)

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
        )

    interpretacao = interpretar_mensagem(
        mensagem,
        perfil_antes,
        campo_aguardando=campo_aguardando,
        ultimo_campo_preenchido=ultimo_campo,
    )

    categoria = interpretacao.get("categoria") or "outro"
    correcao = bool(interpretacao.get("correcao"))
    dados = interpretacao.get("dados") or {}
    usou_llm = bool(interpretacao.get("usou_llm"))

    # Fora de escopo: preserva 100% do perfil e da etapa.
    if categoria == "fora_escopo" and not dados:
        proxima = pergunta_para(proximo_campo(perfil_antes))
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
        perfil_antes,
        dados,
    )

    estado["perfil"] = perfil

    ultimo_alterado = _campo_principal_alterado(alteracoes)

    if ultimo_alterado:
        controle["ultimo_campo_preenchido"] = ultimo_alterado

    # A cada mensagem recalculamos do zero o que falta.
    # Não importa qual era a pergunta anterior se o usuário trouxe outra informação.
    proximo = proximo_campo(perfil)
    controle["campo_aguardando"] = proximo

    # Dúvida imobiliária no meio do fluxo:
    # responde e retoma o próximo campo sem perder qualquer dado fornecido junto.
    if categoria == "duvida_imobiliaria":
        pergunta = pergunta_para(proximo)
        resposta = _resposta_duvida_imobiliaria(
            mensagem,
            proxima_pergunta=pergunta,
        )

        return _finalizar(
            estado=estado,
            lead_id=lead_id,
            resposta=resposta,
            qual_antes=qual_antes,
            usou_llm=usou_llm,
        )

    # Ainda qualificando.
    if proximo:
        ack = _ack_alteracoes(
            alteracoes,
            correcao=correcao,
        )

        pergunta = pergunta_para(proximo) or "Pode me contar um pouco mais sobre sua busca?"

        if ack:
            resposta = f"{ack}\n\n{pergunta}"
        elif categoria == "outro":
            resposta = (
                "Não consegui identificar esse dado com segurança. "
                f"{pergunta}"
            )
        else:
            resposta = pergunta

        return _finalizar(
            estado=estado,
            lead_id=lead_id,
            resposta=resposta,
            qual_antes=qual_antes,
            usou_llm=usou_llm,
        )

    # Qualificação completa.
    controle["campo_aguardando"] = None

    if _quer_agendar(mensagem):
        resposta = _oferecer_agenda()

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

    # Só aqui o catálogo é consultado.
    resultado = _buscar_por_perfil(perfil)

    resposta, sugestoes, mostrar, match, motivo = _resposta_resultado(
        perfil,
        resultado,
    )

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
    )


def follow_up(lead_id: str) -> dict[str, Any]:
    """Retoma a conversa preservando o estado real do lead."""
    estado = memoria.carregar(lead_id)
    estado.setdefault("perfil", {})

    perfil = estado.get("perfil") or {}
    controle = _controle(estado)

    proximo = proximo_campo(perfil)
    controle["campo_aguardando"] = proximo

    if proximo:
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