# Qualificação de leads e resumo para corretores

Responsável: Letícia. Módulos: `src/qualificacao/` e `src/resumo/`.
Requisitos atendidos: "Qualificação de leads" e "Resumo inteligente" (enunciado Fase 5).

## 1. Qualificação (`src/qualificacao/lead.py`)

### Score ponderado (inspirado em BANT)

| Critério      | Peso | Regra |
|---------------|-----:|-------|
| Necessidade   | 20 | Intenção identificada (compra, aluguel, investimento) |
| Detalhamento  | 25 | Região + quartos (compra/aluguel) ou retorno + perfil (investimento) |
| Orçamento     | 20 | Faixa de preço ou ticket informado |
| Prazo         | 20 | Urgência alta 20, média 12, baixa 4, sem informação 0 |
| Engajamento   | 15 | Mensagens do lead: 1 → 5, 2 → 10, 3+ → 15 |

Prioridade: **quente** ≥ 70, **morno** ≥ 40, **frio** < 40 (`config.py`).

**Por que ponderado?** A versão anterior media só o % de campos preenchidos, e
informar "quartos" valia o mesmo que informar orçamento. Um SDR real prioriza
pelo que indica chance de fechamento: necessidade, orçamento, prazo e engajamento.

**Por que explicável?** Cada critério devolve pontos e motivo. O corretor vê *por
que* o lead é quente. Isso é IA com humano no controle (human-in-the-loop), e não
uma nota caixa-preta.

**Encaminhamento:** investidores vão para "especialista em investimentos", como pede
o cenário 2 do enunciado.

### Extração com LLM (`src/qualificacao/extracao_llm.py`)

- Regex não entende "tenho uns 800k" ou "preciso mudar antes das férias".
- Com `OPENAI_API_KEY`, o LLM lê a mensagem no contexto das últimas mensagens e
  devolve JSON validado pelo schema Pydantic `PerfilExtraido`, com
  `temperature=0` e o prompt "não invente dados".
- **Merge conservador:** o LLM só preenche lacunas e nunca sobrescreve o que as
  regras já extraíram. Também acumula objeções citadas pelo cliente.
- **Fallback:** sem chave ou com erro, retorna `None` e o fluxo por regras segue.

## 2. Resumo para corretor (`src/resumo/corretor.py`)

Objetivo: o corretor entender o lead em 30 segundos, sem ler a conversa.

Conteúdo: prioridade e score, encaminhamento, ação sugerida, sinopse, perfil,
justificativa por critério, objeções, pontos de atenção, imóveis sugeridos,
agendamentos e últimas mensagens.

- **Objeções** (regras): preço, financiamento, localização, custos fixos,
  indecisão e decisão compartilhada.
- **Pontos de atenção**: lead quente e urgente (retornar hoje), investidor
  (especialista), catálogo sem aderência, lead aguardando resposta (gatilho de
  follow-up) e informações pendentes.
- **Sinopse com LLM** (`usar_llm=True`): um briefing em linguagem natural,
  validado pelo schema `SinopseLLM`. O padrão é `False` porque o agente monta o
  resumo a cada mensagem e não faz sentido pagar uma chamada de LLM por turno. A
  CLI (`--resumo`, `--demo`) liga o LLM na hora da entrega.
- **Exportação:** `dados/saidas/resumo_<lead>.md` (para humanos) e `.json`
  (pronto para CRM/webhook, um dos diferenciais do enunciado).

## 3. Como rodar

```bash
pip install -r requirements.txt
python -m pytest -q                 # 17 testes, sem rede e sem LLM
python main.py --demo               # 3 cenários + resumo do LEAD-001
python main.py --resumo LEAD-001    # resumo de um lead específico
```

## 4. Integração com o restante do projeto

- `score_lead(perfil)` mantém as chaves originais (`score`, `prioridade`,
  `campos_faltantes`, `pronto_para_agendar`) e adiciona `criterios`,
  `justificativa` e `encaminhamento`.
- `score_estado(estado)` inclui o engajamento e é usado em `sdr.py` e no dashboard.
- `montar_resumo(estado)` mantém as chaves antigas e adiciona novas.
