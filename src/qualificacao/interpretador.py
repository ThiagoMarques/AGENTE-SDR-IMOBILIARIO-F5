"""Interpretação de mensagens humanas para o SDR.

Princípios:
- aceita erros de digitação;
- aceita informações fora de ordem;
- uma mensagem pode preencher vários campos;
- correções explícitas substituem valores antigos;
- `campo_aguardando` é contexto, não uma prisão;
- funciona sem LLM;
- se houver LLM, ele é apenas uma camada auxiliar de interpretação.
"""

from __future__ import annotations

import json
import re
import unicodedata
from difflib import SequenceMatcher
from typing import Any

import config


REGIOES: dict[str, str] = {
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
    "itaim bibi": "itaim bibi",
    "brooklin": "brooklin",
    "jardins": "jardins",
    "republica": "república",
    "república": "república",
}


INTENCOES: dict[str, tuple[str, ...]] = {
    "aluguel": (
        "alugar",
        "aluguel",
        "locacao",
        "locação",
        "locar",
    ),
    "compra": (
        "comprar",
        "compra",
        "aquisicao",
        "aquisição",
    ),
    "investimento": (
        "investir",
        "investimento",
        "investidor",
    ),
}


TIPOS_IMOVEL: dict[str, tuple[str, ...]] = {
    "apartamento": ("apartamento", "apto", "ape", "apê"),
    "casa": ("casa",),
    "cobertura": ("cobertura",),
    "studio": ("studio", "estudio", "estúdio"),
}


CORRECAO_HINTS = (
    "na verdade",
    "corrigindo",
    "quis dizer",
    "eu errei",
    "errei",
    "desculpa",
    "pensando bem",
    "melhor",
    "mudei de ideia",
    "mudei",
    "nao,",
    "não,",
    "nao ",
    "não ",
)


FORA_ESCOPO = (
    "previsao do tempo",
    "clima",
    "temperatura",
    "futebol",
    "jogo do",
    "campeonato",
    "politica",
    "eleicao",
    "piada",
    "horoscopo",
    "receita de",
    "bitcoin",
    "criptomoeda",
    "chatgpt",
)


IMOBILIARIO_HINTS = (
    "imovel",
    "apartamento",
    "apto",
    "casa",
    "cobertura",
    "studio",
    "aluguel",
    "alugar",
    "comprar",
    "compra",
    "investir",
    "investimento",
    "condominio",
    "iptu",
    "garagem",
    "vaga",
    "pet",
    "cachorro",
    "gato",
    "elevador",
    "metro",
    "metragem",
    "visita",
    "corretor",
    "financiamento",
    "entrada",
    "documentacao",
    "contrato",
    "fiador",
    "seguro fianca",
    "bairro",
    "regiao",
    "quarto",
    "quartos",
)


QUESTION_STARTS = (
    "tem ",
    "aceita ",
    "aceitam ",
    "posso ",
    "pode ",
    "quanto ",
    "como ",
    "qual ",
    "quando ",
    "onde ",
    "vocês ",
    "voces ",
)


def normalizar_texto(texto: str) -> str:
    t = (texto or "").lower().strip()
    t = unicodedata.normalize("NFKD", t)
    t = "".join(c for c in t if not unicodedata.combining(c))
    t = re.sub(r"\s+", " ", t)
    return t


def _tokens(texto: str) -> list[str]:
    return re.findall(r"[a-z0-9]+", normalizar_texto(texto))


def _similar(a: str, b: str) -> float:
    return SequenceMatcher(None, normalizar_texto(a), normalizar_texto(b)).ratio()


def _ngrams(tokens: list[str], n: int) -> list[str]:
    if n <= 0 or len(tokens) < n:
        return []
    return [" ".join(tokens[i : i + n]) for i in range(len(tokens) - n + 1)]


def parece_correcao(texto: str) -> bool:
    t = normalizar_texto(texto)
    return any(normalizar_texto(x) in t for x in CORRECAO_HINTS)


def _detectar_intencao(texto: str) -> str | None:
    t = normalizar_texto(texto)

    # Match direto primeiro.
    for intencao, aliases in INTENCOES.items():
        for alias in aliases:
            if normalizar_texto(alias) in t:
                return intencao

    # Depois fuzzy por token. Bom para "alugr", "alugaar", "compraar" etc.
    for token in _tokens(t):
        if len(token) < 4:
            continue

        melhor_intencao = None
        melhor_score = 0.0

        for intencao, aliases in INTENCOES.items():
            for alias in aliases:
                alias_n = normalizar_texto(alias)
                if " " in alias_n:
                    continue

                score = _similar(token, alias_n)

                if score > melhor_score:
                    melhor_score = score
                    melhor_intencao = intencao

        if melhor_score >= 0.78:
            return melhor_intencao

    return None


def _detectar_regioes(texto: str) -> list[str]:
    t = normalizar_texto(texto)
    encontrados: list[str] = []

    normalizadas = {
        normalizar_texto(chave): valor
        for chave, valor in REGIOES.items()
    }

    # Exato.
    for chave, valor in sorted(
        normalizadas.items(),
        key=lambda item: -len(item[0]),
    ):
        if re.search(rf"\b{re.escape(chave)}\b", t):
            if valor not in encontrados:
                encontrados.append(valor)

    if encontrados:
        return encontrados

    # Fuzzy por n-grams: "zuna sul" -> "zona sul".
    toks = _tokens(t)

    for chave, valor in normalizadas.items():
        partes = chave.split()
        candidatos = _ngrams(toks, len(partes))

        melhor = max(
            (_similar(cand, chave) for cand in candidatos),
            default=0.0,
        )

        if melhor >= 0.78 and valor not in encontrados:
            encontrados.append(valor)

    return encontrados


def _detectar_tipo_imovel(texto: str) -> str | None:
    t = normalizar_texto(texto)

    for tipo, aliases in TIPOS_IMOVEL.items():
        for alias in aliases:
            alias_n = normalizar_texto(alias)

            if re.search(rf"\b{re.escape(alias_n)}\b", t):
                return tipo

    return None


def _sem_preferencia(texto: str) -> bool:
    t = normalizar_texto(texto)

    return t in {
        "nao",
        "nenhuma",
        "nenhum",
        "qualquer",
        "tanto faz",
        "indiferente",
        "nao sei",
        "ainda nao sei",
        "sem preferencia",
        "sem preferencias",
    } or any(
        x in t
        for x in (
            "sem preferencia",
            "qualquer regiao",
            "qualquer bairro",
            "qualquer quantidade",
            "nao tenho preferencia",
            "nao tenho um valor",
            "nao sei o valor",
        )
    )


def _extrair_quartos_explicitos(texto: str) -> dict[str, Any]:
    t = normalizar_texto(texto)

    # 2 ou 3 quartos
    m = re.search(
        r"\b(\d{1,2})\s*(?:ou|a)\s*(\d{1,2})\s*"
        r"(?:quartos?|dormitorios?|dorms?|qtos?)\b",
        t,
    )

    if m:
        a, b = sorted((int(m.group(1)), int(m.group(2))))
        return {
            "quartos": a,
            "quartos_min": a,
            "quartos_max": b,
        }

    m = re.search(
        r"\b(\d{1,2})\s*(?:quartos?|dormitorios?|dorms?|qtos?|q)\b",
        t,
    )

    if m:
        return {"quartos": int(m.group(1))}

    return {}


def _numero_para_float(txt: str) -> float:
    # Para o escopo do projeto: ponto é separador de mil quando não há vírgula.
    valor = txt.strip().replace(" ", "")

    if "," in valor:
        valor = valor.replace(".", "").replace(",", ".")
    elif valor.count(".") == 1:
        esquerda, direita = valor.split(".")

        # 2.000 -> 2000, mas 2.5 -> 2.5
        if len(direita) == 3:
            valor = esquerda + direita

    return float(valor)


def _extrair_preco_explicito(texto: str) -> float | None:
    t = normalizar_texto(texto)

    # 1 milhão / 1,5 milhão / 2 milhões / 1.2 mi
    m = re.search(r"\br?\$?\s*([\d.,]+)\s*(?:milhao|milhoes|mi)\b", t)

    if m:
        return _numero_para_float(m.group(1)) * 1_000_000

    # 2 mil / 2.5 mil / 2,5 mil
    m = re.search(r"\br?\$?\s*([\d.,]+)\s*mil\b", t)

    if m:
        return _numero_para_float(m.group(1)) * 1000

    # R$ 2000 / R$ 2.000
    m = re.search(r"\br\$\s*([\d.,]+)\b", t)

    if m:
        return _numero_para_float(m.group(1))

    # até 2000 / orçamento 2000 / valor 2000 / teto 2000
    m = re.search(
        r"(?:ate|no maximo|maximo|orcamento|valor|preco|teto|pago|pagar|ticket)"
        r"(?:\s+de)?\s*[:\-]?\s*r?\$?\s*([\d.,]+)\b",
        t,
    )

    if m:
        return _numero_para_float(m.group(1))

    return None


def _extrair_urgencia(texto: str) -> str | None:
    t = normalizar_texto(texto)

    if any(
        x in t
        for x in (
            "urgente",
            "essa semana",
            "esta semana",
            "o quanto antes",
            "agora",
            "curto prazo",
            "pra ontem",
            "este mes",
            "esse mes",
        )
    ):
        return "alta"

    if any(
        x in t
        for x in (
            "sem pressa",
            "so olhando",
            "pesquisando",
            "longo prazo",
        )
    ):
        return "baixa"

    if any(
        x in t
        for x in (
            "medio prazo",
            "alguns meses",
        )
    ):
        return "media"

    if t in {"curto", "alta"}:
        return "alta"

    if t in {"medio", "media"}:
        return "media"

    if t in {"longo", "baixa"}:
        return "baixa"

    return None


def _extrair_investimento(texto: str) -> dict[str, Any]:
    t = normalizar_texto(texto)
    dados: dict[str, Any] = {}

    m = re.search(r"\b(\d+(?:[.,]\d+)?)\s*%", t)

    if m:
        dados["retorno_esperado"] = m.group(1).replace(",", ".") + "% a.a."

    if any(
        x in t
        for x in (
            "renda recorrente",
            "renda mensal",
            "renda de aluguel",
            "locacao",
            "aluguel",
        )
    ):
        dados["perfil"] = "renda recorrente"

    elif any(
        x in t
        for x in (
            "valorizacao",
            "valorizar",
            "ganho de capital",
        )
    ):
        dados["perfil"] = "valorização"

    return dados


def _campo_numerico_por_contexto(
    numero: float,
    *,
    campo_aguardando: str | None,
    ultimo_campo_preenchido: str | None,
    correcao: bool,
    perfil: dict[str, Any],
) -> str | None:
    # Correção explícita tem prioridade sobre a pergunta atual.
    if correcao and ultimo_campo_preenchido in {
        "quartos",
        "faixa_preco",
        "ticket",
    }:
        return ultimo_campo_preenchido

    # Heurística humana:
    # se o bot espera preço mas a pessoa manda "2", provavelmente está
    # corrigindo/adiantando quartos, pois R$ 2 é implausível neste contexto.
    if campo_aguardando in {"faixa_preco", "ticket"} and numero <= 20:
        if perfil.get("quartos") is not None or ultimo_campo_preenchido == "quartos":
            return "quartos"

    # Se espera quartos e recebe 2000, isso parece preço informado fora de ordem.
    if campo_aguardando == "quartos" and numero >= 100:
        return "ticket" if perfil.get("intencao") == "investimento" else "faixa_preco"

    if campo_aguardando in {"quartos", "faixa_preco", "ticket"}:
        return campo_aguardando

    # Fora de ordem sem pergunta compatível.
    if numero <= 20:
        return "quartos"

    if numero >= 100:
        return "ticket" if perfil.get("intencao") == "investimento" else "faixa_preco"

    return None


def extrair_dados_deterministicos(
    texto: str,
    perfil: dict[str, Any],
    *,
    campo_aguardando: str | None,
    ultimo_campo_preenchido: str | None,
) -> dict[str, Any]:
    t = normalizar_texto(texto)
    dados: dict[str, Any] = {}

    intencao = _detectar_intencao(texto)

    if intencao:
        dados["intencao"] = intencao

    regioes = _detectar_regioes(texto)

    if regioes:
        dados["regiao"] = regioes[0]
        dados["regiao_flexivel"] = False

        if len(regioes) > 1:
            dados["regioes"] = regioes

    tipo = _detectar_tipo_imovel(texto)

    if tipo:
        dados["tipo_imovel"] = tipo

        # "procuro apartamento na zona sul": tipo sem verbo é compra
        # (cenário típico do desafio), mas nunca sobrescreve intenção já dita.
        if not intencao and not perfil.get("intencao"):
            dados["intencao"] = "compra"

    dados.update(_extrair_quartos_explicitos(texto))

    preco = _extrair_preco_explicito(texto)

    if preco is not None:
        if (
            perfil.get("intencao") == "investimento"
            or dados.get("intencao") == "investimento"
            or "ticket" in t
        ):
            dados["ticket"] = preco
        else:
            dados["faixa_preco"] = preco

    urgencia = _extrair_urgencia(texto)

    if urgencia:
        dados["urgencia"] = urgencia

    dados.update(_extrair_investimento(texto))

    # "não tenho preferência", "não sei", "tanto faz" responde o campo atual
    # sem fazer o agente perguntar eternamente.
    if _sem_preferencia(texto) and campo_aguardando:
        if campo_aguardando in {"regiao", "quartos", "faixa_preco", "ticket"}:
            dados[f"{campo_aguardando}_flexivel"] = True

            # Se antes havia valor, "sem preferência" deve liberar o filtro.
            dados[campo_aguardando] = None

        elif campo_aguardando == "urgencia":
            dados["urgencia"] = "indefinida"

        elif campo_aguardando in {"perfil", "retorno_esperado"}:
            dados[f"{campo_aguardando}_flexivel"] = True
            dados[campo_aguardando] = None

    # Número isolado: usa contexto, não regras concorrentes.
    m_num = re.fullmatch(r"\s*r?\$?\s*([\d.,]+)\s*", t)

    if m_num:
        numero = _numero_para_float(m_num.group(1))

        campo = _campo_numerico_por_contexto(
            numero,
            campo_aguardando=campo_aguardando,
            ultimo_campo_preenchido=ultimo_campo_preenchido,
            correcao=parece_correcao(texto),
            perfil=perfil,
        )

        if campo == "quartos" and numero <= 20:
            dados["quartos"] = int(numero)
            dados["quartos_flexivel"] = False

        elif campo in {"faixa_preco", "ticket"} and numero >= 100:
            dados[campo] = float(numero)
            dados[f"{campo}_flexivel"] = False

    # Correção curta: "na verdade 2".
    if parece_correcao(texto) and ultimo_campo_preenchido:
        m = re.search(r"\b(\d+(?:[.,]\d+)?)\b", t)

        if m:
            numero = _numero_para_float(m.group(1))

            if ultimo_campo_preenchido == "quartos" and numero <= 20:
                dados["quartos"] = int(numero)

            elif ultimo_campo_preenchido in {"faixa_preco", "ticket"}:
                # "na verdade 2500"
                if numero >= 100:
                    dados[ultimo_campo_preenchido] = numero

    return dados


def _sanitizar_dados_llm(raw: Any) -> dict[str, Any]:
    if not isinstance(raw, dict):
        return {}

    dados = raw.get("dados")

    if not isinstance(dados, dict):
        return {}

    out: dict[str, Any] = {}

    intencao = dados.get("intencao")

    if intencao in {"compra", "aluguel", "investimento"}:
        out["intencao"] = intencao

    regiao = dados.get("regiao")

    if isinstance(regiao, str) and regiao.strip():
        # Primeiro tenta normalizar para uma região conhecida.
        detectadas = _detectar_regioes(regiao)
        out["regiao"] = detectadas[0] if detectadas else normalizar_texto(regiao)

    tipo = dados.get("tipo_imovel")

    if tipo in {"apartamento", "casa", "cobertura", "studio"}:
        out["tipo_imovel"] = tipo

    quartos = dados.get("quartos")

    if isinstance(quartos, (int, float)) and 0 <= quartos <= 20:
        out["quartos"] = int(quartos)

    for campo in ("faixa_preco", "ticket"):
        valor = dados.get(campo)

        if isinstance(valor, (int, float)) and valor >= 100:
            out[campo] = float(valor)

    urgencia = dados.get("urgencia")

    if urgencia in {"alta", "media", "baixa", "indefinida"}:
        out["urgencia"] = urgencia

    for campo in ("retorno_esperado", "perfil"):
        valor = dados.get(campo)

        if isinstance(valor, str) and valor.strip():
            out[campo] = valor.strip()

    return out


def interpretar_com_llm(
    texto: str,
    perfil: dict[str, Any],
    *,
    campo_aguardando: str | None,
    ultimo_campo_preenchido: str | None,
) -> dict[str, Any] | None:
    """Fallback opcional. Nunca é necessário para o agente funcionar."""
    if not getattr(config, "OPENAI_API_KEY", None):
        return None

    try:
        from openai import OpenAI

        client = OpenAI(api_key=config.OPENAI_API_KEY)

        system = (
            "Você é apenas um interpretador de mensagens para um SDR imobiliário. "
            "NÃO converse com o cliente. Retorne somente JSON válido. "
            "Extraia apenas informações presentes ou claramente implícitas na mensagem. "
            "Pode corrigir erros de digitação óbvios, por exemplo 'zuna sul' -> 'zona sul' "
            "e 'alugr' -> 'aluguel'. Não invente valores. "
            "O usuário pode corrigir dados anteriores, mudar de ideia, responder fora de ordem "
            "ou fornecer vários dados na mesma mensagem. "
            "Categorias permitidas: dados, duvida_imobiliaria, fora_escopo, saudacao, outro. "
            "Formato: "
            '{"categoria":"dados","correcao":false,"dados":{'
            '"intencao":null,"regiao":null,"quartos":null,"faixa_preco":null,'
            '"urgencia":null,"ticket":null,"retorno_esperado":null,'
            '"perfil":null,"tipo_imovel":null}}'
        )

        user = (
            f"Perfil atual: {json.dumps(perfil, ensure_ascii=False)}\n"
            f"Campo que o agente estava perguntando: {campo_aguardando or '(nenhum)'}\n"
            f"Último campo preenchido: {ultimo_campo_preenchido or '(nenhum)'}\n"
            f"Mensagem: {texto}"
        )

        resp = client.chat.completions.create(
            model=config.LLM_MODEL,
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            temperature=0,
            response_format={"type": "json_object"},
        )

        content = (resp.choices[0].message.content or "").strip()

        if not content:
            return None

        raw = json.loads(content)

        return {
            "categoria": raw.get("categoria"),
            "correcao": bool(raw.get("correcao")),
            "dados": _sanitizar_dados_llm(raw),
        }

    except Exception:
        # O agente continua 100% funcional sem LLM.
        return None


def _tem_dado_util(dados: dict[str, Any]) -> bool:
    return any(
        chave
        not in {
            "regiao_flexivel",
            "quartos_flexivel",
            "faixa_preco_flexivel",
            "ticket_flexivel",
        }
        or bool(valor)
        for chave, valor in dados.items()
    )


def parece_duvida_imobiliaria(texto: str) -> bool:
    t = normalizar_texto(texto)

    parece_pergunta = "?" in texto or t.startswith(QUESTION_STARTS)

    if not parece_pergunta:
        return False

    return any(
        normalizar_texto(hint) in t
        for hint in IMOBILIARIO_HINTS
    )


def mensagem_fora_de_escopo(texto: str) -> bool:
    t = normalizar_texto(texto)
    return any(normalizar_texto(x) in t for x in FORA_ESCOPO)


def interpretar_mensagem(
    texto: str,
    perfil: dict[str, Any],
    *,
    campo_aguardando: str | None,
    ultimo_campo_preenchido: str | None,
) -> dict[str, Any]:
    """Combina regras locais + LLM opcional sem entregar o controle ao modelo."""
    dados = extrair_dados_deterministicos(
        texto,
        perfil,
        campo_aguardando=campo_aguardando,
        ultimo_campo_preenchido=ultimo_campo_preenchido,
    )

    categoria = "dados" if _tem_dado_util(dados) else "outro"
    correcao = parece_correcao(texto)

    if mensagem_fora_de_escopo(texto) and not _tem_dado_util(dados):
        categoria = "fora_escopo"

    elif parece_duvida_imobiliaria(texto):
        categoria = "duvida_imobiliaria"

    # O LLM complementa, nunca é requisito.
    llm = interpretar_com_llm(
        texto,
        perfil,
        campo_aguardando=campo_aguardando,
        ultimo_campo_preenchido=ultimo_campo_preenchido,
    )

    if llm:
        for chave, valor in (llm.get("dados") or {}).items():
            # Regras determinísticas têm prioridade quando já entenderam o campo.
            if chave not in dados:
                # Evita o LLM sobrescrever silenciosamente um valor antigo
                # sem sinal de correção. Mudanças explícitas de região/intenção
                # normalmente já são capturadas deterministicamente.
                antigo = perfil.get(chave)

                if antigo in (None, "") or correcao or llm.get("correcao"):
                    dados[chave] = valor

        if categoria == "outro" and llm.get("categoria") in {
            "dados",
            "duvida_imobiliaria",
            "fora_escopo",
            "saudacao",
            "outro",
        }:
            categoria = str(llm["categoria"])

        correcao = correcao or bool(llm.get("correcao"))

    if _tem_dado_util(dados) and categoria == "outro":
        categoria = "dados"

    return {
        "categoria": categoria,
        "correcao": correcao,
        "dados": dados,
        "usou_llm": bool(llm),
    }


def reconciliar_perfil(
    perfil_atual: dict[str, Any],
    dados: dict[str, Any],
) -> tuple[dict[str, Any], dict[str, tuple[Any, Any]]]:
    """Aplica somente mudanças reais e devolve antes/depois por campo."""
    novo = dict(perfil_atual)
    alteracoes: dict[str, tuple[Any, Any]] = {}

    for campo, valor in dados.items():
        antigo = novo.get(campo)

        if antigo != valor:
            novo[campo] = valor
            alteracoes[campo] = (antigo, valor)

    # Se valor concreto chegou, desliga flexibilidade daquele campo.
    for campo in ("regiao", "quartos", "faixa_preco", "ticket"):
        if campo in dados and dados.get(campo) not in (None, ""):
            flex = f"{campo}_flexivel"

            if novo.get(flex):
                antigo = novo.get(flex)
                novo[flex] = False
                alteracoes[flex] = (antigo, False)

    return novo, alteracoes
