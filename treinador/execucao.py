"""Uma rodada do treinador, gravando o progresso em disco a cada conversa.

A pasta da rodada (treinador/saidas/<id>/) tem:
- status.json: estado (rodando/concluida/erro), progresso, parâmetros e as conversas já avaliadas;
- conversas.json e relatorio.md ao final.
A API e a tela só leem esses arquivos: o treinador roda em outro processo.
"""
from __future__ import annotations

import json
import os
import traceback
from contextlib import nullcontext
from datetime import datetime
from pathlib import Path
from typing import Any

from treinador import llm
from treinador.avaliador import avaliar
from treinador.canal import CanalApi, CanalLocal, ambiente_isolado
from treinador.personas import Persona
from treinador.regressao import salvar_casos
from treinador.relatorio import montar
from treinador.simulador import conversar

PASTA_SAIDAS = Path(__file__).resolve().parent / "saidas"


def novo_id() -> str:
    return datetime.now().strftime("%Y%m%d-%H%M%S")


def gravar_json(caminho: Path, dados: Any) -> None:
    tmp = caminho.with_suffix(".tmp")
    tmp.write_text(json.dumps(dados, ensure_ascii=False, indent=2), encoding="utf-8")
    os.replace(tmp, caminho)  # quem lê nunca vê o arquivo pela metade


def _resumo(execucoes: list[dict[str, Any]]) -> dict[str, Any]:
    medias = [e["avaliacao"]["media"] for e in execucoes if e["avaliacao"]["media"] is not None]
    return {
        "aprovadas": sum(1 for e in execucoes if e["avaliacao"]["aprovada"]),
        "media": round(sum(medias) / len(medias), 2) if medias else None,
        "falhas_automaticas": sum(len(e["avaliacao"]["deterministicas"]) for e in execucoes),
        "falhas_juiz": sum(len(e["avaliacao"]["juiz"]["falhas"]) for e in execucoes),
    }


def executar(
    personas: list[Persona],
    *,
    modo: str,
    url: str,
    rodadas: int,
    max_turnos: int,
    sem_llm: bool,
    gerar_regressao: bool,
    pasta: Path,
    ao_progresso=None,
) -> dict[str, Any]:
    pasta.mkdir(parents=True, exist_ok=True)
    usar_llm = llm.disponivel() and not sem_llm
    sem_roteiro = [] if usar_llm else [p.id for p in personas if not p.roteiro]
    personas = [p for p in personas if p.id not in sem_roteiro]  # contexto livre só roda com o LLM
    parametros = {
        "modo": modo,
        "personas": [p.id for p in personas],
        "ignoradas_sem_llm": sem_roteiro,
        "rodadas": rodadas,
        "max_turnos": max_turnos,
        "lead": "LLM" if usar_llm else "roteiro",
        "juiz": usar_llm,
        "modelo": llm.modelo() if usar_llm else "—",
        "gerar_regressao": gerar_regressao,
    }
    status: dict[str, Any] = {
        "id": pasta.name,
        "estado": "rodando",
        "pid": os.getpid(),
        "inicio": datetime.now().isoformat(timespec="seconds"),
        "fim": None,
        "parametros": parametros,
        "total": len(personas) * rodadas,
        "concluidas": 0,
        "atual": None,
        "execucoes": [],
        "resumo": _resumo([]),
        "casos": [],
        "erro": None,
    }
    caminho_status = pasta / "status.json"
    gravar_json(caminho_status, status)

    canal = CanalApi(url) if modo == "api" else CanalLocal()
    contexto = ambiente_isolado() if modo == "local" else nullcontext()
    execucoes: list[dict[str, Any]] = []
    try:
        with contexto:
            for persona in personas:
                for rodada in range(rodadas):
                    status["atual"] = {"persona": persona.id, "persona_nome": persona.rotulo, "rodada": rodada + 1}
                    gravar_json(caminho_status, status)
                    resultado = conversar(persona, canal, usar_llm=usar_llm, max_turnos=max_turnos)
                    resultado["avaliacao"] = avaliar(persona, resultado, usar_llm=usar_llm)
                    execucoes.append(resultado)
                    status.update(concluidas=len(execucoes), execucoes=execucoes, resumo=_resumo(execucoes))
                    gravar_json(caminho_status, status)
                    if ao_progresso:
                        ao_progresso(resultado)

        casos = salvar_casos(execucoes) if gerar_regressao else []
        gravar_json(pasta / "conversas.json", execucoes)
        (pasta / "relatorio.md").write_text(
            montar(execucoes, casos_salvos=casos, parametros=parametros), encoding="utf-8"
        )
        status.update(estado="concluida", casos=[p.name for p in casos])
    except Exception as exc:
        status.update(estado="erro", erro=f"{type(exc).__name__}: {exc}\n{traceback.format_exc(limit=3)}")
    finally:
        status.update(fim=datetime.now().isoformat(timespec="seconds"), atual=None)
        gravar_json(caminho_status, status)
    return status
