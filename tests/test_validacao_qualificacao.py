"""Bateria de validação da qualificação (fluxo completo, modo regras, sem LLM).

Cada caso simula uma conversa real e confere prioridade e/ou campos extraídos.
Casos marcados com `xfail` são DEFEITOS CONHECIDOS na extração por regex
(`extrair_sinais` em src/agente/sdr.py). `strict=True`: quando o defeito for
corrigido, o teste passa a acusar XPASS, avisando para remover a marcação.
"""
import pytest

import config
from src.agente.sdr import processar_mensagem
from src.imoveis import catalogo

FAKE = [
    {"id": "RE-1", "type": "sale", "price": 420000, "beds": 2, "city": "Austin",
     "state": "TX", "address": "x", "property_type": "apt", "sqft": 900},
    {"id": "RE-2", "type": "rent", "price": 3000, "beds": 2, "city": "Austin",
     "state": "TX", "address": "y", "property_type": "apt", "sqft": 800},
]
REGEX = "defeito conhecido em extrair_sinais (sdr.py)"


@pytest.fixture(autouse=True)
def ambiente(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "CONVERSAS_DIR", tmp_path / "conversas")
    monkeypatch.setattr(config, "CRM_WEBHOOK_URL", "")
    monkeypatch.setattr(catalogo, "_get_listings", lambda p: [catalogo._normalizar(x) for x in FAKE])


def conversar(lead, *mensagens):
    r = None
    for m in mensagens:
        r = processar_mensagem(lead, m)
    return r


# ------------------------------------------------------------- funcionando

def test_c01_compra_completa_urgente_e_quente():
    r = conversar("C01", "Estou procurando apartamento na zona sul.",
                  "Quero 2 quartos, até 500 mil, é urgente.")
    assert r["qualificacao"]["prioridade"] == "quente"
    assert r["qualificacao"]["pronto_para_agendar"]


def test_c02_curioso_sem_pressa_e_frio():
    r = conversar("C02", "Oi, só estou pesquisando preços, sem pressa.")
    assert r["qualificacao"]["prioridade"] == "frio"


def test_c04_investidor_completo_quente_para_especialista():
    r = conversar("C04", "Quero investir em imóveis para renda.",
                  "Ticket de 400 mil, espero 6% ao ano.")
    assert r["qualificacao"]["prioridade"] == "quente"
    assert r["qualificacao"]["encaminhamento"] == "especialista em investimentos"


def test_c12_so_intencao_e_frio():
    r = conversar("C12", "Procuro uma casa.")
    assert r["qualificacao"]["prioridade"] == "frio"


def test_c03_aluguel_com_regiao_apenas_e_frio():
    # Calibração: só intenção + região ainda é frio (37). Decisão consciente.
    r = conversar("C03", "Quero alugar em Pinheiros.")
    assert r["qualificacao"]["prioridade"] == "frio"


# ------------------------------------------------------------- defeitos conhecidos (regex)

@pytest.mark.xfail(strict=True, reason=REGEX + ': "800k" não vira orçamento')
def test_c05_orcamento_em_k():
    r = conversar("C05", "Quero comprar casa em Moema, 3 quartos, tenho uns 800k, urgente.")
    assert r["perfil"].get("faixa_preco") == 800000


def test_c06_orcamento_em_milhao():
    r = conversar("C06", "Quero comprar cobertura no Itaim, 4 quartos, até 1,5 milhão, o quanto antes.")
    assert r["perfil"].get("faixa_preco") == 1500000


@pytest.mark.xfail(strict=True, reason=REGEX + ': "em 3 meses" não vira urgência')
def test_c07_prazo_em_meses():
    r = conversar("C07", "Comprar apê na Vila Mariana, 2 dorms, até 600 mil, pretendo mudar em 3 meses.")
    assert r["perfil"].get("urgencia") in {"media", "média"}


@pytest.mark.xfail(strict=True, reason=REGEX + ': bairro "Mooca" e "esse mês" não reconhecidos')
def test_c08_bairro_fora_da_lista_e_prazo_no_mes():
    r = conversar("C08", "Quero alugar na Mooca, 2 quartos, até 3 mil, preciso mudar esse mês.")
    assert r["perfil"].get("regiao") == "mooca"
    assert r["perfil"].get("urgencia") == "alta"
    assert r["qualificacao"]["prioridade"] == "quente"


@pytest.mark.xfail(strict=True, reason=REGEX + ': "agora" vence "só olhando"')
def test_c09_agora_nao_indica_urgencia_quando_so_olhando():
    r = conversar("C09", "Agora estou só olhando, quero comprar apartamento no futuro.")
    assert r["perfil"].get("urgencia") == "baixa"
    assert r["qualificacao"]["prioridade"] == "frio"


@pytest.mark.xfail(strict=True, reason=REGEX + ': "renda" com "alugar" vira investimento')
def test_c10_renda_do_cliente_nao_e_investimento():
    r = conversar("C10", "Quero alugar apto, minha renda é 10 mil, 2 quartos na zona oeste.")
    assert r["perfil"]["intencao"] == "aluguel"
    assert r["qualificacao"]["encaminhamento"] == "corretor"


@pytest.mark.xfail(strict=True, reason=REGEX + ': "dois quartos" por extenso não é lido')
def test_c11_quartos_por_extenso():
    r = conversar("C11", "Quero comprar apartamento com dois quartos na zona norte até 450 mil.")
    assert r["perfil"].get("quartos") == 2
