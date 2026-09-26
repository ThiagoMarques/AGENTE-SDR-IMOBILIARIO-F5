# Qualificação de leads, resumo para corretores e integração com CRM

Responsável: Letícia.
Módulos: `src/qualificacao/`, `src/resumo/` e `src/crm/`.
Requisitos atendidos: "Qualificação de leads" e "Resumo inteligente". Diferencial: "Integração com CRM".

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
- **Merge com precedência do LLM:** quando o LLM extrai um campo, o valor dele
  vale sobre o da regex. Campos que ele não retornou nunca são apagados, e as
  objeções são acumuladas. *Por quê:* a bateria de validação mostrou erros da
  regex ("1,5 milhão" → 1, "minha renda" → investimento) que um merge só de
  lacunas preservaria mesmo com LLM ligado.
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
  (estruturado, o mesmo payload enviado ao CRM; veja a seção 3).

## 3. Integração com CRM (`src/crm/`)

**O que é:** o agente envia o lead ao CRM por **webhook HTTP (POST JSON)**. Para a
POC, o CRM é simulado em FastAPI (`src/crm/servidor_mock.py`), assim como a base
de imóveis. A integração em si é real: requisição HTTP, autenticação por token,
resposta e persistência no lado do CRM. Para usar um CRM de verdade (ou
n8n/Zapier), basta trocar `CRM_WEBHOOK_URL`.

**Quando envia (por evento, não a cada mensagem):**

| Evento | Quando |
|--------|--------|
| `lead_atualizado` | A prioridade do lead mudou (ex.: frio → quente) |
| `lead_qualificado` | O lead ficou pronto para agendar |
| `resumo_gerado` | O resumo foi gerado para o corretor (`--resumo` / `--demo`) |

Leads sem intenção identificada não são enviados, porque ainda não há o que
qualificar.

**Decisões de arquitetura:**
- **Adapter:** o agente depende de `CRMAdapter`, não de um fornecedor.
  `WebhookCRM` é a implementação atual. Um `HubSpotCRM` seria outra classe com o
  mesmo método `enviar`.
- **Resiliência:** falha de rede nunca derruba o atendimento. O evento vai para
  `dados/crm_pendentes.jsonl` e é reenviado com `python main.py --crm-reenviar`.
- **Idempotência:** o CRM faz upsert por `lead_id` e guarda o histórico de
  eventos, então reenvios não duplicam leads.
- **Segurança:** o token vem do `.env` (`CRM_WEBHOOK_TOKEN`) e é enviado como
  `Authorization: Bearer`. O CRM simulado recusa com 401 se o token não bater.

**CRM simulado:** `GET /` (painel HTML que atualiza sozinho, ordenado por score),
`GET /leads`, `GET /leads/{id}` e `POST /webhook/leads`.

## 4. Como rodar

```bash
pip install -r requirements.txt
cp .env.example .env
python -m pytest -q                 # 24 testes, sem internet e sem LLM

# terminal 1: CRM simulado -> abra http://127.0.0.1:8001
python main.py --crm-servidor

# terminal 2: agente
python main.py --demo               # 3 cenários; leads chegam no painel do CRM
python main.py --resumo LEAD-001    # resumo + evento resumo_gerado no CRM
python main.py --crm-reenviar       # reenvia eventos que falharam
```

## 5. Integração com o restante do projeto

- `score_lead(perfil)` mantém as chaves originais (`score`, `prioridade`,
  `campos_faltantes`, `pronto_para_agendar`) e adiciona `criterios`,
  `justificativa` e `encaminhamento`.
- `score_estado(estado)` inclui o engajamento e é usado em `sdr.py` e no dashboard.
- `montar_resumo(estado)` mantém as chaves antigas e adiciona novas.
- `processar_mensagem` devolve a chave `crm` com o status do envio (`None` quando não houve evento).
