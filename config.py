"""Configuração central do Agente SDR Imobiliário (Fase 5)."""
from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent
load_dotenv(ROOT / ".env")

# Runtime local (não versionado)
DADOS_DIR = ROOT / "dados"
CONVERSAS_DIR = DADOS_DIR / "conversas"
SAIDAS_DIR = DADOS_DIR / "saidas"

# Catálogo fake público (sem auth)
# Docs: https://fakeapifordevs.vercel.app/docs/realestate
IMOVEIS_API_BASE = (
    os.getenv("IMOVEIS_API_BASE") or "https://fakeapifordevs.vercel.app/api/realestate"
).rstrip("/")
IMOVEIS_API_TIMEOUT = float(os.getenv("IMOVEIS_API_TIMEOUT") or "20")

OPENAI_API_KEY = (os.getenv("OPENAI_API_KEY") or "").strip()
LLM_MODEL = (os.getenv("LLM_MODEL") or "gpt-4o-mini").strip()

SCORE_QUENTE = 70
SCORE_MORNO = 40
