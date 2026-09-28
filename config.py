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

