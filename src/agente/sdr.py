"""Agente SDR: intenção, qualificação, busca de imóveis e resposta (LLM opcional)."""
from __future__ import annotations

import json
import re
from typing import Any

import config
from src.agenda.scheduler import sugerir_horarios
from src.imoveis.catalogo import buscar, formatar_imovel
from src.memoria import conversa as memoria
from src.qualificacao.lead import proxima_pergunta, score_lead
from src.resumo.corretor import montar_resumo


def detectar_intencao(texto: str, perfil_atual: dict[str, Any] | None = None) -> str | None:
    t = texto.lower()
    # Renda/retorno/ticket apontam investimento (mesmo se citar "locação").
    if any(p in t for p in ("investir", "investimento", "renda", "yield", "retorno", "ticket")):
        return "investimento"
    if (perfil_atual or {}).get("intencao") == "investimento" and any(
        p in t for p in ("locação", "locacao", "aluguel", "%")
    ):
        return "investimento"
    if any(p in t for p in ("alugar", "aluguel", "locação", "locacao")):
        return "aluguel"
    if any(p in t for p in ("comprar", "compra", "apartamento", "casa", "cobertura")):
        return "compra"
    return None


def extrair_sinais(texto: str, perfil: dict[str, Any]) -> dict[str, Any]:
    """Heurísticas leves para enriquecer o perfil a partir da mensagem."""
    t = texto.lower()
    novo = dict(perfil)

    intencao = detectar_intencao(texto, perfil)
    if intencao:
        novo["intencao"] = intencao

    regioes = {
        "zona sul": "zona sul",
        "zona oeste": "zona oeste",
        "zona norte": "zona norte",
        "zona leste": "zona leste",
        "centro": "centro",
        "moema": "moema",
        "pinheiros": "pinheiros",
        "vila mariana": "vila mariana",
        "itaim": "itaim bibi",
    }
    for chave, valor in regioes.items():
        if chave in t:
            novo["regiao"] = valor
            break

    m_quartos = re.findall(r"(\d+)\s*(?:quartos?|dorms?|dormitórios?)", t)
    if not m_quartos:
        m_quartos = re.findall(r"(\d+)\s*ou\s*(\d+)\s*(?:quartos?|dorms?)", t)
        if m_quartos:
            nums = [int(x) for pair in m_quartos for x in pair]
            novo["quartos"] = min(nums)
    else:
        # "2 ou 3 quartos" -> fica com o menor pedido viável na busca
        nums = [int(x) for x in m_quartos]
        if "ou" in t and len(nums) >= 1:
            # captura também o número antes do "ou"
            m_range = re.search(r"(\d+)\s*ou\s*(\d+)\s*(?:quartos?|dorms?)", t)
            if m_range:
                novo["quartos"] = min(int(m_range.group(1)), int(m_range.group(2)))
            else:
                novo["quartos"] = min(nums)
        else:
            novo["quartos"] = nums[0]

    # Preço: "900 mil", "até R$ 900.000", "ticket de 400 mil"
    m_mil = re.search(r"(?:até|ate|max(?:imo)?|no máximo|ticket(?:\s*de)?)\s*r?\$?\s*([\d\.]+)\s*mil\b", t)
    if not m_mil:
        m_mil = re.search(r"([\d\.]+)\s*mil\b", t)
    if m_mil:
        novo["faixa_preco"] = float(m_mil.group(1).replace(".", "")) * 1000
        if "ticket" in t:
            novo["ticket"] = novo["faixa_preco"]
    else:
        m_preco = re.search(r"(?:até|ate|max(?:imo)?|no máximo|ticket(?:\s*de)?)\s*r?\$?\s*([\d\.]+)", t)
        if m_preco:
            valor = float(m_preco.group(1).replace(".", ""))
            novo["faixa_preco"] = valor
            if "ticket" in t:
                novo["ticket"] = valor

    if any(p in t for p in ("urgente", "essa semana", "o quanto antes", "agora")):
        novo["urgencia"] = "alta"
    elif any(p in t for p in ("sem pressa", "só olhando", "pesquisando")):
        novo["urgencia"] = "baixa"

    m_ret = re.search(r"(\d+[.,]?\d*)\s*%", t)
    if m_ret and (novo.get("intencao") == "investimento" or "retorno" in t or "ao ano" in t):
        novo["retorno_esperado"] = m_ret.group(1).replace(",", ".") + "% a.a."

    if novo.get("intencao") == "investimento" and any(
        p in t for p in ("renda", "locação", "locacao", "aluguel")
    ):
        novo["perfil"] = "renda recorrente"

    return novo


def _resposta_deterministica(
    mensagem: str,
    estado: dict[str, Any],
    qual: dict[str, Any],
    sugestoes: list[dict[str, Any]],
) -> str:
    nome_ctx = estado.get("lead_id", "cliente")
    partes = [
        f"Olá! Sou o assistente SDR da imobiliária. Vou te ajudar com calma, {nome_ctx}."
    ]
    pergunta = proxima_pergunta(estado.get("perfil") or {})
    if sugestoes:
        partes.append("Com o que entendi até agora, estes imóveis batem com o perfil:")
        for im in sugestoes[:3]:
            partes.append(formatar_imovel(im))
    if pergunta:
        partes.append(pergunta)
    elif qual.get("pronto_para_agendar"):
        horarios = sugerir_horarios(3)
        partes.append(
            "Perfil completo. Posso agendar uma conversa/visita. Horários sugeridos: "
            + "; ".join(horarios)
            + ". Qual prefere?"
        )
    else:
        partes.append("Quer que eu refine a busca ou fale com um corretor?")
    return "\n\n".join(partes)


def _resposta_llm(mensagem: str, estado: dict[str, Any], sugestoes: list[dict[str, Any]]) -> str | None:
    if not config.OPENAI_API_KEY:
        return None
    try:
        from openai import OpenAI

        client = OpenAI(api_key=config.OPENAI_API_KEY)
        catalogo_txt = "\n".join(formatar_imovel(i) for i in sugestoes) or "(nenhum imóvel filtrado)"
        system = (
            "Você é um SDR imobiliário brasileiro, cordial e objetivo. "
            "Qualifique o lead (compra, aluguel ou investimento), faça uma pergunta por vez, "
            "mantenha contexto e nunca invente imóveis fora da lista fornecida. "
            "Quando o perfil estiver completo, ofereça agendar reunião/visita. "
            "Respostas curtas, humanizadas, em português."
        )
        user = (
            f"Perfil atual: {json.dumps(estado.get('perfil') or {}, ensure_ascii=False)}\n"
            f"Imóveis candidatos:\n{catalogo_txt}\n\n"
            f"Mensagem do lead: {mensagem}"
        )
        resp = client.chat.completions.create(
            model=config.LLM_MODEL,
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            temperature=0.4,
        )
        return (resp.choices[0].message.content or "").strip() or None
    except Exception:
        return None


def processar_mensagem(lead_id: str, mensagem: str) -> dict[str, Any]:
    estado = memoria.carregar(lead_id)
    memoria.adicionar_mensagem(estado, "lead", mensagem)

    perfil = extrair_sinais(mensagem, estado.get("perfil") or {})
    estado["perfil"] = perfil
    qual = score_lead(perfil)

    preco_max = perfil.get("faixa_preco") or perfil.get("ticket")
    quartos = perfil.get("quartos")
    sugestoes = buscar(
        intencao=perfil.get("intencao"),
        regiao=perfil.get("regiao"),
        quartos_min=int(quartos) if quartos is not None else None,
        preco_max=float(preco_max) if preco_max is not None else None,
    )
    estado["imoveis_sugeridos"] = [s["id"] for s in sugestoes]

    resposta_llm = _resposta_llm(mensagem, estado, sugestoes)
    usou_llm = bool(resposta_llm)
    resposta = resposta_llm or _resposta_deterministica(mensagem, estado, qual, sugestoes)

    memoria.adicionar_mensagem(estado, "agente", resposta)
    path = memoria.salvar(estado)

    return {
        "lead_id": lead_id,
        "resposta": resposta,
        "perfil": perfil,
        "qualificacao": qual,
        "imoveis": sugestoes,
        "conversa_path": str(path),
        "resumo_corretor": montar_resumo(estado),
        "usou_llm": usou_llm,
    }


def follow_up(lead_id: str) -> dict[str, Any]:
    """Retoma conversa parada mantendo contexto (cenário 3 do desafio)."""
    estado = memoria.carregar(lead_id)
    perfil = estado.get("perfil") or {}
    qual = score_lead(perfil)
    pergunta = proxima_pergunta(perfil)
    if estado.get("mensagens"):
        texto = (
            "Oi! Passando para retomar nossa conversa. "
            "Vi que paramos no meio do atendimento e queria te ajudar a avançar."
        )
    else:
        texto = "Oi! Sou o assistente SDR. Como posso te ajudar a encontrar o imóvel ideal?"
    if pergunta:
        texto += f" {pergunta}"
    elif qual.get("pronto_para_agendar"):
        texto += " Se fizer sentido, posso já te passar horários para visita."
    memoria.adicionar_mensagem(estado, "agente", texto)
    path = memoria.salvar(estado)
    return {"lead_id": lead_id, "resposta": texto, "conversa_path": str(path), "qualificacao": qual}
