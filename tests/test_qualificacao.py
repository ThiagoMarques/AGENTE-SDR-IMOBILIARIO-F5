from src.qualificacao.extracao_llm import extrair_perfil_llm, mesclar_perfil
from src.qualificacao.lead import campos_faltantes, proxima_pergunta, score_estado, score_lead

COMPRA_COMPLETA = {
    "intencao": "compra", "regiao": "zona sul", "quartos": 2,
    "faixa_preco": 500000, "urgencia": "alta",
}
INVESTIDOR = {"intencao": "investimento", "ticket": 400000,
              "retorno_esperado": "6% a.a.", "perfil": "renda recorrente"}


def test_lead_vazio_e_frio():
    q = score_lead({})
    assert q["score"] == 0 and q["prioridade"] == "frio"
    assert q["campos_faltantes"][0] == "intencao"


def test_compra_completa_e_urgente_e_quente_e_pronta():
    q = score_lead(COMPRA_COMPLETA)
    assert q["score"] == 100
    assert q["prioridade"] == "quente"
    assert q["pronto_para_agendar"] is True
    assert q["encaminhamento"] == "corretor"


def test_orcamento_pesa_mais_que_quartos():
    com_orcamento = score_lead({"intencao": "compra", "faixa_preco": 500000})["score"]
    com_quartos = score_lead({"intencao": "compra", "quartos": 2})["score"]
    assert com_orcamento > com_quartos


def test_urgencia_baixa_reduz_score():
    base = dict(COMPRA_COMPLETA)
    alta = score_lead(base)["score"]
    base["urgencia"] = "baixa"
    assert score_lead(base)["score"] < alta


def test_investidor_vai_para_especialista():
    q = score_lead(INVESTIDOR)
    assert q["encaminhamento"] == "especialista em investimentos"
    assert q["campos_faltantes"] == []


def test_justificativa_explica_cada_criterio():
    q = score_lead({"intencao": "aluguel"})
    nomes = {c["criterio"] for c in q["criterios"]}
    assert nomes == {"necessidade", "detalhamento", "orcamento", "prazo"}
    assert "Orçamento não informado" in q["justificativa"]


def test_engajamento_entra_quando_ha_mensagens():
    estado = {"perfil": COMPRA_COMPLETA,
              "mensagens": [{"papel": "lead", "texto": "oi"}, {"papel": "agente", "texto": "olá"}]}
    q = score_estado(estado)
    assert any(c["criterio"] == "engajamento" for c in q["criterios"])
    assert q["score"] < 100  # só 1 mensagem do lead


def test_proxima_pergunta_segue_funil():
    assert "comprar, alugar ou investir" in proxima_pergunta({})
    assert proxima_pergunta(COMPRA_COMPLETA) is None
    assert campos_faltantes({"intencao": "investimento"}) == ["ticket", "retorno_esperado", "perfil"]


def test_llm_ausente_retorna_none():
    assert extrair_perfil_llm("quero comprar") is None


def test_merge_llm_corrige_regex_sem_apagar_e_acumula_objecoes():
    # regex errou: "1,5 milhão" -> 1 e "minha renda" -> investimento
    regras = {"intencao": "investimento", "regiao": "moema", "faixa_preco": 1.0, "objecoes": ["preço"]}
    llm = {"intencao": "aluguel", "faixa_preco": 1500000, "quartos": 3,
           "objecoes": ["preço", "financiamento"]}
    m = mesclar_perfil(regras, llm)
    assert m["intencao"] == "aluguel"
    assert m["faixa_preco"] == 1500000
    assert m["regiao"] == "moema"  # LLM não retornou: mantém
    assert m["quartos"] == 3
    assert m["objecoes"] == ["preço", "financiamento"]


def test_merge_sem_llm_mantem_regras():
    regras = {"intencao": "compra"}
    assert mesclar_perfil(regras, None) == regras
