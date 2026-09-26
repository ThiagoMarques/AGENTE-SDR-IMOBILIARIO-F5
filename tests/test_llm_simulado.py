"""Caminho com LLM usando um cliente OpenAI falso (sem rede e sem custo).

Valida: parsing do JSON, validação Pydantic, merge com as regras e fallback
quando o modelo devolve algo inválido ou a API falha.
"""
import json
from types import SimpleNamespace

import openai
import pytest

import config
from src.qualificacao.extracao_llm import extrair_perfil_llm, mesclar_perfil
from src.resumo.corretor import montar_resumo


def cliente_falso(conteudo=None, erro=None):
    class _Completions:
        def create(self, **kwargs):
            _Completions.ultima_chamada = kwargs
            if erro:
                raise erro
            msg = SimpleNamespace(content=conteudo)
            return SimpleNamespace(choices=[SimpleNamespace(message=msg)])

    class _Cliente:
        def __init__(self, **kwargs):
            self.chat = SimpleNamespace(completions=_Completions())

    return _Cliente, _Completions


@pytest.fixture
def llm(monkeypatch):
    monkeypatch.setattr(config, "OPENAI_API_KEY", "sk-teste")

    def usar(conteudo=None, erro=None):
        cls, comp = cliente_falso(conteudo, erro)
        monkeypatch.setattr(openai, "OpenAI", cls)
        return comp
    return usar


ESTADO = {
    "lead_id": "L-LLM",
    "perfil": {"intencao": "compra", "regiao": "moema", "quartos": 3,
               "faixa_preco": 800000, "urgencia": "alta"},
    "mensagens": [{"papel": "lead", "texto": "Quero 3 quartos em Moema, uns 800k, mas acho o condomínio caro."}],
    "imoveis_sugeridos": ["RE-1"],
}


# ---------------------------------------------------------------- extração

def test_extracao_converte_valores_e_descarta_nulos(llm):
    comp = llm(json.dumps({"intencao": "compra", "regiao": "moema", "quartos": 3,
                           "faixa_preco": 800000, "ticket": None, "urgencia": "media",
                           "objecoes": ["condomínio caro"]}))
    r = extrair_perfil_llm("Quero 3 quartos em Moema, uns 800k", {})
    assert r == {"intencao": "compra", "regiao": "moema", "quartos": 3,
                 "faixa_preco": 800000.0, "urgencia": "media", "objecoes": ["condomínio caro"]}
    assert comp.ultima_chamada["response_format"] == {"type": "json_object"}
    assert comp.ultima_chamada["temperature"] == 0


def test_extracao_corrige_erro_da_regex_no_merge(llm):
    llm(json.dumps({"faixa_preco": 1500000}))
    regras = {"intencao": "compra", "regiao": "itaim bibi", "faixa_preco": 1.0}
    m = mesclar_perfil(regras, extrair_perfil_llm("até 1,5 milhão", regras))
    assert m["faixa_preco"] == 1500000 and m["regiao"] == "itaim bibi"


@pytest.mark.parametrize("resposta", [
    "isto não é json",
    json.dumps({"intencao": "comprar-ou-alugar"}),   # fora do Literal
    json.dumps({"quartos": 50}),                     # fora do limite
])
def test_extracao_invalida_cai_para_regras(llm, resposta):
    llm(resposta)
    assert extrair_perfil_llm("qualquer coisa") is None


def test_extracao_com_api_fora_do_ar_nao_quebra(llm):
    llm(erro=RuntimeError("timeout"))
    assert extrair_perfil_llm("qualquer coisa") is None


# ---------------------------------------------------------------- resumo

def test_resumo_usa_sinopse_do_llm(llm):
    llm(json.dumps({
        "sinopse": "Cliente busca 3 quartos em Moema até 800 mil, com pressa.",
        "objecoes": ["valor do condomínio"],
        "pontos_atencao": ["Sensível a custos fixos"],
        "proximo_passo": "Apresentar opções com condomínio abaixo de 1.500.",
    }))
    r = montar_resumo(ESTADO, usar_llm=True)
    assert r["gerado_por"] == "llm"
    assert r["sinopse"].startswith("Cliente busca 3 quartos")
    assert r["acao_sugerida"] == "Apresentar opções com condomínio abaixo de 1.500."
    assert "valor do condomínio" in r["objecoes"] and "custos fixos" in r["objecoes"]  # LLM + regras
    assert "Sensível a custos fixos" in r["pontos_atencao"]


def test_resumo_nao_chama_llm_por_padrao(llm):
    comp = llm(json.dumps({"sinopse": "nunca deveria aparecer aqui"}))
    r = montar_resumo(ESTADO)
    assert r["gerado_por"] == "regras"
    assert not hasattr(comp, "ultima_chamada")


@pytest.mark.parametrize("resposta", ["{}", json.dumps({"sinopse": "curta"}), "texto solto"])
def test_resumo_llm_invalido_cai_para_regras(llm, resposta):
    llm(resposta)
    r = montar_resumo(ESTADO, usar_llm=True)
    assert r["gerado_por"] == "regras"
    assert r["sinopse"].startswith("Lead com interesse em compra")


def test_resumo_com_api_fora_do_ar_cai_para_regras(llm):
    llm(erro=ConnectionError("sem rede"))
    assert montar_resumo(ESTADO, usar_llm=True)["gerado_por"] == "regras"
