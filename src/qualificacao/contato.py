"""Captura de contato no chat: nome, e-mail (com correção de domínio) e respostas sim/não."""
from __future__ import annotations

import difflib
import re
import unicodedata
from typing import Callable

_DOMINIOS_COMUNS = (
    "gmail.com", "hotmail.com", "outlook.com", "live.com", "yahoo.com", "yahoo.com.br",
    "icloud.com", "uol.com.br", "bol.com.br", "terra.com.br", "hotmail.com.br", "outlook.com.br",
)

_PADROES_NOME = (
    (re.compile(r"\bmeu nome (?:é|e|eh)\s+", re.I), False),
    (re.compile(r"\bme chamo\s+", re.I), False),
    (re.compile(r"\bpode me chamar de\s+", re.I), False),
    (re.compile(r"\baqui (?:é|e|eh) (?:o|a)\s+", re.I), False),
    (re.compile(r"\bsou (?:o|a)\s+", re.I), True),
)
_CONECTORES = {"da", "de", "do", "das", "dos"}
_NAO_NOME = {
    "e", "mas", "quero", "queria", "busco", "procuro", "estou", "to", "tenho", "gostaria",
    "aqui", "pode", "sim", "nao", "oi", "ola", "bom", "boa", "dia", "tarde", "noite",
    "tudo", "bem", "obrigado", "obrigada", "ok", "certo", "isso", "claro", "beleza",
    "interessado", "interessada", "corretor", "cliente", "comprador", "procurando",
    "apartamento", "apto", "casa", "imovel", "cobertura", "visita", "quartos", "quarto",
}
_PEDIU_NOME = ("te chamar", "seu nome", "se chama")

_AFIRMA = re.compile(
    r"^(sim|s|isso|isso mesmo|exato|certo|pode|pode ser|pode sim|claro|ok|okay|beleza|"
    r"fechado|confirmo|confirmado|perfeito|bora|com certeza|esta certo|ta certo|correto)\b"
)
_NEGA = re.compile(r"^(nao|n|errado|negativo|ta errado|esta errado)\b")


def _norm(texto: str) -> str:
    base = unicodedata.normalize("NFKD", texto or "").encode("ascii", "ignore").decode()
    return re.sub(r"[!?.…,;]+", " ", base.lower()).strip()


def afirmativo(texto: str) -> bool:
    return bool(_AFIRMA.match(_norm(texto)))


def negativo(texto: str) -> bool:
    return bool(_NEGA.match(_norm(texto)))


def sugerir_correcao_email(email: str) -> str | None:
    """'ana@gmial.com' -> 'ana@gmail.com'. None se o domínio parece certo (ou é corporativo)."""
    usuario, _, dominio = email.partition("@")
    if not dominio or dominio in _DOMINIOS_COMUNS:
        return None
    parecido = difflib.get_close_matches(dominio, _DOMINIOS_COMUNS, n=1, cutoff=0.8)
    return f"{usuario}@{parecido[0]}" if parecido else None


_TRATAMENTOS = {"seu", "dona", "sr", "sra", "srta", "senhor", "senhora", "dr", "dra", "doutor", "doutora", "dom"}


def vocativo(nome: str | None) -> str:
    """Como chamar a pessoa: 'Ana Souza' -> 'Ana'; 'Seu João' -> 'Seu João' (não 'Seu')."""
    palavras = (nome or "").split()
    if not palavras:
        return ""
    if len(palavras) > 1 and _norm(palavras[0]).rstrip(".") in _TRATAMENTOS:
        return " ".join(palavras[:2])
    return palavras[0]


def _formatar_nome(palavras: list[str]) -> str:
    return " ".join(p.lower() if p.lower() in _CONECTORES else p[:1].upper() + p[1:].lower() for p in palavras)


def _nome_a_partir(trecho: str, *, exige_maiuscula: bool) -> str | None:
    trecho = re.split(r"[.!?,;:\n]", trecho, maxsplit=1)[0]  # "Lucas. Tava pensando…" -> "Lucas"
    palavras = re.findall(r"[^\W\d_]+(?:'[^\W\d_]+)?", trecho)
    nome: list[str] = []
    for i, p in enumerate(palavras[:4]):
        chave = _norm(p)
        if chave in _CONECTORES and nome and i + 1 < len(palavras) and palavras[i + 1][:1].isupper():
            nome.append(p)
            continue
        if chave in _NAO_NOME or chave in _CONECTORES or len(p) < 2:
            break
        if exige_maiuscula and not nome and not p[:1].isupper():
            return None
        nome.append(p)
        if len([n for n in nome if _norm(n) not in _CONECTORES]) == 3:
            break
    return _formatar_nome(nome) if nome else None


def extrair_nome(
    texto: str,
    ultima_fala_agente: str = "",
    rejeitar: Callable[[str], bool] | None = None,
) -> str | None:
    """'meu nome é ana souza' -> 'Ana Souza'.

    Resposta curta ('Ana') só conta se o agente pediu o nome e `rejeitar` não
    reconhecer ali outra resposta (ex.: 'comprar', 'Pinheiros').
    """
    texto_sem = re.sub(r"\S+@\S+", " ", texto or "")
    for padrao, exige_maiuscula in _PADROES_NOME:
        m = padrao.search(texto_sem)
        if m:
            nome = _nome_a_partir(texto_sem[m.end():], exige_maiuscula=exige_maiuscula)
            if nome:
                return nome
    if not any(p in _norm(ultima_fala_agente) for p in _PEDIU_NOME):
        return None
    resposta = re.sub(r"^(?:(?:e|eh|é|sou)\s+)?(?:(?:o|a)\s+)?", "", texto_sem.strip(), flags=re.I).strip(" .!,")
    # "Ana, quero comprar" -> tenta a frase toda e depois só o trecho antes da vírgula
    for curto in dict.fromkeys((resposta, resposta.split(",")[0].strip())):
        if (
            curto
            and not re.search(r"\d", curto)
            and 1 <= len(curto.split()) <= 3
            and not (rejeitar and rejeitar(curto))
        ):
            nome = _nome_a_partir(curto, exige_maiuscula=False)
            if nome and len(nome.split()) == len(curto.split()):
                return nome
    return None
