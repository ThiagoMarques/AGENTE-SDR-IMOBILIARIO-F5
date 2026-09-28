# Roteiro de testes na tela (aplicação completa)

Testes manuais ponta a ponta: **chat (front) → API → Postgres → CRM simulado**.
Use **IDs de lead novos** em cada rodada, para que o histórico de testes anteriores não interfira.

## 0. Preparação

1. Postgres.app aberto, com status **Running**.
2. Limpe o CRM simulado. Com ele parado (Ctrl+C na aba do CRM):
   ```bash
   rm -f dados/crm_mock.json
   ```
3. Suba os três serviços, cada um numa aba do terminal, na raiz do projeto:
   ```bash
   python3 main.py --crm-servidor                        # aba 1
   python3 -m uvicorn api.app:app --reload --port 8000   # aba 2
   cd frontend && npm run dev                            # aba 3
   ```
4. Abra **http://localhost:5173** (chat/dashboard) e **http://127.0.0.1:8001** (CRM).

## 1. Qualificação

### T1 — Compra sem orçamento → **morno**
Lead: `TESTE-01`
| # | Mensagem | Esperado |
|---|---|---|
| 1 | Quero comprar apartamento na zona sul | Selo **Frio** (37). Agente confirma a intenção e pergunta a próxima informação |
| 2 | 2 quartos, é bem urgente | Selo **Morno**, pontuação **75**. Agente pergunta o orçamento |

- **CRM:** `TESTE-01`, **morno**, 75, último evento `lead_atualizado`.
- **Por quê:** o score é 75, mas sem orçamento a prioridade fica limitada a morno.

### T2 — Compra completa → **quente** e pronto para agendar
Continue no `TESTE-01`:
| # | Mensagem | Esperado |
|---|---|---|
| 3 | Até 700 mil | Selo **Quente**, pontuação **100**. Agente oferece horários de visita |

- **CRM:** `TESTE-01` passa para **quente**, com último evento `lead_qualificado`.
- A pontuação é a mesma no chat, na lista da esquerda, no dashboard e no CRM.

### T3 — Investidor → especialista
Lead: `TESTE-02`
| # | Mensagem | Esperado |
|---|---|---|
| 1 | Quero investir em imóveis para renda | Selo **Morno** (46). Agente pergunta o ticket |
| 2 | Ticket de 400 mil, espero 6% ao ano | Selo **Quente**, pontuação **94** |

- **CRM:** encaminhar para **especialista em investimentos**, ação "agendar conversa com especialista", último evento `lead_qualificado`.

### T4 — Curioso → **frio**
Lead: `TESTE-03`
| # | Mensagem | Esperado |
|---|---|---|
| 1 | Oi, só estou pesquisando preços, sem pressa | Selo **Frio** (9) |

- **CRM:** `TESTE-03` **não aparece**, porque sem intenção não há evento. Isso é o comportamento correto.

### T5 — Mensagem fora de escopo
No `TESTE-03`: "Quem ganhou o jogo ontem?"
- Agente responde que cuida só de imóveis e redireciona, sem sugerir imóveis. O perfil não muda.
- A pontuação sobe alguns pontos (9 → 14) porque a mensagem conta como engajamento. É esperado, mas continua **frio**.

## 2. Follow-up

### T6 — Retomar contato
1. Abra o `TESTE-01` e clique em **Retomar contato**.
2. **Esperado:** mensagem do agente retomando a conversa **com contexto** (menciona compra / zona sul).
3. Clique em **Retomar contato** de novo, sem responder como lead.
4. Gere o resumo (T8): nos pontos de atenção deve aparecer *"Lead não respondeu ao follow-up"*.

## 3. Dashboard do corretor

### T7 — Métricas e lista
Ícone de quadradinhos na barra lateral.
- Os contadores **Total / Quentes / Mornos / Frios** batem com os selos de cada lead. Depois de T1 a T9: 4 leads, sendo 3 quentes e 1 frio.
- Ao clicar num lead, aparecem o perfil, as últimas mensagens e a **Ação sugerida**.
- **Limitação conhecida:** o painel mostra só a ação sugerida. A sinopse, a justificativa do score, as objeções e os pontos de atenção vêm na API (`GET /leads/{id}/resumo`), mas ainda não aparecem na tela.

## 4. Resumo para o corretor

### T8 — Resumo completo
No terminal:
```bash
python3 main.py --resumo TESTE-01
```
- Imprime o resumo com prioridade, sinopse, "Por que essa prioridade", objeções e pontos de atenção.
- Gera `dados/saidas/resumo_TESTE-01.md` e `.json`.
- **CRM:** último evento `resumo_gerado`.
- Lead inexistente (`--resumo NAO-EXISTE`): mensagem "não encontrado", sem arquivo e sem evento no CRM.

### T9 — Objeções
Lead `TESTE-04`: "Quero comprar em Moema, 3 quartos, até 900 mil, mas achei o condomínio caro e preciso ver financiamento."
- `--resumo TESTE-04`: objeções **preço**, **custos fixos** e **financiamento**.

## 5. Agendamento

### T10 — Registro de visita
O chat **oferece** horários, mas não existe botão para **registrar** o agendamento. O registro é feito pela API:
```bash
curl -X POST http://127.0.0.1:8000/leads/TESTE-01/agendar \
  -H "Content-Type: application/json" -d '{"horario": "30/09/2026 10:00", "tipo": "visita"}'
```
- Dashboard: **Agendamentos** passa a 1.
- `--resumo TESTE-01`: ação sugerida "Confirmar reunião/visita com o corretor responsável".

## 6. Resiliência do CRM

### T11 — CRM fora do ar
1. Pare o CRM (Ctrl+C na aba 1).
2. No chat, crie o `TESTE-05` e envie "Quero alugar em Pinheiros, 2 quartos, até 4 mil, urgente".
3. **Esperado:** o chat **responde normalmente**, sem travar nem mostrar erro.
4. O arquivo `dados/crm_pendentes.jsonl` passa a existir.
5. Suba o CRM de novo e rode `python3 main.py --crm-reenviar` → `{"enviados": 1, "pendentes": 0}`. O `TESTE-05` aparece no painel.

## Registro dos resultados

| Teste | Resultado | Observação |
|---|---|---|
| T1 | | |
| T2 | | |
| T3 | | |
| T4 | | |
| T5 | | |
| T6 | | |
| T7 | | |
| T8 | | |
| T9 | | |
| T10 | | |
| T11 | | |
