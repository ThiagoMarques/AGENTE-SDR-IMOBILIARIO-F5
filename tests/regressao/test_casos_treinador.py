"""Casos gerados pelo treinador (python -m treinador): cada um falha até a conversa sair limpa."""
import json
from pathlib import Path

import pytest

from src.agente.sdr import processar_mensagem
from treinador.verificacoes import formatar_falhas, verificar_conversa

CASOS = sorted((Path(__file__).parent / "casos").glob("*.json"))


@pytest.mark.parametrize("caminho", CASOS, ids=[c.stem for c in CASOS])
def test_caso_do_treinador(caminho):
    caso = json.loads(caminho.read_text(encoding="utf-8"))
    lead_id = f"REG-{caminho.stem}"
    conversa = []
    for mensagem in caso["mensagens_lead"]:
        conversa.append({"papel": "lead", "texto": mensagem})
        conversa.append({"papel": "agente", "texto": processar_mensagem(lead_id, mensagem)["resposta"]})

    falhas = verificar_conversa(conversa)
    assert not falhas, f"persona {caso['persona']}:\n{formatar_falhas(falhas)}"
