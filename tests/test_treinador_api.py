"""Rotas do treinador: dispara o processo externo e lê o que ele grava em disco."""
import os

import pytest
from fastapi.testclient import TestClient

from api import treinador as rotas
from api.app import app
from treinador.execucao import gravar_json


class PopenFalso:
    chamadas: list = []

    def __init__(self, cmd, **kwargs):
        PopenFalso.chamadas.append(cmd)

    def poll(self):
        return 0


@pytest.fixture
def cliente(tmp_path, monkeypatch):
    monkeypatch.setattr(rotas, "PASTA_SAIDAS", tmp_path)
    monkeypatch.setattr(rotas, "PASTA_CASOS", tmp_path / "casos")
    monkeypatch.setattr(rotas.subprocess, "Popen", PopenFalso)
    monkeypatch.setattr(rotas, "_PROCESSOS", {})
    monkeypatch.setattr(rotas.contextos, "ARQUIVO", tmp_path / "contextos.json")
    PopenFalso.chamadas = []
    return TestClient(app)


def test_config_lista_as_personas(cliente):
    cfg = cliente.get("/treinador/config").json()
    assert {"investidor_direto", "so_responde_sim"} <= {p["id"] for p in cfg["personas"]}
    assert "llm_disponivel" in cfg


def test_iniciar_dispara_o_processo_com_os_parametros(cliente):
    r = cliente.post("/treinador/rodadas", json={
        "personas": ["so_responde_sim"], "rodadas": 2, "max_turnos": 8, "usar_llm": False, "gerar_regressao": False})
    assert r.status_code == 202
    cmd = PopenFalso.chamadas[0]
    assert cmd[1:3] == ["-m", "treinador"]
    assert {"--sem-llm", "--sem-regressao"} <= set(cmd)
    assert cmd[cmd.index("--personas") + 1] == "so_responde_sim" and cmd[cmd.index("--rodadas") + 1] == "2"
    assert cliente.get(f"/treinador/rodadas/{r.json()['id']}").json()["estado"] == "iniciando"


def test_persona_desconhecida_e_rodada_simultanea(cliente, tmp_path):
    assert cliente.post("/treinador/rodadas", json={"personas": ["nao_existe"]}).status_code == 422

    (tmp_path / "20260101-000000").mkdir()
    gravar_json(tmp_path / "20260101-000000" / "status.json", {"id": "20260101-000000", "estado": "rodando", "pid": os.getpid()})
    assert cliente.post("/treinador/rodadas", json={}).status_code == 409


def test_contexto_e_salvo_listado_e_removido(cliente):
    texto = "simule uma conversa de um Senhor de idade que fala pausadamente e possui confusões e dúvidas"
    criado = cliente.post("/treinador/contextos", json={"contexto": texto}).json()
    assert criado["id"].startswith("ctx_") and criado["contexto"] == texto
    assert criado["nome"] == "Senhor de idade que fala"

    assert [c["id"] for c in cliente.get("/treinador/config").json()["contextos"]] == [criado["id"]]
    assert cliente.post("/treinador/contextos", json={"contexto": "curto"}).status_code == 422

    assert cliente.delete(f"/treinador/contextos/{criado['id']}").status_code == 200
    assert cliente.get("/treinador/contextos").json() == []
    assert cliente.delete(f"/treinador/contextos/{criado['id']}").status_code == 404


def test_rodada_com_contexto_exige_ia(cliente, monkeypatch):
    ctx = cliente.post("/treinador/contextos", json={"contexto": "senhora que só escreve em letras maiúsculas", "nome": "Dona Maria"}).json()
    monkeypatch.setattr(rotas.llm, "disponivel", lambda: True)
    assert cliente.post("/treinador/rodadas", json={"personas": [ctx["id"]], "usar_llm": False}).status_code == 422

    r = cliente.post("/treinador/rodadas", json={"personas": ["so_responde_sim", ctx["id"]], "usar_llm": True})
    assert r.status_code == 202
    cmd = PopenFalso.chamadas[0]
    assert cmd[cmd.index("--personas") + 1] == f"so_responde_sim,{ctx['id']}"


def test_rodada_com_processo_morto_aparece_interrompida(cliente, tmp_path):
    (tmp_path / "20260101-000000").mkdir()
    gravar_json(tmp_path / "20260101-000000" / "status.json",
                {"id": "20260101-000000", "estado": "rodando", "pid": 999_999_999, "execucoes": [{"x": 1}]})
    lista = cliente.get("/treinador/rodadas").json()
    assert lista[0]["estado"] == "interrompida" and "execucoes" not in lista[0]
    assert cliente.get("/treinador/rodadas/20260101-000000").json()["execucoes"] == [{"x": 1}]
    assert cliente.get("/treinador/rodadas/nada").status_code == 404
