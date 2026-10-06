"""Resumo inteligente para o corretor (human-in-the-loop).

O objetivo é que o corretor entenda o lead em 30 segundos, sem ler a conversa:
quem é, o que quer, quão quente está (e por quê), o que preocupa o cliente
e qual o próximo passo.

Duas camadas:
1) Regras (sempre): prioridade, justificativa do score, pontos de atenção,
   objeções detectadas por palavras-chave e ação sugerida.
2) LLM (opcional, usar_llm=True + OPENAI_API_KEY): sinopse em linguagem
   natural a partir da conversa, validada por schema Pydantic. Se falhar,
   a sinopse por regras é usada — o resumo nunca fica vazio.
"""
from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field, ValidationError

import config
from src.qualificacao.lead import formatar_valor, score_estado

ROTULOS = {
    "nome": "Nome",
    "intencao": "Intenção",
    "regiao": "Região",
    "quartos": "Quartos",
    "faixa_preco": "Orçamento",
    "ticket": "Ticket de investimento",
    "urgencia": "Urgência",
    "retorno_esperado": "Retorno esperado",
    "perfil": "Perfil de investidor",
    "email": "E-mail",
}

NOMES_CRITERIOS = {
    "necessidade": "Necessidade", "detalhamento": "Detalhamento", "orcamento": "Orçamento",
    "prazo": "Prazo", "engajamento": "Engajamento",
}

OBJECOES = {
    "preço": ("caro", "muito alto", "fora do orçamento", "desconto"),
    "financiamento": ("financiamento", "financiar", "entrada", "fgts", "crédito", "credito"),
    "localização": ("longe", "distante", "trânsito", "transito"),
    "custos fixos": ("condomínio", "condominio", "iptu"),
    "indecisão": ("vou pensar", "não sei", "nao sei", "talvez", "ainda não", "ainda nao"),
    "decisão compartilhada": (
        "minha esposa", "meu marido", "minha família", "minha familia", "meu sócio", "meu socio",
        "minha sócia", "minha socia", "meu esposo", "minha mulher",
    ),
}


class SinopseLLM(BaseModel):
    sinopse: str = Field(..., min_length=10)
    objecoes: list[str] = Field(default_factory=list)
    pontos_atencao: list[str] = Field(default_factory=list)
    proximo_passo: str = ""


# ---------------------------------------------------------------- regras

def detectar_objecoes(mensagens: list[dict[str, Any]]) -> list[str]:
    texto = " ".join((m.get("texto") or "").lower() for m in mensagens if m.get("papel") == "lead")
    return [nome for nome, termos in OBJECOES.items() if any(t in texto for t in termos)]


def pontos_de_atencao(estado: dict[str, Any], qual: dict[str, Any]) -> list[str]:
    perfil = estado.get("perfil") or {}
    msgs = estado.get("mensagens") or []
    pontos: list[str] = []
    if qual["prioridade"] == "quente" and str(perfil.get("urgencia")).lower() in {"alta", "urgente"}:
        pontos.append("Lead quente com urgência alta: retornar ainda hoje.")
    if qual["encaminhamento"] != "corretor":
        pontos.append(f"Perfil investidor: direcionar para {qual['encaminhamento']}.")
    if perfil.get("intencao") and not estado.get("imoveis_sugeridos"):
        pontos.append("Nenhum imóvel do catálogo atende aos filtros: rever critérios com o cliente.")
    alerta = _alerta_follow_up(msgs)
    if alerta:
        pontos.append(alerta)
    if qual["campos_faltantes"]:
        rot = [ROTULOS.get(c, c) for c in qual["campos_faltantes"]]
        pontos.append(f"Informações pendentes: {', '.join(rot)}.")
    return pontos


HORAS_SEM_RESPOSTA = 24


def _alerta_follow_up(msgs: list[dict[str, Any]], agora: datetime | None = None) -> str | None:
    """Lead parado = não respondeu a um follow-up, ou está em silêncio há 24h+.

    O agente sempre responde por último, então "última mensagem do agente"
    sozinho não indica abandono.
    """
    if not msgs or msgs[-1].get("papel") != "agente":
        return None
    idx_lead = max((i for i, m in enumerate(msgs) if m.get("papel") == "lead"), default=-1)
    sem_resposta = len(msgs) - 1 - idx_lead  # mensagens do agente após a última do lead
    if sem_resposta >= 2:
        return "Lead não respondeu ao follow-up: tentar outro canal ou contato humano."
    if idx_lead >= 0:
        try:
            ultima = datetime.fromisoformat(msgs[idx_lead]["em"])
        except (KeyError, TypeError, ValueError):
            return None
        horas = ((agora or datetime.now(timezone.utc)) - ultima) / timedelta(hours=1)
        if horas >= HORAS_SEM_RESPOSTA:
            return f"Lead sem responder há {int(horas)}h: candidato a follow-up."
    return None


def sinopse_regras(estado: dict[str, Any], qual: dict[str, Any]) -> str:
    p = estado.get("perfil") or {}
    if not p.get("intencao"):
        n = sum(1 for m in estado.get("mensagens") or [] if m.get("papel") == "lead")
        return (
            f"Intenção ainda não identificada ({n} mensagem(ns) do lead). "
            f"Classificado como {qual['prioridade']} (score {qual['score']})."
        )
    partes = [f"Lead com interesse em {p['intencao']}"]
    if p.get("regiao"):
        partes.append(f"na região {p['regiao']}")
    if p.get("quartos"):
        partes.append(f"com {p['quartos']}+ quartos")
    orc = p.get("ticket") or p.get("faixa_preco")
    if orc:
        partes.append(f"e orçamento de até {formatar_valor(orc)}")
    texto = " ".join(partes) + "."
    if p.get("retorno_esperado"):
        texto += f" Espera retorno de {p['retorno_esperado']}"
        texto += f" ({p['perfil']})." if p.get("perfil") else "."
    if p.get("urgencia"):
        texto += f" Urgência {p['urgencia']}."
    texto += f" Classificado como {qual['prioridade']} (score {qual['score']})."
    return texto


def _acao(qual: dict[str, Any], estado: dict[str, Any]) -> str:
    ativos = [a for a in estado.get("agendamentos") or [] if a.get("status", "agendado") == "agendado"]
    if ativos:
        return f"Visita marcada para {ativos[-1].get('horario')}: confirmar com o corretor responsável."
    if qual.get("encaminhamento") != "corretor" and qual.get("pronto_para_agendar"):
        return f"Lead investidor qualificado: agendar conversa com {qual['encaminhamento']}."
    if qual.get("pronto_para_agendar"):
        return "Lead qualificado: oferecer horários de visita/reunião."
    if qual.get("prioridade") == "quente":
        return "Priorizar retorno humano; completar campos faltantes."
    if qual.get("campos_faltantes"):
        rot = [ROTULOS.get(c, c) for c in qual["campos_faltantes"]]
        return f"Continuar qualificação. Faltam: {', '.join(rot)}."
    return "Manter nurture / follow-up."


# ---------------------------------------------------------------- LLM

def _sinopse_llm(estado: dict[str, Any], qual: dict[str, Any]) -> SinopseLLM | None:
    if not config.OPENAI_API_KEY:
        return None
    try:
        from openai import OpenAI

        client = OpenAI(api_key=config.OPENAI_API_KEY)
        conversa = "\n".join(
            f"[{m.get('papel')}] {m.get('texto')}" for m in (estado.get("mensagens") or [])[-20:]
        )
        system = (
            "Você prepara briefings para corretores de imóveis. Com base APENAS na conversa e "
            "no perfil fornecidos, responda um JSON com: sinopse (2 a 3 frases objetivas sobre "
            "quem é o lead e o que busca), objecoes (lista), pontos_atencao (lista curta), "
            "proximo_passo (uma frase). Não invente dados. Português do Brasil."
        )
        user = (
            f"Perfil: {json.dumps(estado.get('perfil') or {}, ensure_ascii=False)}\n"
            f"Qualificação: score {qual['score']} ({qual['prioridade']}). {qual['justificativa']}\n"
            f"Conversa:\n{conversa}"
        )
        resp = client.chat.completions.create(
            model=config.LLM_MODEL,
            messages=[{"role": "system", "content": system}, {"role": "user", "content": user}],
            response_format={"type": "json_object"},
            temperature=0.2,
        )
        return SinopseLLM.model_validate(json.loads(resp.choices[0].message.content or "{}"))
    except (ValidationError, json.JSONDecodeError):
        return None
    except Exception:
        return None


# ---------------------------------------------------------------- API pública

def montar_resumo(estado: dict[str, Any], usar_llm: bool = False) -> dict[str, Any]:
    """Monta o pacote para o corretor.

    usar_llm=False por padrão: o agente chama esta função a cada mensagem,
    e não faz sentido pagar uma chamada de LLM por turno. Use usar_llm=True
    na hora de entregar o resumo ao corretor (CLI --resumo / demo).
    """
    perfil = estado.get("perfil") or {}
    mensagens = estado.get("mensagens") or []
    qual = score_estado(estado)

    objecoes = detectar_objecoes(mensagens)
    for o in perfil.get("objecoes") or []:
        if o not in objecoes:
            objecoes.append(o)
    pontos = pontos_de_atencao(estado, qual)
    sinopse = sinopse_regras(estado, qual)
    acao = _acao(qual, estado)
    gerado_por = "regras"

    if usar_llm:
        llm = _sinopse_llm(estado, qual)
        if llm:
            sinopse = llm.sinopse
            objecoes = objecoes + [o for o in llm.objecoes if o not in objecoes]
            pontos = pontos + [p for p in llm.pontos_atencao if p not in pontos]
            if llm.proximo_passo:
                acao = llm.proximo_passo
            gerado_por = "llm"

    return {
        "lead_id": estado.get("lead_id"),
        "gerado_em": datetime.now(timezone.utc).isoformat(),
        "gerado_por": gerado_por,
        "sinopse": sinopse,
        "perfil": perfil,
        "qualificacao": qual,
        "encaminhamento": qual["encaminhamento"],
        "objecoes": objecoes,
        "pontos_atencao": pontos,
        "imoveis_sugeridos": estado.get("imoveis_sugeridos") or [],
        "agendamentos": estado.get("agendamentos") or [],
        "ultimas_mensagens": mensagens[-6:],
        "acao_sugerida": acao,
    }


def _valor_campo(campo: str, valor: Any) -> str:
    if campo in {"faixa_preco", "ticket"}:
        return formatar_valor(valor)
    return str(valor)


def formatar_resumo_txt(resumo: dict[str, Any]) -> str:
    """Resumo legível (Markdown simples) para o corretor."""
    q = resumo["qualificacao"]
    perfil = resumo.get("perfil") or {}
    linhas = [
        f"# Resumo do lead {resumo['lead_id']}",
        "",
        f"**Prioridade:** {q['prioridade'].upper()} (score {q['score']}/100)",
        f"**Encaminhar para:** {resumo.get('encaminhamento', 'corretor')}",
        f"**Ação sugerida:** {resumo.get('acao_sugerida')}",
        "",
        "## Sinopse",
        resumo.get("sinopse") or "-",
        "",
        "## Perfil",
    ]
    campos = [c for c in ROTULOS if perfil.get(c)]
    if "ticket" in campos and "faixa_preco" in campos and perfil["ticket"] == perfil["faixa_preco"]:
        campos.remove("faixa_preco")
    linhas += [f"- {ROTULOS[c]}: {_valor_campo(c, perfil[c])}" for c in campos] or ["- (sem dados)"]

    linhas += ["", "## Por que essa prioridade"]
    for c in q.get("criterios") or []:
        nome = NOMES_CRITERIOS.get(c["criterio"], c["criterio"])
        linhas.append(f"- {nome}: {c['pontos']}/{c['maximo']} — {c['motivo']}")

    linhas += ["", "## Objeções do cliente"]
    linhas += [f"- {o}" for o in resumo.get("objecoes") or []] or ["- Nenhuma identificada"]
    linhas += ["", "## Pontos de atenção"]
    linhas += [f"- {p}" for p in resumo.get("pontos_atencao") or []] or ["- Nenhum"]

    imoveis = resumo.get("imoveis_sugeridos") or []
    linhas += ["", f"## Imóveis sugeridos ({len(imoveis)})"]
    linhas.append(", ".join(str(i) for i in imoveis) if imoveis else "- Nenhum")

    ags = resumo.get("agendamentos") or []
    if ags:
        linhas += ["", "## Agendamentos"]
        linhas += [f"- {a.get('tipo')} em {a.get('horario')} ({a.get('status')})" for a in ags]

    linhas += ["", "## Últimas mensagens"]
    for m in resumo.get("ultimas_mensagens") or []:
        texto = (m.get("texto") or "").replace("\n", " ")
        if len(texto) > 160:
            texto = texto[:157] + "..."
        linhas.append(f"- **{m.get('papel')}:** {texto}")
    linhas += ["", f"_Gerado por: {resumo.get('gerado_por')} em {resumo.get('gerado_em')}_"]
    return "\n".join(linhas)


def exportar_resumo(resumo: dict[str, Any], pasta: Path | None = None) -> dict[str, Path]:
    """Salva resumo_<lead>.md (para humanos) e .json (para CRM/integrações)."""
    pasta = pasta or config.SAIDAS_DIR
    pasta.mkdir(parents=True, exist_ok=True)
    safe = "".join(c if c.isalnum() or c in "-_" else "_" for c in str(resumo["lead_id"]))
    md = pasta / f"resumo_{safe}.md"
    js = pasta / f"resumo_{safe}.json"
    md.write_text(formatar_resumo_txt(resumo), encoding="utf-8")
    js.write_text(json.dumps(resumo, ensure_ascii=False, indent=2), encoding="utf-8")
    return {"md": md, "json": js}
