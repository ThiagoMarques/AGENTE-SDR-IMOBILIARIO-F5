"""Treinador externo: verificações automáticas e uma rodada offline com roteiro."""
import json

from treinador.avaliador import avaliar
from treinador.canal import CanalLocal
from treinador.personas import PERSONAS, por_id
from treinador.regressao import salvar_casos
from treinador.simulador import conversar
from treinador.verificacoes import verificar_conversa


def _conversa(*falas):
    papeis = ("lead", "agente")
    return [{"papel": papeis[i % 2], "texto": t} for i, t in enumerate(falas)]


def _tipos(conversa):
    return {f["tipo"] for f in verificar_conversa(conversa)}


def test_detecta_resposta_repetida():
    vazia = "Não encontrei nada com 1 quarto na Asa Sul até R$ 200 mil por enquanto."
    assert "repetiu_resposta" in _tipos(_conversa("sem pressa", vazia, "sim", vazia))


def test_detecta_cidades_misturadas():
    texto = "Não encontrei nada na Asa Sul. Dentro do seu valor, tenho opções em República e em Pinheiros."
    assert "cidades_misturadas" in _tipos(_conversa("sem pressa", texto))


def test_detecta_texto_quebrado_e_jargao():
    texto = "Não encontrei o filtro exato. está em República; tem 1 quartos. Anotei: 7% a.a.."
    tipos = _tipos(_conversa("oi", texto))
    assert {"texto_quebrado", "jargao"} <= tipos


def test_detecta_pergunta_em_loop():
    pergunta = "Seu foco é renda recorrente, valorização ou outro objetivo?"
    assert "pergunta_em_loop" in _tipos(_conversa("a", pergunta, "b", pergunta, "c", pergunta))


def test_conversa_boa_nao_tem_falha():
    conversa = _conversa(
        "quero investir", "Perfeito, anotei: buscar para investir.\n\nQual valor você pretende investir?",
        "200 mil", "Perfeito, anotei: ticket de R$ 200 mil.\n\nSeu foco é renda recorrente, valorização ou outro objetivo?",
    )
    assert verificar_conversa(conversa) == []


def test_todas_as_personas_tem_roteiro():
    assert all(p.roteiro for p in PERSONAS)
    assert len({p.id for p in PERSONAS}) == len(PERSONAS)


def test_rodada_offline_com_roteiro_e_regressao(tmp_path):
    persona = por_id(["so_responde_sim"])[0]
    resultado = conversar(persona, CanalLocal(), usar_llm=False, max_turnos=12)
    assert resultado["fim"] == "roteiro concluído" and not resultado["erro"]
    assert len(resultado["conversa"]) == 2 * len(persona.roteiro)

    resultado["avaliacao"] = avaliar(persona, resultado, usar_llm=False)
    assert resultado["avaliacao"]["aprovada"], resultado["avaliacao"]["deterministicas"]

    ruim = {**resultado, "avaliacao": {"deterministicas": [{"tipo": "jargao", "turno": 1, "descricao": "x"}]}}
    salvos = salvar_casos([ruim, ruim], pasta=tmp_path)
    assert len(salvos) == 1  # a mesma sequência de mensagens não vira dois casos
    caso = json.loads(salvos[0].read_text(encoding="utf-8"))
    assert caso["mensagens_lead"] == persona.roteiro


def test_contexto_vira_persona_e_guia_o_lead_simulado(tmp_path, monkeypatch):
    from treinador import contextos, simulador

    monkeypatch.setattr(contextos, "ARQUIVO", tmp_path / "contextos.json")
    texto = "Senhor de idade que fala pausadamente e possui confusões e dúvidas"
    ctx = contextos.criar(texto, "Seu Antônio")
    persona = por_id([ctx["id"]])[0]
    assert persona.descricao == texto and persona.rotulo == "Seu Antônio" and not persona.roteiro

    prompts = []

    def llm_falso(sistema, usuario, temperatura=0.0):
        prompts.append(usuario)
        return {"mensagem": "boa tarde... eu queria... comprar um apartamento", "encerrar": len(prompts) > 1}

    monkeypatch.setattr(simulador.llm, "json_do_llm", llm_falso)
    resultado = conversar(persona, CanalLocal(), usar_llm=True, max_turnos=5)
    assert texto in prompts[0]
    assert resultado["persona_nome"] == "Seu Antônio" and resultado["persona_descricao"] == texto
    assert resultado["conversa"][0]["texto"].startswith("boa tarde...")


def test_contexto_sem_llm_fica_de_fora_da_rodada(tmp_path, monkeypatch):
    from treinador import contextos, execucao

    ctx = contextos.como_persona({"id": "ctx_teste_1", "nome": "Teste", "contexto": "lead que só manda áudio"})
    status = execucao.executar(
        [ctx, por_id(["monossilabico"])[0]], modo="local", url="", rodadas=1, max_turnos=6,
        sem_llm=True, gerar_regressao=False, pasta=tmp_path / "rodada",
    )
    assert status["parametros"]["ignoradas_sem_llm"] == ["ctx_teste_1"]
    assert [e["persona"] for e in status["execucoes"]] == ["monossilabico"]
