"""Conversas reprovadas nas verificações determinísticas viram casos em tests/regressao/casos/.

tests/regressao/test_casos_treinador.py reenvia as mensagens do lead ao agente (sem LLM, sem banco)
e falha enquanto as mesmas verificações acusarem problema.
"""
from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any

PASTA_CASOS = Path(__file__).resolve().parents[1] / "tests" / "regressao" / "casos"


def salvar_casos(execucoes: list[dict[str, Any]], *, pasta: Path = PASTA_CASOS) -> list[Path]:
    pasta.mkdir(parents=True, exist_ok=True)
    carimbo = datetime.now().strftime("%Y%m%d-%H%M%S")
    existentes = {
        tuple(json.loads(p.read_text(encoding="utf-8")).get("mensagens_lead") or [])
        for p in pasta.glob("*.json")
    }
    salvos = []
    for i, ex in enumerate(execucoes, start=1):
        falhas = ex["avaliacao"]["deterministicas"]
        mensagens = [m["texto"] for m in ex["conversa"] if m["papel"] == "lead"]
        if not falhas or tuple(mensagens) in existentes:
            continue
        caso = {
            "persona": ex["persona"],
            "persona_nome": ex.get("persona_nome") or ex["persona"],
            "persona_descricao": ex.get("persona_descricao") or "",
            "criado_em": datetime.now().isoformat(timespec="seconds"),
            "mensagens_lead": mensagens,
            "falhas_detectadas": falhas,
            "conversa_original": ex["conversa"],
        }
        caminho = pasta / f"{carimbo}-{ex['persona']}-{i}.json"
        caminho.write_text(json.dumps(caso, ensure_ascii=False, indent=2), encoding="utf-8")
        existentes.add(tuple(mensagens))
        salvos.append(caminho)
    return salvos
