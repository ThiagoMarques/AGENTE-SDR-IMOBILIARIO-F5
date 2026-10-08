"""python -m treinador [--modo local|api] [--personas a,b] [--rodadas N] [--sem-llm] [--limpar]"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ))

from treinador import llm  # noqa: E402
from treinador.canal import PREFIXO_LEAD  # noqa: E402
from treinador.contextos import como_persona  # noqa: E402
from treinador.execucao import PASTA_SAIDAS, executar, novo_id  # noqa: E402
from treinador.personas import PERSONAS, por_id  # noqa: E402


def _limpar_banco() -> None:
    from sqlalchemy import select

    from src.db.models import Lead
    from src.db.session import session_scope

    sessao = session_scope()
    try:
        leads = sessao.scalars(select(Lead).where(Lead.id.like(f"{PREFIXO_LEAD}%"))).all()
        for lead in leads:
            sessao.delete(lead)
        sessao.commit()
        print(f"{len(leads)} lead(s) {PREFIXO_LEAD}* removido(s) do PostgreSQL.")
    finally:
        sessao.close()


def _imprimir(resultado: dict) -> None:
    av = resultado["avaliacao"]
    media = f"{av['media']:.1f}" if av["media"] is not None else "—"
    print(f"→ {resultado['persona']}: {'ok' if av['aprovada'] else 'REPROVADA'} · média {media} · "
          f"{len(av['deterministicas'])} automática(s) · {len(av['juiz']['falhas'])} do juiz", flush=True)


def main() -> None:
    p = argparse.ArgumentParser(prog="python -m treinador", description="Simula leads, avalia o agente e gera regressões.")
    p.add_argument("--modo", choices=("local", "api"), default="local",
                   help="local: agente no mesmo processo, memória em RAM (padrão). api: HTTP no /chat, grava no banco.")
    p.add_argument("--url", default="http://localhost:8000", help="URL da API no modo api.")
    p.add_argument("--personas", default="", help=f"Ids separados por vírgula (fixas ou contextos ctx_*). Fixas: {', '.join(x.id for x in PERSONAS)}")
    p.add_argument("--contexto", action="append", default=[],
                   help='Lead descrito em texto livre, ex.: "senhor de idade que fala pausadamente". Pode repetir; exige LLM.')
    p.add_argument("--rodadas", type=int, default=1, help="Conversas por persona (com LLM cada uma sai diferente).")
    p.add_argument("--max-turnos", type=int, default=12)
    p.add_argument("--sem-llm", action="store_true", help="Usa os roteiros fixos e só as verificações automáticas.")
    p.add_argument("--sem-regressao", action="store_true", help="Não grava casos em tests/regressao/casos.")
    p.add_argument("--id", default="", help="Nome da pasta da rodada em treinador/saidas (padrão: data e hora).")
    p.add_argument("--limpar", action="store_true", help=f"Remove do PostgreSQL os leads {PREFIXO_LEAD}* e sai.")
    args = p.parse_args()

    if args.limpar:
        _limpar_banco()
        return
    if not llm.disponivel() and not args.sem_llm:
        print("OPENAI_API_KEY ausente: usando roteiros fixos e só verificações automáticas.")

    ids = [x.strip() for x in args.personas.split(",") if x.strip()]
    avulsos = [como_persona({"id": f"ctx_avulso_{i + 1}", "nome": f"Contexto {i + 1}", "contexto": texto})
               for i, texto in enumerate(args.contexto)]
    personas = (por_id(ids) if ids or not avulsos else []) + avulsos

    pasta = PASTA_SAIDAS / (args.id or novo_id())
    status = executar(
        personas,
        modo=args.modo,
        url=args.url,
        rodadas=args.rodadas,
        max_turnos=args.max_turnos,
        sem_llm=args.sem_llm,
        gerar_regressao=not args.sem_regressao,
        pasta=pasta,
        ao_progresso=_imprimir,
    )

    if status["parametros"]["ignoradas_sem_llm"]:
        print(f"Ignoradas por falta de LLM (sem roteiro): {', '.join(status['parametros']['ignoradas_sem_llm'])}")
    if status["estado"] == "erro":
        print(f"\nA rodada falhou: {status['erro']}")
        sys.exit(1)
    print(f"\n{status['resumo']['aprovadas']}/{status['total']} aprovadas. Relatório: {pasta / 'relatorio.md'}")
    if status["casos"]:
        print(f"{len(status['casos'])} caso(s) de regressão novo(s) em tests/regressao/casos/")
    if args.modo == "api":
        print(f"Os leads {PREFIXO_LEAD}* ficaram no banco; remova com: python -m treinador --limpar")


if __name__ == "__main__":
    main()
