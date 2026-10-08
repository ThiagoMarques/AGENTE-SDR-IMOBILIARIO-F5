"""Treinador externo do agente SDR.

Simula leads conversando com o agente, avalia as conversas (regras + LLM juiz),
gera casos de regressão e um relatório de melhorias. Não altera o agente:
as correções continuam passando por pessoas e pelos testes.

Uso: python -m treinador --help
"""
