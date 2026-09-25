"""
Ponto de entrada — Agente SDR Imobiliário (Tech Challenge Fase 5).
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import config


def checar_ambiente() -> None:
    for d in (config.CONVERSAS_DIR, config.SAIDAS_DIR):
        d.mkdir(parents=True, exist_ok=True)

    print("AGENTE-SDR-IMOBILIARIO — ambiente")
    print(f"  raiz: {config.ROOT}")
    print(f"  api_imoveis: {config.IMOVEIS_API_BASE}/listings")
    print(f"  LLM: {'configurado' if config.OPENAI_API_KEY else 'ausente (modo determinístico)'}")
    print(f"  modelo: {config.LLM_MODEL}")
    try:
        from src.imoveis.catalogo import buscar

        amostra = buscar(intencao="compra", limite=1)
        print(f"  api_ok: {bool(amostra)} ({amostra[0]['id'] if amostra else 'sem itens'})")
    except Exception as exc:
        print(f"  api_ok: False ({exc})")


def cmd_imoveis(intencao: str | None, regiao: str | None, quartos: int | None, preco_max: float | None) -> None:
    from src.imoveis.catalogo import buscar, formatar_imovel

    itens = buscar(intencao=intencao, regiao=regiao, quartos_min=quartos, preco_max=preco_max)
    if not itens:
        print("Nenhum imóvel encontrado com esses filtros.")
        return
    for im in itens:
        print(formatar_imovel(im))
        print()


def cmd_chat(lead_id: str, mensagem: str) -> None:
    from src.agente.sdr import processar_mensagem

    out = processar_mensagem(lead_id, mensagem)
    print(out["resposta"])
    print()
    print("---")
    print(json.dumps({
        "perfil": out["perfil"],
        "qualificacao": out["qualificacao"],
        "imoveis": [i["id"] for i in out["imoveis"]],
        "conversa": out["conversa_path"],
    }, ensure_ascii=False, indent=2))


def cmd_demo() -> None:
    """Roda os 3 cenários do enunciado (compra, investimento, follow-up)."""
    from src.agente.sdr import follow_up, processar_mensagem
    from src.resumo.corretor import exportar_resumo, formatar_resumo_txt, montar_resumo
    from src.memoria import conversa as memoria

    print("=== Cenário 1 — Compra ===\n")
    r1 = processar_mensagem("LEAD-001", "Estou procurando apartamento na zona sul.")
    print(r1["resposta"], "\n")
    r1b = processar_mensagem(
        "LEAD-001",
        "Quero 2 ou 3 quartos, até 500 mil dólares, com certa urgência essa semana.",
    )
    print(r1b["resposta"], "\n")

    print("=== Cenário 2 — Investimento ===\n")
    r2 = processar_mensagem("LEAD-002", "Quero investir em imóveis para renda.")
    print(r2["resposta"], "\n")
    r2b = processar_mensagem(
        "LEAD-002",
        "Ticket de 400 mil, espero cerca de 6% ao ano com locação.",
    )
    print(r2b["resposta"], "\n")

    print("=== Cenário 3 — Follow-up ===\n")
    processar_mensagem("LEAD-003", "Vi um apto em Austin, mas precisei sair.")
    r3 = follow_up("LEAD-003")
    print(r3["resposta"], "\n")

    print("=== Resumo para corretor (LEAD-001) ===\n")
    estado = memoria.carregar("LEAD-001")
    resumo = montar_resumo(estado, usar_llm=True)
    texto = formatar_resumo_txt(resumo)
    print(texto)
    exportar_resumo(resumo)

    config.SAIDAS_DIR.mkdir(parents=True, exist_ok=True)
    out = config.SAIDAS_DIR / "demo_cenarios.json"
    payload = {
        "compra": r1b,
        "investimento": r2b,
        "follow_up": r3,
        "resumo_lead_001": resumo,
    }
    # serialização segura (sem path objects)
    def _clean(obj):
        if isinstance(obj, dict):
            return {k: _clean(v) for k, v in obj.items() if k != "conversa_path"}
        if isinstance(obj, list):
            return [_clean(x) for x in obj]
        return obj

    out.write_text(json.dumps(_clean(payload), ensure_ascii=False, indent=2), encoding="utf-8")
    (config.SAIDAS_DIR / "resumo_LEAD-001.txt").write_text(texto, encoding="utf-8")
    print(f"\nSaídas em {config.SAIDAS_DIR}")


def cmd_dashboard() -> None:
    from src.dashboard.metricas import montar_dashboard

    dash = montar_dashboard()
    print(json.dumps(dash, ensure_ascii=False, indent=2))


def cmd_resumo(lead_id: str) -> None:
    from src.memoria import conversa as memoria
    from src.resumo.corretor import exportar_resumo, formatar_resumo_txt, montar_resumo

    estado = memoria.carregar(lead_id)
    resumo = montar_resumo(estado, usar_llm=True)
    print(formatar_resumo_txt(resumo))
    paths = exportar_resumo(resumo)
    print(f"\nSalvo em {paths['md']} e {paths['json']}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Agente SDR Imobiliário — Fase 5")
    parser.add_argument("--checar", action="store_true", help="Valida pastas e credenciais")
    parser.add_argument("--demo", action="store_true", help="Roda os 3 cenários do desafio")
    parser.add_argument("--dashboard", action="store_true", help="Métricas mínimas das conversas")
    parser.add_argument("--chat", metavar="MSG", help="Envia mensagem ao agente")
    parser.add_argument("--lead", default="LEAD-DEMO", help="ID do lead (padrão LEAD-DEMO)")
    parser.add_argument("--resumo", metavar="LEAD_ID", help="Gera resumo para o corretor")
    parser.add_argument("--imoveis", action="store_true", help="Lista imóveis filtrados")
    parser.add_argument("--intencao", choices=["compra", "aluguel", "investimento"])
    parser.add_argument("--regiao", type=str)
    parser.add_argument("--quartos", type=int)
    parser.add_argument("--preco-max", type=float)

    args = parser.parse_args()

    if args.checar:
        checar_ambiente()
        return
    if args.demo:
        cmd_demo()
        return
    if args.dashboard:
        cmd_dashboard()
        return
    if args.resumo:
        cmd_resumo(args.resumo)
        return
    if args.chat:
        cmd_chat(args.lead, args.chat)
        return
    if args.imoveis:
        cmd_imoveis(args.intencao, args.regiao, args.quartos, args.preco_max)
        return

    parser.print_help()


if __name__ == "__main__":
    main()
