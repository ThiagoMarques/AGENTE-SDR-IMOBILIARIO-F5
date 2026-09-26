import json
from datetime import datetime, timedelta, timezone

from src.resumo.corretor import _alerta_follow_up, exportar_resumo, formatar_resumo_txt, montar_resumo


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


def test_detecta_objecoes():
    r = montar_resumo(_estado())
    assert {"preço", "custos fixos", "financiamento"} <= set(r["objecoes"])


def test_consultar_horarios_nao_e_decisao_compartilhada():
    e = _estado()
    e["mensagens"].append({"papel": "lead", "texto": "Posso consultar os horários de visita?"})
    assert "decisão compartilhada" not in montar_resumo(e)["objecoes"]
    e["mensagens"].append({"papel": "lead", "texto": "Preciso ver com minha esposa."})
    assert "decisão compartilhada" in montar_resumo(e)["objecoes"]


def test_conversa_ativa_nao_gera_alerta_de_follow_up():
    agora = datetime.now(timezone.utc).isoformat()
    msgs = [{"papel": "lead", "texto": "oi", "em": agora}, {"papel": "agente", "texto": "olá", "em": agora}]
    assert _alerta_follow_up(msgs) is None


def test_lead_que_nao_respondeu_follow_up_gera_alerta():
    agora = datetime.now(timezone.utc).isoformat()
    msgs = [{"papel": "lead", "texto": "oi", "em": agora},
            {"papel": "agente", "texto": "olá", "em": agora},
            {"papel": "agente", "texto": "retomando nossa conversa", "em": agora}]
    assert "não respondeu ao follow-up" in _alerta_follow_up(msgs)


def test_lead_em_silencio_ha_mais_de_24h_gera_alerta():
    antes = (datetime.now(timezone.utc) - timedelta(hours=30)).isoformat()
    msgs = [{"papel": "lead", "texto": "oi", "em": antes}, {"papel": "agente", "texto": "olá", "em": antes}]
    assert "30h" in _alerta_follow_up(msgs)


def test_sinopse_sem_intencao_e_legivel():
    e = {"lead_id": "X", "perfil": {}, "mensagens": [{"papel": "lead", "texto": "oi"}]}
    s = montar_resumo(e)["sinopse"]
    assert s.startswith("Intenção ainda não identificada") and "interesse em intenção" not in s


def test_investidor_nao_duplica_orcamento_e_ticket():
    e = {"lead_id": "INV", "perfil": {"intencao": "investimento", "ticket": 400000, "faixa_preco": 400000,
         "retorno_esperado": "6% a.a.", "perfil": "renda recorrente"}, "mensagens": []}
    txt = formatar_resumo_txt(montar_resumo(e))
    assert "- Ticket de investimento: 400.000" in txt and "- Orçamento: 400.000" not in txt


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
