"""Rotas do treinador: a API só dispara o processo e lê os arquivos que ele grava.

O treinador roda em outro processo (python -m treinador) porque o modo local troca a memória
e desliga integrações no módulo inteiro; dentro da API isso afetaria as conversas reais.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any

from fastapi import APIRouter, HTTPException
from fastapi.responses import PlainTextResponse
from pydantic import BaseModel, Field

from treinador import contextos, llm
from treinador.execucao import PASTA_SAIDAS, novo_id
from treinador.personas import PERSONAS
from treinador.regressao import PASTA_CASOS

RAIZ = Path(__file__).resolve().parents[1]

router = APIRouter(prefix="/treinador", tags=["treinador"])

# Processos disparados por esta API; poll() recolhe o filho que terminou (senão o pid segue "vivo").
_PROCESSOS: dict[str, subprocess.Popen] = {}


class RodadaIn(BaseModel):
    personas: list[str] = Field(default_factory=list, description="Vazio = todas")
    rodadas: int = Field(1, ge=1, le=5)
    max_turnos: int = Field(12, ge=2, le=20)
    usar_llm: bool = True
    gerar_regressao: bool = True


class ContextoIn(BaseModel):
    contexto: str = Field(..., min_length=10, max_length=1500)
    nome: str = Field("", max_length=60)


def _processo_vivo(pid: int | None) -> bool:
    if not pid:
        return False
    try:
        os.kill(pid, 0)
    except (ProcessLookupError, PermissionError):
        return False
    return True


def _ler_status(pasta: Path) -> dict[str, Any] | None:
    processo = _PROCESSOS.get(pasta.name)
    if processo is not None and processo.poll() is not None:
        _PROCESSOS.pop(pasta.name, None)
    try:
        status = json.loads((pasta / "status.json").read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError):
        return None
    if status.get("estado") == "rodando" and not _processo_vivo(status.get("pid")):
        status["estado"] = "interrompida"
    return status


def _rodadas() -> list[dict[str, Any]]:
    if not PASTA_SAIDAS.exists():
        return []
    pastas = sorted((p for p in PASTA_SAIDAS.iterdir() if p.is_dir()), reverse=True)
    return [s for s in (_ler_status(p) for p in pastas) if s]


@router.get("/config")
def configuracao() -> dict[str, Any]:
    return {
        "llm_disponivel": llm.disponivel(),
        "modelo": llm.modelo(),
        "personas": [
            {"id": p.id, "descricao": p.descricao, "objetivo": p.objetivo, "roteiro": p.roteiro}
            for p in PERSONAS
        ],
        "contextos": contextos.listar(),
    }


@router.get("/contextos")
def listar_contextos() -> list[dict[str, Any]]:
    return contextos.listar()


@router.post("/contextos", status_code=201)
def criar_contexto(body: ContextoIn) -> dict[str, Any]:
    if not body.contexto.strip():
        raise HTTPException(status_code=422, detail="Descreva o lead que deve ser simulado.")
    return contextos.criar(body.contexto, body.nome)


@router.delete("/contextos/{contexto_id}")
def remover_contexto(contexto_id: str) -> dict[str, bool]:
    if not contextos.remover(contexto_id):
        raise HTTPException(status_code=404, detail="Contexto não encontrado")
    return {"removido": True}


@router.get("/rodadas")
def listar_rodadas() -> list[dict[str, Any]]:
    return [{k: v for k, v in s.items() if k != "execucoes"} for s in _rodadas()]


@router.post("/rodadas", status_code=202)
def iniciar_rodada(body: RodadaIn) -> dict[str, Any]:
    subindo = any(p.poll() is None for p in _PROCESSOS.values())
    if subindo or any(s["estado"] == "rodando" for s in _rodadas()):
        raise HTTPException(status_code=409, detail="Já existe uma rodada em andamento.")
    ids_contextos = {c["id"] for c in contextos.listar()}
    ids_validos = {p.id for p in PERSONAS} | ids_contextos
    desconhecidas = [p for p in body.personas if p not in ids_validos]
    if desconhecidas:
        raise HTTPException(status_code=422, detail=f"Personas desconhecidas: {', '.join(desconhecidas)}")
    if not (body.usar_llm and llm.disponivel()) and ids_contextos & set(body.personas):
        raise HTTPException(status_code=422, detail="Contextos personalizados só rodam com o lead e o juiz com IA ligados.")

    rodada_id = novo_id()
    PASTA_SAIDAS.mkdir(parents=True, exist_ok=True)
    cmd = [sys.executable, "-m", "treinador", "--id", rodada_id,
           "--rodadas", str(body.rodadas), "--max-turnos", str(body.max_turnos)]
    if body.personas:
        cmd += ["--personas", ",".join(body.personas)]
    if not body.usar_llm:
        cmd.append("--sem-llm")
    if not body.gerar_regressao:
        cmd.append("--sem-regressao")

    log = (PASTA_SAIDAS / f"{rodada_id}.log").open("w", encoding="utf-8")
    # Sessão própria: o --reload da API não derruba uma rodada em andamento.
    _PROCESSOS[rodada_id] = subprocess.Popen(
        cmd, cwd=RAIZ, stdout=log, stderr=subprocess.STDOUT, start_new_session=True
    )
    return {"id": rodada_id}


@router.get("/rodadas/{rodada_id}")
def obter_rodada(rodada_id: str) -> dict[str, Any]:
    pasta = PASTA_SAIDAS / rodada_id
    if pasta.parent != PASTA_SAIDAS:
        raise HTTPException(status_code=404, detail="Rodada não encontrada")
    status = _ler_status(pasta)
    if status is None:
        log = PASTA_SAIDAS / f"{rodada_id}.log"
        if log.exists():  # o processo ainda está subindo (ou caiu antes de gravar o status)
            return {"id": rodada_id, "estado": "iniciando", "log": log.read_text(encoding="utf-8")[-2000:]}
        raise HTTPException(status_code=404, detail="Rodada não encontrada")
    return status


@router.get("/rodadas/{rodada_id}/relatorio", response_class=PlainTextResponse)
def relatorio_rodada(rodada_id: str) -> str:
    caminho = PASTA_SAIDAS / rodada_id / "relatorio.md"
    if caminho.parent.parent != PASTA_SAIDAS or not caminho.exists():
        raise HTTPException(status_code=404, detail="Relatório ainda não disponível")
    return caminho.read_text(encoding="utf-8")


@router.get("/casos")
def listar_casos() -> list[dict[str, Any]]:
    casos = []
    for caminho in sorted(PASTA_CASOS.glob("*.json"), reverse=True):
        caso = json.loads(caminho.read_text(encoding="utf-8"))
        casos.append({
            "arquivo": caminho.name,
            "persona": caso.get("persona"),
            "persona_nome": caso.get("persona_nome"),
            "criado_em": caso.get("criado_em"),
            "mensagens_lead": caso.get("mensagens_lead") or [],
            "falhas_detectadas": caso.get("falhas_detectadas") or [],
        })
    return casos
