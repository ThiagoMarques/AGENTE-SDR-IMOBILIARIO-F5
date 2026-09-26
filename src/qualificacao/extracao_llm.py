"""Extração estruturada do perfil do lead com LLM (opcional).

Por que usar LLM aqui?
- Regex não entende variações naturais ("tenho uns 800k", "preciso mudar
  antes das férias", "3 dorms ou mais"). O LLM interpreta a mensagem no
  contexto da conversa e devolve JSON validado por um schema Pydantic.
- As regras continuam como fallback: sem OPENAI_API_KEY ou em caso de erro,
  a função retorna None e o fluxo determinístico segue funcionando.
- Merge com precedência do LLM: quando o LLM extrai um campo, o valor dele
  vale sobre o da regex (a validação mostrou erros de regex como "1,5 milhão"
  -> 1 e "minha renda" -> investimento, que um merge só-preenche-lacunas
  preservaria). Campos que o LLM NÃO retornou nunca são apagados.
"""
from __future__ import annotations

import json
from typing import Any, Literal, Optional

from pydantic import BaseModel, Field, ValidationError

import config


class PerfilExtraido(BaseModel):
    intencao: Optional[Literal["compra", "aluguel", "investimento"]] = None
    regiao: Optional[str] = Field(None, description="bairro ou região citada, em minúsculas")
    quartos: Optional[int] = Field(None, ge=0, le=10)
    faixa_preco: Optional[float] = Field(None, ge=0, description="valor máximo em número")
    ticket: Optional[float] = Field(None, ge=0, description="valor a investir, se investidor")
    urgencia: Optional[Literal["alta", "media", "baixa"]] = None
    retorno_esperado: Optional[str] = Field(None, description="ex.: '6% a.a.'")
    perfil: Optional[Literal["renda recorrente", "valorização"]] = None
    objecoes: list[str] = Field(default_factory=list, description="dúvidas ou barreiras citadas")


_SYSTEM = (
    "Você extrai dados de qualificação de leads imobiliários. "
    "Responda SOMENTE um JSON com as chaves: intencao, regiao, quartos, faixa_preco, "
    "ticket, urgencia, retorno_esperado, perfil, objecoes. "
    "Use null quando a informação não aparecer. Não invente dados. "
    "Valores monetários como número (\"800k\" -> 800000). "
    "urgencia: alta (dias/semanas, 'urgente'), media (alguns meses), baixa (sem pressa, só pesquisando)."
)


def extrair_perfil_llm(
    mensagem: str,
    perfil_atual: dict[str, Any] | None = None,
    historico: list[dict[str, Any]] | None = None,
) -> dict[str, Any] | None:
    """Retorna só os campos extraídos (sem nulos) ou None se LLM indisponível."""
    if not config.OPENAI_API_KEY:
        return None
    try:
        from openai import OpenAI

        client = OpenAI(api_key=config.OPENAI_API_KEY)
        contexto = "\n".join(f"[{m.get('papel')}] {m.get('texto')}" for m in (historico or [])[-6:])
        user = (
            f"Perfil já conhecido: {json.dumps(perfil_atual or {}, ensure_ascii=False)}\n"
            f"Conversa recente:\n{contexto or '(início)'}\n\n"
            f"Nova mensagem do lead: {mensagem}"
        )
        resp = client.chat.completions.create(
            model=config.LLM_MODEL,
            messages=[{"role": "system", "content": _SYSTEM}, {"role": "user", "content": user}],
            response_format={"type": "json_object"},
            temperature=0,
        )
        bruto = json.loads(resp.choices[0].message.content or "{}")
        extraido = PerfilExtraido.model_validate(bruto)
    except (ValidationError, json.JSONDecodeError):
        return None
    except Exception:
        return None
    return {k: v for k, v in extraido.model_dump().items() if v not in (None, [], "")}


def mesclar_perfil(perfil_regras: dict[str, Any], extraido: dict[str, Any] | None) -> dict[str, Any]:
    """LLM tem precedência nos campos que extraiu; o resto é mantido.

    O LLM recebe o perfil atual e o histórico, com temperature=0 e a instrução
    de não inventar; nulos são descartados antes do merge, então ele corrige
    valores mas não apaga informação. Objeções são acumuladas.
    """
    if not extraido:
        return perfil_regras
    novo = dict(perfil_regras)
    for campo, valor in extraido.items():
        if campo == "objecoes":
            atuais = list(novo.get("objecoes") or [])
            novo["objecoes"] = atuais + [o for o in valor if o not in atuais]
        else:
            novo[campo] = valor
    return novo
