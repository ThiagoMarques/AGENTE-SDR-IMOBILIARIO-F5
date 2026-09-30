"""Configuração central do Agente SDR Imobiliário (Fase 5)."""
from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent
load_dotenv(ROOT / ".env")

# Runtime local (não versionado)
DADOS_DIR = ROOT / "dados"
CONVERSAS_DIR = DADOS_DIR / "conversas"  # legado; memória agora é Postgres
SAIDAS_DIR = DADOS_DIR / "saidas"

# PostgreSQL (docker compose: usuário/senha/db = sdr)
DATABASE_URL = (
    os.getenv("DATABASE_URL")
    or "postgresql+psycopg://sdr:sdr@localhost:5432/sdr"
).strip()

# Catálogo fake público (sem auth)
# Docs: https://fakeapifordevs.vercel.app/docs/realestate
IMOVEIS_API_BASE = (
    os.getenv("IMOVEIS_API_BASE") or "https://fakeapifordevs.vercel.app/api/realestate"
).rstrip("/")
IMOVEIS_API_TIMEOUT = float(os.getenv("IMOVEIS_API_TIMEOUT") or "20")
# br = catálogo sintético Brasil (padrão); fake = Fake Real Estate API (EUA)
IMOVEIS_SOURCE = (os.getenv("IMOVEIS_SOURCE") or "br").strip().lower()

OPENAI_API_KEY = (os.getenv("OPENAI_API_KEY") or "").strip()
LLM_MODEL = (os.getenv("LLM_MODEL") or "gpt-4o-mini").strip()

CORS_ORIGINS = [
    o.strip()
    for o in (os.getenv("CORS_ORIGINS") or "http://localhost:5173,http://127.0.0.1:5173").split(",")
    if o.strip()
]

SCORE_QUENTE = 70
SCORE_MORNO = 40

# Integração CRM via webhook (vazio = desabilitado)
# Para a demo: python main.py --crm-servidor  ->  http://127.0.0.1:8001/webhook/leads
CRM_WEBHOOK_URL = (os.getenv("CRM_WEBHOOK_URL") or "").strip()
CRM_WEBHOOK_TOKEN = (os.getenv("CRM_WEBHOOK_TOKEN") or "").strip()
CRM_TIMEOUT = float(os.getenv("CRM_TIMEOUT") or "3")
CRM_PENDENTES = DADOS_DIR / "crm_pendentes.jsonl"
CRM_MOCK_DB = DADOS_DIR / "crm_mock.json"

# Agenda: links/.ics funcionam sem credencial; Google/Outlook só com OAuth configurado.
# Tokens: python main.py --agenda-auth google|outlook  (salvos em dados/agenda_tokens.json)
AGENDA_TZ = (os.getenv("AGENDA_TZ") or "America/Sao_Paulo").strip()
AGENDA_DURACAO_MIN = int(os.getenv("AGENDA_DURACAO_MIN") or "60")
AGENDA_CORRETOR_EMAIL = (os.getenv("AGENDA_CORRETOR_EMAIL") or "").strip()
AGENDA_IMOBILIARIA = (os.getenv("AGENDA_IMOBILIARIA") or "Imobiliária").strip()
AGENDA_TIMEOUT = float(os.getenv("AGENDA_TIMEOUT") or "5")
AGENDA_TOKENS = DADOS_DIR / "agenda_tokens.json"

GOOGLE_CLIENT_ID = (os.getenv("GOOGLE_CLIENT_ID") or "").strip()
GOOGLE_CLIENT_SECRET = (os.getenv("GOOGLE_CLIENT_SECRET") or "").strip()
GOOGLE_REFRESH_TOKEN = (os.getenv("GOOGLE_REFRESH_TOKEN") or "").strip()
GOOGLE_CALENDAR_ID = (os.getenv("GOOGLE_CALENDAR_ID") or "primary").strip()

MS_CLIENT_ID = (os.getenv("MS_CLIENT_ID") or "").strip()
MS_CLIENT_SECRET = (os.getenv("MS_CLIENT_SECRET") or "").strip()
MS_TENANT = (os.getenv("MS_TENANT") or "common").strip()
MS_REFRESH_TOKEN = (os.getenv("MS_REFRESH_TOKEN") or "").strip()

