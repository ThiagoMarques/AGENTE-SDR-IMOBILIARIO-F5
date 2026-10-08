"""Relatório em Markdown de uma rodada do treinador."""
from __future__ import annotations

from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

from treinador.avaliador import CRITERIOS, NOTA_MINIMA


def _trecho(conversa: list[dict[str, Any]], turno: int) -> str:
    """Mensagem do lead no turno e a resposta do agente a ela."""
    atual, linhas = 0, []
    for m in conversa:
        if m["papel"] == "lead":
            atual += 1
        if atual == turno:
            quem = "Lead" if m["papel"] == "lead" else "Agente"
            texto = m["texto"].replace("\n", " ")
            linhas.append(f"> **{quem}:** {texto[:300]}{'…' if len(texto) > 300 else ''}")
    return "\n>\n".join(linhas)


def montar(execucoes: list[dict[str, Any]], *, casos_salvos: list[Path], parametros: dict[str, Any]) -> str:
    total = len(execucoes)
    aprovadas = sum(1 for e in execucoes if e["avaliacao"]["aprovada"])
    medias_criterio: dict[str, list[float]] = defaultdict(list)
    for e in execucoes:
        for k, v in e["avaliacao"]["juiz"]["notas"].items():
            medias_criterio[k].append(v)

    out = [
        "# Relatório do treinador",
        "",
        f"- **Modo:** {parametros['modo']} · **lead simulado:** {parametros['lead']} · "
        f"**avaliação por LLM:** {'sim' if parametros['juiz'] else 'não'} · **modelo:** {parametros['modelo']}",
        f"- **Conversas:** {total} · **aprovadas:** {aprovadas} · **reprovadas:** {total - aprovadas} "
        f"(aprovação = nenhuma falha automática e média do juiz ≥ {NOTA_MINIMA})",
    ]
    if medias_criterio:
        out += ["", "## Notas médias do juiz (1 a 5)", ""]
        for k in CRITERIOS:
            if medias_criterio.get(k):
                vs = medias_criterio[k]
                out.append(f"- **{k}:** {sum(vs) / len(vs):.1f}")

    automaticas = Counter(f["tipo"] for e in execucoes for f in e["avaliacao"]["deterministicas"])
    qualitativas = Counter(f["tipo"] for e in execucoes for f in e["avaliacao"]["juiz"]["falhas"])
    if automaticas or qualitativas:
        out += ["", "## Falhas por tipo", ""]
        for tipo, n in automaticas.most_common():
            out.append(f"- `{tipo}` (automática): {n}")
        for tipo, n in qualitativas.most_common():
            out.append(f"- `{tipo}` (juiz): {n}")

    out += ["", "## Conversas", ""]
    for e in sorted(execucoes, key=lambda x: (x["avaliacao"]["aprovada"], x["avaliacao"]["media"] or 0)):
        av = e["avaliacao"]
        status = "aprovada" if av["aprovada"] else "reprovada"
        media = f"{av['media']:.1f}" if av["media"] is not None else "—"
        out += [f"### {e.get('persona_nome') or e['persona']} · {status} · média {media}", ""]
        if e["persona"].startswith("ctx_"):
            out += [f"> Contexto: {e.get('persona_descricao', '')}", ""]
        out += [f"Lead `{e['lead_id']}`, {len(e['conversa']) // 2} turnos, fim: {e['fim']}."]
        if av["juiz"]["resumo"]:
            out += ["", f"_{av['juiz']['resumo']}_"]
        for f in av["deterministicas"]:
            out += ["", f"**Automática, turno {f['turno']}, `{f['tipo']}`:** {f['descricao']}", "",
                    _trecho(e["conversa"], f["turno"])]
        for f in av["juiz"]["falhas"]:
            out += ["", f"**Juiz, turno {f['turno']}, `{f['tipo']}`:** {f['descricao']}"]
            if f["sugestao"]:
                out.append(f"Sugestão: {f['sugestao']}")
            trecho = _trecho(e["conversa"], f["turno"])
            if trecho:
                out += ["", trecho]
        out.append("")

    out += ["## Casos de regressão", ""]
    if casos_salvos:
        out.append("Novos casos (rode `pytest tests/regressao` para ver quais ainda falham sem LLM):")
        out += [f"- `{p.name}`" for p in casos_salvos]
    else:
        out.append("Nenhum caso novo.")
    return "\n".join(out) + "\n"
