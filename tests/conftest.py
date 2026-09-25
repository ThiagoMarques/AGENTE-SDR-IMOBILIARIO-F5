import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import config  # noqa: E402


@pytest.fixture(autouse=True)
def sem_llm(monkeypatch):
    """Testes rodam no modo determinístico (sem custo nem rede)."""
    monkeypatch.setattr(config, "OPENAI_API_KEY", "")
