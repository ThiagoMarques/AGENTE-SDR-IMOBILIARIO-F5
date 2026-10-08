"""Fluxo interativo: erro de digitação, mudança de ideia no meio e fora de escopo sem perder o funil."""
from src.agente.sdr import processar_mensagem


def conversar(lead, *mensagens):
    r = None
    for m in mensagens:
        r = processar_mensagem(lead, m)
    return r


def test_alugar_digitado_errado_nao_repete_a_pergunta():
    r = conversar("FX-1", "quero alugr um apartamento")
    assert r["perfil"]["intencao"] == "aluguel"
    assert "comprar, alugar ou investir" not in r["resposta"]


def test_regiao_digitada_errada():
    r = conversar("FX-2", "quero comprar na zuna sul")
    assert r["perfil"]["regiao"] == "zona sul"


def test_muda_a_regiao_quando_o_agente_pergunta_quartos():
    r = conversar("FX-3", "quero comprar na zona sul", "até 800 mil")
    assert "quartos" in r["resposta"].lower()

    r = processar_mensagem("FX-3", "ah, não, muda pra zona leste")
    assert r["perfil"]["regiao"] == "zona leste"
    assert "atualizei" in r["resposta"].lower() and "quartos" in r["resposta"].lower()


def test_varios_dados_fora_de_ordem_na_mesma_mensagem():
    r = conversar("FX-4", "oi", "3 quartos em moema até 1 milhão, quero comprar")
    perfil = r["perfil"]
    assert perfil["intencao"] == "compra" and perfil["regiao"] == "moema"
    assert perfil["quartos"] == 3 and perfil["faixa_preco"] == 1_000_000


def test_sem_resultado_fala_natural_e_sugere_ajuste_concreto():
    r = conversar("FX-6", "quero comprar na zona sul", "200000", "1 quarto", "curto")
    assert "conjunto de filtros" not in r["resposta"]
    assert r["resposta"].startswith("Não encontrei nada com 1 quarto na Zona Sul até R$ 200 mil")
    assert "o mais em conta que tenho hoje sai por R$" in r["resposta"]


def test_sugestao_de_outra_regiao_fica_na_mesma_cidade():
    r = conversar("FX-7", "quero investir na asa sul", "200 mil", "renda", "6% ao ano")
    assert "Não encontrei nada" in r["resposta"]
    for bairro_de_sp in ("República", "Pinheiros", "Moema", "Vila Mariana"):
        assert bairro_de_sp not in r["resposta"]


def test_sim_aceita_a_regiao_sugerida_e_refaz_a_busca(monkeypatch):
    from src.agente import sdr

    def busca(perfil):
        if perfil.get("regiao") == "asa norte":
            return sdr.buscar_resultado(intencao="compra", regiao="asa norte")
        return {"imoveis": [], "match": "vazio", "motivo": "", "pistas": {
            "menor_preco_regiao": 980_000.0,
            "outras_regioes": [{"regiao": "asa norte", "nome": "Asa Norte"}]}}

    monkeypatch.setattr(sdr, "_buscar_por_perfil", busca)
    r = conversar("FX-8", "quero comprar na asa sul", "200 mil", "1 quarto", "sem pressa")
    assert "tenho opções na Asa Norte. Quer que eu procure por lá?" in r["resposta"]

    r = processar_mensagem("FX-8", "sim")
    assert r["perfil"]["regiao"] == "asa norte"
    assert "Não encontrei nada" not in r["resposta"] and r["imoveis"]


def test_sim_depois_da_busca_vazia_propoe_valor_e_segundo_sim_mostra():
    r = conversar("FX-9", "quero comprar na asa sul", "200 mil", "1 quarto", "sem pressa")
    assert "Não encontrei nada" in r["resposta"]

    r = processar_mensagem("FX-9", "sim")
    assert r["resposta"].startswith("Uma ideia: subindo o valor para R$ 980 mil, já tenho opção na Asa Sul.")

    r = processar_mensagem("FX-9", "sim")
    assert r["perfil"]["faixa_preco"] == 980_000 and r["imoveis"]


def test_liberar_a_regiao_sem_nada_no_valor_diz_isso_e_oferece_o_menor_preco():
    r = conversar("FX-15", "quero comprar na asa sul", "200 mil", "1 quarto", "sem pressa")
    r = processar_mensagem("FX-15", "pode olhar outra região então")
    assert r["resposta"].startswith("Procurei em todas as regiões que atendo e não encontrei nada com 1 quarto até R$ 200 mil.")
    assert "Quer que eu busque até esse valor?" in r["resposta"]

    r = processar_mensagem("FX-15", "pode olhar outra região então")
    assert r["resposta"].startswith("Já procurei em todas as regiões")
    assert "deixo pro corretor" not in r["resposta"]

    r = processar_mensagem("FX-15", "sim")
    assert r["imoveis"] and "Não encontrei nada" not in r["resposta"]


def test_kitnet_vira_studio_sem_quarto_e_valor_com_uns_e_lido():
    r = conversar("FX-16", "quero alugar uma kitnet na zona sul, até uns 1.500 por mês")
    assert r["perfil"]["quartos"] == 0 and r["perfil"]["faixa_preco"] == 1500
    assert "Quantos quartos" not in r["resposta"]

    r = processar_mensagem("FX-16", "sem pressa")
    assert "nada com na" not in r["resposta"] and "0 quartos" not in r["resposta"]
    assert "studio/kitnet" in r["resposta"]


def test_nome_para_no_ponto_final():
    r = conversar("FX-17", "quero comprar na zona sul até 800 mil", "Pode me chamar de Lucas. Tava pensando em 2 quartos")
    assert r["perfil"]["nome"] == "Lucas" and r["perfil"]["quartos"] == 2
    assert not r["perfil"].get("perfil")


def test_llm_nao_grava_nome_como_foco_de_investimento():
    from src.qualificacao.interpretador import _sanitizar_dados_llm

    assert "perfil" not in _sanitizar_dados_llm({"dados": {"perfil": "Lucas"}})
    assert _sanitizar_dados_llm({"dados": {"perfil": "renda com aluguel"}})["perfil"] == "renda recorrente"
    assert "retorno_esperado" not in _sanitizar_dados_llm({"dados": {"retorno_esperado": "o mais rápido"}})


def test_ver_opcoes_primeiro_antes_de_marcar_nao_agenda():
    from src.agenda.scheduler import interpretar_escolha

    ofertados = ["07/10/2026 10:00", "07/10/2026 14:00"]
    assert interpretar_escolha("quero ver isso primeiro antes de marcar", ofertados) is None
    assert interpretar_escolha("tem algo lá? quero ver isso primeiro", ofertados) is None
    assert interpretar_escolha("o primeiro", ofertados).inicio is not None
    assert interpretar_escolha("pode ser o primeiro horário", ofertados).inicio is not None


def test_lugar_nao_vira_alugar_quando_a_intencao_ja_existe():
    r = conversar("FX-30", "quero comprar na zona sul", "quero um lugar tranquilo, até 800 mil")
    assert r["perfil"]["intencao"] == "compra"


def test_llm_com_correcao_nao_troca_campo_que_o_lead_nao_citou(monkeypatch):
    from src.qualificacao import interpretador

    perfil = {"intencao": "compra", "quartos": 2}
    falso = {"categoria": "dados", "correcao": True, "dados": {"quartos": 1, "intencao": "aluguel", "urgencia": "alta"}}
    monkeypatch.setattr(interpretador, "interpretar_com_llm", lambda *a, **k: falso)

    dados = interpretador.interpretar_mensagem(
        "na verdade preciso disso logo", perfil, campo_aguardando=None, ultimo_campo_preenchido="quartos"
    )["dados"]
    assert "quartos" not in dados and "intencao" not in dados and dados["urgencia"] == "alta"

    dados = interpretador.interpretar_mensagem(
        "na verdade um quarto só", perfil, campo_aguardando=None, ultimo_campo_preenchido="quartos"
    )["dados"]
    assert dados["quartos"] == 1


def test_preco_por_extenso():
    from src.qualificacao.interpretador import _extrair_preco_explicito as preco

    assert preco("2 mil e quinhentos") == 2500
    assert preco("dois mil e oitocentos reais") == 2800
    assert preco("mil e quinhentos por mês") == 1500
    assert preco("um milhão e meio") == 1_500_000
    assert preco("1 milhão e 200 mil") == 1_200_000


def test_regiao_central_e_cidade_inteira():
    from src.qualificacao.interpretador import _detectar_regioes, _sanitizar_dados_llm

    assert _detectar_regioes("na região central") == ["centro"]
    assert "regiao" not in _sanitizar_dados_llm({"dados": {"regiao": "São Paulo"}})
    assert "regiao" not in _sanitizar_dados_llm({"dados": {"regiao": "Brasília"}})


def test_tratamento_entra_no_vocativo():
    from src.qualificacao.contato import vocativo

    assert vocativo("Seu João") == "Seu João"
    assert vocativo("Dona Maria Silva") == "Dona Maria"
    assert vocativo("Maria Silva") == "Maria"


def test_mais_opcoes_nao_vai_pro_corretor():
    conversar("FX-31", "quero comprar na zona leste", "800 mil", "2 quartos", "sem pressa")
    r = processar_mensagem("FX-31", "Tem mais opções nessa região?")
    assert "deixo pro corretor" not in r["resposta"]


def test_me_avisa_anota_uma_vez_e_encerra():
    conversar("FX-32", "quero comprar na asa sul", "200 mil", "1 quarto", "sem pressa")
    primeira = processar_mensagem("FX-32", "tá bom, se aparecer algo me avisa")
    assert "Deixo anotado" in primeira["resposta"]
    segunda = processar_mensagem("FX-32", "ok, vou esperar então")
    assert segunda["resposta"] != primeira["resposta"] and "Tô por aqui" not in segunda["resposta"]


def test_mudar_o_valor_e_deixar_horarios_pra_depois_refaz_a_busca():
    conversar("FX-18", "quero comprar na zona leste", "800 mil", "2 quartos", "sem pressa")
    r = processar_mensagem("FX-18", "aumenta o valor pra até 1 milhão, os horários eu vejo depois")
    assert r["perfil"]["faixa_preco"] == 1_000_000
    assert "Tenho estes horários" not in r["resposta"] and "Visita marcada" not in r["resposta"]


def test_insistir_sem_dado_novo_nunca_repete_a_mesma_resposta():
    r = conversar("FX-14", "quero comprar na asa sul", "200 mil", "1 quarto", "sem pressa")
    respostas = [r["resposta"]]
    for msg in ("não", "hmm", "sei lá", "nada"):
        respostas.append(processar_mensagem("FX-14", msg)["resposta"])
    assert all(a != b for a, b in zip(respostas, respostas[1:])), respostas


def test_investidor_responde_so_renda():
    r = conversar("FX-10", "quero investir", "200 mil", "renda")
    assert r["perfil"]["perfil"] == "renda recorrente"


def test_prazo_nao_vira_retorno_esperado():
    r = conversar("FX-11", "quero investir", "200 mil", "valorização", "em 3 anos")
    assert not r["perfil"].get("retorno_esperado")
    assert "prazo de 3 anos" in r["resposta"] and "retorno" in r["resposta"]


def test_inquilino_que_quer_alugar_nao_ganha_foco_de_investidor():
    r = conversar("FX-12", "quero alugar um apartamento")
    assert not r["perfil"].get("perfil")


def test_logo_e_meses_viram_prazo():
    assert conversar("FX-15", "quero comprar no brooklin", "1,2 milhão", "2 quartos", "logo")["perfil"]["urgencia"] == "alta"
    assert conversar("FX-16", "quero comprar no brooklin", "1,2 milhão", "2 quartos", "uns 6 meses")["perfil"]["urgencia"] == "media"


def test_pedir_visita_no_meio_da_qualificacao_nao_vira_nao_entendi():
    r = conversar("FX-17", "quero comprar no brooklin", "1,2 milhão")
    r = processar_mensagem("FX-17", "quero agendar uma visita")
    assert r["resposta"].startswith("Consigo marcar, sim! Antes, só preciso saber: quantos quartos")


def test_nao_entendi_duas_vezes_traz_exemplos_em_vez_de_repetir():
    conversar("FX-18", "quero comprar no brooklin", "1,2 milhão", "2 quartos")
    primeira = processar_mensagem("FX-18", "hmm")["resposta"]
    segunda = processar_mensagem("FX-18", "hmm")["resposta"]
    assert primeira.startswith("Desculpa, não entendi bem.")
    assert segunda != primeira and "por exemplo" in segunda


def test_duvida_comum_tem_resposta_de_verdade():
    conversar("FX-13", "quero investir", "200 mil")
    r = processar_mensagem("FX-13", "o que é ITBI?")
    assert "imposto" in r["resposta"] and "foco" in r["resposta"]
    assert "contexto imobiliário" not in r["resposta"]


def test_fora_de_escopo_responde_fixo_e_volta_para_a_pergunta_do_fluxo():
    conversar("FX-5", "quero comprar na zona sul")
    r = processar_mensagem("FX-5", "qual a previsão do tempo amanhã?")
    assert r["fora_de_escopo"] and "Voltando à sua busca" in r["resposta"]
    assert r["perfil"]["regiao"] == "zona sul"
