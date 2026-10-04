"""Agente SDR: intenção, qualificação, busca de imóveis e resposta (LLM opcional)."""
from __future__ import annotations

import json
import re
from typing import Any

import config
from src.agenda.scheduler import sugerir_horarios
from src.imoveis.catalogo import buscar_resultado, formatar_imovel
from src.memoria import conversa as memoria
from src.crm.cliente import sincronizar as sincronizar_crm
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
            txt = f"{mi:.1f}".rstrip("0").rstrip(".")
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

    m_mil = re.search(
        r"(?:até|ate|max(?:imo)?|no máximo|ticket(?:\s*de)?)\s*r?\$?\s*([\d\.]+)\s*mil\b",
        t,
    )
    if not m_mil:
        m_mil = re.search(r"([\d\.]+)\s*mil\b", t)
    if m_mil:
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


def _oferecer_agenda(sugestoes: list[dict[str, Any]]) -> str:
    horarios = sugerir_horarios(3)
    linhas = [
        "Acho que já tenho o essencial do seu perfil.",
        "Que tal marcarmos uma conversa rápida ou uma visita com um corretor?",
        "Horários que posso oferecer:",
    ]
    for h in horarios:
        linhas.append(f"• {h}")
    linhas.append("Qual desses te encaixa melhor? Se preferir outro dia/horário, me fala.")
    if sugestoes:
        linhas.insert(
            1,
            "Posso já alinhar a visita em cima das opções que separamos.",
        )
    return "\n".join(linhas)


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
    elif (
    match_busca == "vazio"
    and not campos_faltantes(perfil)
    and pode_sugerir_imoveis(perfil)
    ):
        partes.append(
            "Não tenho imóvel com esse filtro no estoque agora. "
            "Me diga outra região ou quantidade de quartos que eu busco de novo."
    )

    if pergunta and not (mostrar_imoveis and sugestoes):
        partes.append(pergunta)
    elif qual.get("pronto_para_agendar") or _quer_agendar(mensagem):
        if not (mostrar_imoveis and sugestoes):
            partes.append(_oferecer_agenda([]))
        else:
            partes.append(_oferecer_agenda(sugestoes))
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
    qualificando: bool = False,
    proxima: str | None = None,
) -> str | None:
    if not config.OPENAI_API_KEY:
        return None
    try:
        from openai import OpenAI

        client = OpenAI(api_key=config.OPENAI_API_KEY)
        catalogo_txt = "\n".join(formatar_imovel(i) for i in sugestoes) or "(lista vazia — NÃO invente imóveis)"
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
            "- Se a lista estiver vazia E a busca já tiver sido realizada: "
            "diga que não encontrou esse filtro e peça outro. "
            "Se estiver qualificando, ignore a lista vazia e faça apenas a próxima pergunta.\n"
            "(região ou quartos). NÃO sugira '7, 8 ou 9 quartos' se isso não estiver na lista.\n"
            "- Se match for aproximado: diga em 1 frase que não tem o exato, mostre "
            "o que TEM (só da lista) e pergunte se quer ver/ajustar.\n"
            "- Proibido jargão: match, lead score, perfil completo, estoque filtrado.\n"
            "- Não se apresente de novo se a conversa já começou.\n"
            "- Fora de escopo: recuse e volte para imóveis.\n"
            "- Durante a qualificação, NÃO apresente imóveis.\n"
            "- Durante a qualificação, faça SOMENTE a próxima pergunta indicada.\n"
            "- Não faça duas perguntas na mesma mensagem.\n"
            "- Se a próxima pergunta estiver vazia, responda naturalmente sem inventar uma nova etapa do funil.\n"
        )
        user = (
            f"Primeira mensagem: {'sim' if primeira else 'não'}\n"
            f"Fora de escopo: {'sim' if fora_de_escopo else 'não'}\n"
            f"Pronto para agendar: {'sim' if pronto_para_agendar else 'não'}\n"
            f"Tipo de busca: {match_busca}\n"
            f"Motivo: {motivo_busca or '(n/a)'}\n"
            f"Perfil: {json.dumps(estado.get('perfil') or {}, ensure_ascii=False)}\n"
            f"Histórico:\n{hist_txt}\n"
            f"Imóveis (única fonte de verdade):\n{catalogo_txt}\n\n"
            f"Mensagem do lead: {mensagem}\n"
            f"Qualificando lead: {'sim' if qualificando else 'não'}\n"
            f"Próxima pergunta da qualificação: {proxima or '(nenhuma)'}\n"
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

    fora = mensagem_fora_de_escopo(mensagem, perfil_antes)

    if fora:
        # Não polui o perfil com sinais falsos; não busca catálogo
        perfil = perfil_antes
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

        resposta = resposta_llm or _resposta_fora_de_escopo(
            primeira=primeira
        )

        memoria.adicionar_mensagem(
            estado,
            "agente",
            resposta,
        )

        memoria.salvar(estado)

        return {
            "lead_id": lead_id,
            "resposta": resposta,
            "perfil": perfil,
            "qualificacao": qual,
            "imoveis": [],
            "exibir_imoveis": False,
            "resumo_corretor": montar_resumo(estado),
            "usou_llm": usou_llm,
            "fora_de_escopo": True,
        }

    # Saudação pura: não força intenção; só conversa
    if _so_saudacao(mensagem) and not perfil_antes.get("intencao"):
        perfil = dict(perfil_antes)
        estado["perfil"] = perfil
        qual = score_estado(estado)

        resposta = _resposta_deterministica(
            mensagem,
            estado,
            qual,
            [],
            perfil_antes=perfil_antes,
            mostrar_imoveis=False,
            match_busca="nao_realizada",
        )

        memoria.adicionar_mensagem(
            estado,
            "agente",
            resposta,
        )

        memoria.salvar(estado)

        return {
            "lead_id": lead_id,
            "resposta": resposta,
            "perfil": perfil,
            "qualificacao": qual,
            "imoveis": [],
            "exibir_imoveis": False,
            "match_busca": "nao_realizada",
            "motivo_busca": "",
            "resumo_corretor": montar_resumo(estado),
            "usou_llm": False,
            "fora_de_escopo": False,
        }

    perfil = extrair_sinais(
        mensagem,
        perfil_antes,
    )

    # LLM complementa/corrige a regex
    # (se houver OPENAI_API_KEY); sem chave, nada muda.
    perfil = mesclar_perfil(
        perfil,
        extrair_perfil_llm(
            mensagem,
            perfil,
            estado.get("mensagens"),
        ),
    )

    estado["perfil"] = perfil

    qual = score_estado(estado)

    faltantes = campos_faltantes(perfil)
    qualificando = bool(faltantes)
    proxima = proxima_pergunta(perfil)

    sugestoes: list[dict[str, Any]] = []
    match_busca = "nao_realizada"
    motivo_busca = ""
    mostrar = False

    if (
        not qualificando
        and pode_sugerir_imoveis(perfil)
    ):
        preco_max = (
            perfil.get("faixa_preco")
            or perfil.get("ticket")
        )

        quartos = perfil.get("quartos")

        resultado = buscar_resultado(
            intencao=perfil.get("intencao"),
            regiao=perfil.get("regiao"),
            quartos_min=(
                int(quartos)
                if quartos is not None
                else None
            ),
            preco_max=(
                float(preco_max)
                if preco_max is not None
                else None
            ),
        )

        sugestoes = resultado.get("imoveis") or []

        match_busca = str(
            resultado.get("match") or "vazio"
        )

        motivo_busca = str(
            resultado.get("motivo") or ""
        )

        mostrar = bool(sugestoes) and (
            perfil.get("quartos") is not None
            or perfil.get("faixa_preco") is not None
            or match_busca == "aproximado"
        )

    resposta_llm = _resposta_llm(
        mensagem,
        estado,
        sugestoes if mostrar else [],
        primeira=primeira,
        pronto_para_agendar=bool(
            qual.get("pronto_para_agendar")
        ),
        match_busca=(
            "n/a"
            if qualificando
            else match_busca
        ),
        motivo_busca=(
            ""
            if qualificando
            else motivo_busca
        ),
        qualificando=qualificando,
        proxima=proxima,
    )

    usou_llm = bool(resposta_llm)

    resposta = resposta_llm or _resposta_deterministica(
        mensagem,
        estado,
        qual,
        sugestoes if mostrar else [],
        perfil_antes=perfil_antes,
        mostrar_imoveis=mostrar,
        match_busca=match_busca,
        motivo_busca=motivo_busca,
    )

    memoria.adicionar_mensagem(
        estado,
        "agente",
        resposta,
    )

    resumo = montar_resumo(estado)

    # Envia ao CRM só se prioridade/prontidão mudou nesta mensagem
    crm = sincronizar_crm(
        estado,
        resumo,
        qual_antes=qual_antes,
    )

    memoria.salvar(estado)

    return {
        "lead_id": lead_id,
        "resposta": resposta,
        "perfil": perfil,
        "qualificacao": qual,
        "imoveis": sugestoes if mostrar else [],
        "exibir_imoveis": mostrar,
        "match_busca": (
            "nao_realizada"
            if qualificando
            else match_busca
        ),
        "motivo_busca": (
            motivo_busca
            if mostrar
            else ""
        ),
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

    if pergunta:
        texto += f" {pergunta}"
    elif qual.get("pronto_para_agendar"):
        texto += " Se fizer sentido, já posso te passar horários para uma visita."

    memoria.adicionar_mensagem(estado, "agente", texto)
    memoria.salvar(estado)
    return {"lead_id": lead_id, "resposta": texto, "qualificacao": qual}
