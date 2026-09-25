import json

from src.resumo.corretor import exportar_resumo, formatar_resumo_txt, montar_resumo


def _estado():
    return {
        "lead_id": "LEAD-T1",
        "perfil": {"intencao": "compra", "regiao": "zona sul", "quartos": 2,
                   "faixa_preco": 500000, "urgencia": "alta"},
        "mensagens": [
            {"papel": "lead", "texto": "Procuro apê na zona sul, 2 quartos."},
            {"papel": "agente", "texto": "Qual o orçamento?"},
            {"papel": "lead", "texto": "Até 500 mil, mas achei caro o condomínio. Preciso ver financiamento."},
            {"papel": "agente", "texto": "Tenho opções, posso agendar?"},
        ],
        "imoveis_sugeridos": ["RE-1", "RE-2"],
        "agendamentos": [],
    }


def test_resumo_tem_campos_essenciais_e_compatibilidade():
    r = montar_resumo(_estado())
    for chave in ("lead_id", "perfil", "qualificacao", "imoveis_sugeridos",
                  "agendamentos", "ultimas_mensagens", "acao_sugerida",
                  "sinopse", "objecoes", "pontos_atencao", "gerado_por"):
        assert chave in r
    assert r["gerado_por"] == "regras"


def test_detecta_objecoes_e_follow_up():
    r = montar_resumo(_estado())
    assert {"preço", "custos fixos", "financiamento"} <= set(r["objecoes"])
    assert any("aguardando resposta" in p for p in r["pontos_atencao"])


def test_usar_llm_sem_chave_cai_para_regras():
    assert montar_resumo(_estado(), usar_llm=True)["gerado_por"] == "regras"


def test_sinopse_regras_descreve_lead():
    s = montar_resumo(_estado())["sinopse"]
    assert "compra" in s and "zona sul" in s and "500.000" in s


def test_texto_legivel_sem_dicionario_cru():
    txt = formatar_resumo_txt(montar_resumo(_estado()))
    assert "# Resumo do lead LEAD-T1" in txt
    assert "- Orçamento: 500.000" in txt
    assert "{'" not in txt  # nada de dict impresso cru


def test_investidor_direcionado_para_especialista():
    e = {"lead_id": "INV", "perfil": {"intencao": "investimento", "ticket": 400000,
         "retorno_esperado": "6% a.a.", "perfil": "renda recorrente"},
         "mensagens": [{"papel": "lead", "texto": "quero investir"}], "imoveis_sugeridos": ["X"]}
    r = montar_resumo(e)
    assert r["encaminhamento"] == "especialista em investimentos"
    assert "especialista" in r["acao_sugerida"]


def test_exporta_md_e_json(tmp_path):
    paths = exportar_resumo(montar_resumo(_estado()), tmp_path)
    assert paths["md"].read_text(encoding="utf-8").startswith("# Resumo")
    assert json.loads(paths["json"].read_text(encoding="utf-8"))["lead_id"] == "LEAD-T1"
