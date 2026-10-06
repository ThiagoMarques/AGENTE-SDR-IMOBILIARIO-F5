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
    print(f"  database: {config.DATABASE_URL.split('@')[-1] if '@' in config.DATABASE_URL else config.DATABASE_URL}")
    print(f"  api_imoveis: {config.IMOVEIS_API_BASE}/listings")
    print(f"  LLM: {'configurado' if config.OPENAI_API_KEY else 'ausente (modo determinístico)'}")
    print(f"  modelo: {config.LLM_MODEL}")
    print(f"  CRM: {config.CRM_WEBHOOK_URL or 'desabilitado (defina CRM_WEBHOOK_URL)'}")
    from src.agenda.calendario import status as status_agenda

    agenda = status_agenda()
    ativas = [nome for nome, ok in agenda.items() if ok]
    print(f"  agenda: {', '.join(ativas) if ativas else 'só links/.ics (rode --agenda-auth google|outlook)'}")
    from src.agenda import email_convite

    print(
        f"  convite por e-mail: {email_convite.provedor()}"
        if email_convite.configurado()
        else "  convite por e-mail: desabilitado (defina EMAIL_FROM + RESEND_API_KEY ou SENDGRID_API_KEY)"
    )
    try:
        from src.db.session import init_db

        init_db()
        print("  db_ok: True")
    except Exception as exc:
        print(f"  db_ok: False ({exc})")
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
        "lead_id": out["lead_id"],
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
    from src.crm.cliente import EVENTO_RESUMO, sincronizar

    crm = sincronizar(estado, resumo, evento=EVENTO_RESUMO)
    memoria.salvar(estado)
    print(f"\nCRM: {crm['status'] if crm else 'sem envio'}")

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
            return {k: _clean(v) for k, v in obj.items()}
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
    if not estado.get("mensagens"):
        print(f"Lead {lead_id} não encontrado (nenhuma conversa salva).")
        return
    from src.crm.cliente import EVENTO_RESUMO, sincronizar

    resumo = montar_resumo(estado, usar_llm=True)
    print(formatar_resumo_txt(resumo))
    paths = exportar_resumo(resumo)
    print(f"\nSalvo em {paths['md']} e {paths['json']}")
    crm = sincronizar(estado, resumo, evento=EVENTO_RESUMO)
    memoria.salvar(estado)
    print(f"CRM: {crm['status'] if crm else 'sem envio'}")


def cmd_crm_servidor(porta: int) -> None:
    import uvicorn

    print(f"CRM simulado em http://127.0.0.1:{porta}  (webhook: /webhook/leads)")
    print(f"No .env do agente: CRM_WEBHOOK_URL=http://127.0.0.1:{porta}/webhook/leads")
    uvicorn.run("src.crm.servidor_mock:app", host="127.0.0.1", port=porta, log_level="warning")


def cmd_crm_reenviar() -> None:
    from src.crm.cliente import reenviar_pendentes

    print(json.dumps(reenviar_pendentes(), ensure_ascii=False))


def cmd_agenda_auth(provedor: str) -> None:
    from src.agenda.calendario import ErroAgenda
    from src.agenda.oauth import autorizar_google, autorizar_outlook

    try:
        if provedor == "google":
            autorizar_google()
        else:
            autorizar_outlook()
    except ErroAgenda as exc:
        raise SystemExit(str(exc)) from exc


def main() -> None:
    parser = argparse.ArgumentParser(description="Agente SDR Imobiliário — Fase 5")
    parser.add_argument("--checar", action="store_true", help="Valida pastas e credenciais")
    parser.add_argument("--demo", action="store_true", help="Roda os 3 cenários do desafio")
    parser.add_argument("--dashboard", action="store_true", help="Métricas mínimas das conversas")
    parser.add_argument("--chat", metavar="MSG", help="Envia mensagem ao agente")
    parser.add_argument("--lead", default="LEAD-DEMO", help="ID do lead (padrão LEAD-DEMO)")
    parser.add_argument("--resumo", metavar="LEAD_ID", help="Gera resumo para o corretor")
    parser.add_argument("--imoveis", action="store_true", help="Lista imóveis filtrados")
    parser.add_argument("--crm-servidor", action="store_true", help="Sobe o CRM simulado (FastAPI)")
    parser.add_argument("--crm-porta", type=int, default=8001)
    parser.add_argument("--crm-reenviar", action="store_true", help="Reenvia eventos pendentes ao CRM")
    parser.add_argument(
        "--agenda-auth",
        choices=["google", "outlook"],
        help="Conecta a agenda do corretor (Google Agenda ou Outlook)",
    )
    parser.add_argument("--intencao", choices=["compra", "aluguel", "investimento"])
    parser.add_argument("--regiao", type=str)
    parser.add_argument("--quartos", type=int)
    parser.add_argument("--preco-max", type=float)

    args = parser.parse_args()

    if args.crm_servidor:
        cmd_crm_servidor(args.crm_porta)
        return
    if args.crm_reenviar:
        cmd_crm_reenviar()
        return
    if args.agenda_auth:
        cmd_agenda_auth(args.agenda_auth)
        return
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
