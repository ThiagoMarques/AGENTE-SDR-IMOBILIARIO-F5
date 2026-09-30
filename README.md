# Agente SDR Imobiliário com IA — Fase 5

Prova de conceito (POC) de um **SDR imobiliário com IA generativa**, desenvolvida no Hackathon da Fase 5 da pós-graduação **IA para Devs (FIAP PosTech)**.

O agente atende leads por um **chat web**, identifica se o cliente quer comprar, alugar ou investir e qualifica o lead com um score explicável. Ele também sugere imóveis de um catálogo simulado, faz follow-up, **agenda visitas pelo próprio chat (com integração ao Google Agenda e ao Outlook)**, gera um resumo para o corretor e sincroniza o lead com um CRM. O corretor acompanha tudo por um **dashboard**.

**Stack:** Python, FastAPI, PostgreSQL (Docker), React + Vite + TypeScript e OpenAI (opcional).

---

## Sumário

- [Problema de negócio](#problema-de-negócio)
- [Funcionalidades](#funcionalidades)
- [Arquitetura](#arquitetura)
- [Como a IA é usada](#como-a-ia-é-usada)
- [Estrutura do projeto](#estrutura-do-projeto)
- [Instalação](#instalação)
- [Como usar](#como-usar)
- [Testes](#testes)
- [Configuração (.env)](#configuração-env)
- [Segurança e privacidade](#segurança-e-privacidade)
- [Limitações conhecidas](#limitações-conhecidas)
- [Roadmap](#roadmap)
- [Solução de problemas](#solução-de-problemas)
- [Equipe](#equipe)

---

## Problema de negócio

Imobiliárias perdem leads por:

- tempo de resposta elevado;
- falta de acompanhamento;
- atendimento manual;
- dificuldade em priorizar leads quentes;
- sobrecarga dos corretores.

O agente assume o primeiro atendimento e a qualificação. O corretor recebe só o que importa: quem é o lead, quão quente ele está e qual o próximo passo. **A decisão final é sempre humana (human-in-the-loop).**

## Funcionalidades

| Objetivo do desafio | Status | Onde |
|---|---|---|
| Atender leads automaticamente | ✅ Chat web (React) e API REST | `frontend/`, `api/app.py`, `src/agente/sdr.py` |
| Conversa humanizada | ✅ LLM (se configurado) ou respostas por regras, com guardrails para mensagens fora de escopo | `src/agente/sdr.py` |
| Identificar intenção (compra, aluguel, investimento) | ✅ | `src/agente/sdr.py`, `src/qualificacao/extracao_llm.py` |
| Coletar informações relevantes | ✅ Funil com uma pergunta por vez + extração estruturada com LLM | `src/coleta/perfil.py`, `src/qualificacao/extracao_llm.py` |
| Qualificar clientes | ✅ Score ponderado 0–100 com justificativa | `src/qualificacao/lead.py` |
| Follow-up automático | ✅ Retoma a conversa com contexto | `src/agente/sdr.py` (`follow_up`), `POST /leads/{id}/follow-up` |
| Agendar reuniões ou visitas | ✅ O lead escolhe no chat ("amanhã às 10", "o segundo", "quinta 15h"); o agente registra, remarca, cancela e cria o evento no Google Agenda / Outlook do corretor | `src/agenda/`, `POST /leads/{id}/agendar` |
| Integrar com base simulada de imóveis | ✅ Catálogo sintético Brasil em BRL (padrão) ou [Fake Real Estate API](https://fakeapifordevs.vercel.app/docs/realestate) | `src/imoveis/` |
| Gerar resumos para corretores | ✅ Markdown + JSON, com sinopse por LLM | `src/resumo/corretor.py`, `GET /leads/{id}/resumo` |
| Dashboard mínimo | ✅ Página do corretor com leads por prioridade | `frontend/src/pages/DashboardPage.tsx`, `GET /dashboard` |

**Diferenciais implementados**

| Diferencial | O que foi feito |
|---|---|
| Memória conversacional | Histórico, perfil, agendamentos e imóveis sugeridos persistidos no PostgreSQL |
| Integração com CRM | Webhook HTTP por evento + CRM simulado em FastAPI com painel web (`src/crm/`) |
| Integração com agenda | Google Agenda (Calendar API) e Outlook (Microsoft Graph): evento na agenda do corretor, convite ao lead e consulta de horários ocupados. Sem credenciais, o lead recebe links "adicionar à agenda" e `.ics` (`src/agenda/`) |
| Segurança | Credenciais só no `.env`, token Bearer no webhook do CRM, dados sintéticos |

## Arquitetura

```
Frontend React (Chat + Dashboard) ──► API FastAPI (api/app.py) ──► processar_mensagem (src/agente/sdr.py)
                                                                      │
      ├─► Memória ............ histórico e perfil no PostgreSQL (src/memoria, src/db)
      ├─► Guardrails ......... fora de escopo não polui o perfil nem busca imóveis
      ├─► Extração ........... regras (regex) + LLM com schema Pydantic
      ├─► Qualificação ....... score ponderado, prioridade, encaminhamento
      ├─► Catálogo ........... catálogo BR sintético ou Fake Real Estate API (src/imoveis)
      ├─► Resposta ........... LLM (OpenAI) ou fluxo determinístico
      ├─► Agenda ............. horários livres, leitura da escolha, Google Agenda / Outlook (src/agenda)
      ├─► Resumo ............. pacote para o corretor (src/resumo)
      └─► CRM ................ webhook por evento ──► CRM simulado (FastAPI, :8001)
```

A CLI (`main.py`) usa o mesmo núcleo e serve para demonstrar os cenários do enunciado pelo terminal.

**Princípios de arquitetura**

- **Componentização:** front, API e núcleo são separados, e cada responsabilidade do núcleo fica num módulo em `src/` (agente, coleta, qualificação, catálogo, memória, agenda, resumo, CRM, dashboard).
- **LLM opcional com fallback:** sem `OPENAI_API_KEY` ou com falha na API, tudo continua funcionando no modo por regras.
- **Adapter para o CRM:** o agente depende de uma interface (`CRMAdapter`), não de um fornecedor. Trocar o CRM simulado por um real é só trocar a URL ou a implementação.
- **Resiliência:** uma falha no CRM não interrompe o atendimento. Os eventos ficam numa fila local e podem ser reenviados.
- **Adapter para a agenda:** Google e Outlook implementam a mesma interface (`criar`, `adicionar_convidados`, `cancelar`, `ocupados`). Se a API da agenda falhar, a visita continua registrada e os links/.ics continuam valendo.

Mais detalhes em [`docs/ARQUITETURA.txt`](docs/ARQUITETURA.txt) e [`docs/QUALIFICACAO_E_RESUMO.md`](docs/QUALIFICACAO_E_RESUMO.md).

## Como a IA é usada

| Onde | Técnica | Por quê |
|---|---|---|
| Resposta ao lead | LLM (`gpt-4o-mini` por padrão) com prompt de SDR: cordial, uma pergunta por vez, sem inventar imóveis fora da lista | Conversa natural e humanizada |
| Extração do perfil | LLM com saída JSON validada por **Pydantic**, `temperature=0`, instrução de não inventar dados | A regex não entende "uns 800k" ou "mudar antes das férias" |
| Merge regras + LLM | O campo extraído pelo LLM tem precedência; o que ele não retornar é mantido | Corrige erros da regex sem apagar informação |
| Qualificação | Score **ponderado e explicável** (inspirado em BANT) | O corretor vê *por que* o lead é quente |
| Resumo para o corretor | LLM gera sinopse, objeções e próximo passo (schema Pydantic); fallback por regras | Corretor entende o lead em 30 segundos |

### Score de qualificação

| Critério | Peso | Regra |
|---|---:|---|
| Necessidade | 20 | Intenção identificada |
| Detalhamento | 25 | Região + quartos (compra/aluguel) ou retorno + perfil (investimento) |
| Orçamento | 20 | Faixa de preço ou ticket informado |
| Prazo | 20 | Urgência alta 20, média 12, baixa 4 |
| Engajamento | 15 | Mensagens do lead: 1 → 5, 2 → 10, 3+ → 15 |

Prioridade: **quente** ≥ 70 · **morno** ≥ 40 · **frio** < 40. **Sem orçamento informado, o lead fica no máximo morno**, porque quente significa contato humano imediato e o corretor precisa saber quanto o cliente pode pagar. Investidores são encaminhados para o **especialista em investimentos**.

## Estrutura do projeto

```
.
├── main.py                     # CLI: demo, chat, resumo, dashboard, CRM
├── config.py                   # Configuração central (lê o .env)
├── docker-compose.yml          # PostgreSQL
├── requirements.txt
├── .env.example                # Modelo de variáveis de ambiente
├── api/app.py                  # API REST (FastAPI) usada pelo front
├── frontend/                   # React + Vite + TypeScript (Chat e Dashboard)
├── docs/
│   ├── ARQUITETURA.txt
│   └── QUALIFICACAO_E_RESUMO.md
├── src/
│   ├── agente/sdr.py           # Orquestração da conversa
│   ├── coleta/perfil.py        # Funil: campos por intenção e próxima pergunta
│   ├── qualificacao/
│   │   ├── lead.py             # Score, prioridade, encaminhamento
│   │   └── extracao_llm.py     # Extração estruturada com LLM
│   ├── imoveis/
│   │   ├── catalogo.py         # Busca (escolhe a fonte pelo IMOVEIS_SOURCE)
│   │   └── catalogo_br.py      # Catálogo sintético Brasil (BRL)
│   ├── memoria/conversa.py     # Memória do lead (usa src/db)
│   ├── db/                     # SQLAlchemy: modelos, sessão, repositórios
│   ├── agenda/
│   │   ├── scheduler.py        # Horários livres, leitura da escolha, agendar/remarcar/cancelar
│   │   ├── calendario.py       # Links Google/Outlook, .ics, Google Calendar API, Microsoft Graph
│   │   └── oauth.py            # Autorização única (--agenda-auth google|outlook)
│   ├── resumo/corretor.py      # Resumo para o corretor (.md e .json)
│   ├── crm/
│   │   ├── cliente.py          # Webhook, eventos, fila de pendentes
│   │   └── servidor_mock.py    # CRM simulado (FastAPI + painel)
│   └── dashboard/metricas.py   # Métricas agregadas
├── tests/                      # pytest (sem internet, sem LLM e sem banco)
└── dados/                      # Saídas geradas em runtime (fora do Git)
```

## Instalação

**Pré-requisitos:** Python 3.10+, Docker (para o PostgreSQL) e Node.js 18+ (para o front).

```bash
git clone https://github.com/ThiagoMarques/AGENTE-SDR-IMOBILIARIO-F5.git
cd AGENTE-SDR-IMOBILIARIO-F5

docker compose up -d             # sobe o PostgreSQL (usuário/senha/banco: sdr)

python3 -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env             # preencha OPENAI_API_KEY (opcional)

python main.py --checar          # valida banco, catálogo, LLM e CRM
```

> No macOS, se aparecer `CERTIFICATE_VERIFY_FAILED`, veja [Solução de problemas](#solução-de-problemas).

## Como usar

### Aplicação web (chat + dashboard)

Use três terminais, todos na raiz do projeto e com o `.venv` ativo nos dois primeiros:

```bash
# Terminal 1 — CRM simulado (painel em http://127.0.0.1:8001)
python main.py --crm-servidor

# Terminal 2 — API
uvicorn api.app:app --reload --port 8000

# Terminal 3 — front
cd frontend && npm install && npm run dev
```

Abra **http://localhost:5173**. No chat você conversa como lead; no dashboard, acompanha os leads como corretor. O front acessa a API pelo proxy `/api` do Vite.

**Principais rotas da API:** `POST /chat`, `GET /leads`, `GET /leads/{id}`, `GET /leads/{id}/resumo`, `POST /leads/{id}/follow-up`, `POST /leads/{id}/agendar`, `GET /leads/{id}/agendamentos/{n}/convite.ics`, `GET /dashboard`, `GET /health`.

### Agendamento de visitas (Google Agenda e Outlook)

Quando o lead está qualificado, o agente oferece três horários livres. O lead responde do jeito que falaria com uma pessoa ("pode ser amanhã às 10", "o segundo", "quinta 15h", "prefiro à tarde", "nenhum desses") e o agente confirma a visita. Também dá para remarcar ("preciso remarcar") e cancelar ("quero cancelar a visita"). Se o lead informar o e-mail, ele entra como convidado do evento.

A integração funciona em três níveis:

| Nível | Precisa de credencial? | O que acontece |
|---|---|---|
| Links e `.ics` | Não | O chat mostra os botões **Google Agenda**, **Outlook**, **Microsoft 365** e **Baixar .ics** para o lead salvar a visita |
| Evento na agenda do corretor | Sim | Evento criado via Google Calendar API ou Microsoft Graph, com convite por e-mail ao lead |
| Horários livres | Sim | O agente só oferece horários em que o corretor não tem compromisso |

**Conectar o Google Agenda (Gmail/Workspace)**

1. No [Google Cloud Console](https://console.cloud.google.com/), ative a **Google Calendar API**, configure a tela de consentimento e crie uma credencial OAuth do tipo **App para computador**.
2. Preencha `GOOGLE_CLIENT_ID` e `GOOGLE_CLIENT_SECRET` no `.env`.
3. Rode `python main.py --agenda-auth google`: o navegador abre, você autoriza e o token é salvo em `dados/agenda_tokens.json`.

**Conectar o Outlook (Outlook.com/Microsoft 365)**

1. No [Microsoft Entra](https://entra.microsoft.com/), registre um app com contas "qualquer diretório + pessoais", habilite **Permitir fluxos de cliente público** e adicione a permissão delegada `Calendars.ReadWrite`.
2. Preencha `MS_CLIENT_ID` no `.env` (e `MS_TENANT`, se for só da sua organização).
3. Rode `python main.py --agenda-auth outlook` e digite o código exibido em microsoft.com/devicelogin.

Confira com `python main.py --checar` (linha `agenda:`) ou `GET /health` (campo `agenda`).

### Demonstração pela CLI (3 cenários do desafio)

Com o PostgreSQL e o CRM simulado no ar:

```bash
python main.py --demo
```

A demo roda três cenários: **compra** ("apartamento na zona sul"), **investimento** ("investir para renda") e **follow-up** (lead que parou de responder). Ela também gera o resumo do `LEAD-001` em `dados/saidas/`. Os leads aparecem no painel do CRM, ordenados por score.

### Comandos da CLI

| Comando | O que faz |
|---|---|
| `python main.py --checar` | Valida banco, catálogo, LLM e CRM |
| `python main.py --demo` | Roda os 3 cenários do desafio |
| `python main.py --chat "Quero alugar em Pinheiros" --lead LEAD-10` | Envia uma mensagem como o lead informado |
| `python main.py --resumo LEAD-10` | Gera o resumo do corretor (`.md` e `.json`) e envia ao CRM |
| `python main.py --dashboard` | Mostra as métricas: leads por prioridade e agendamentos |
| `python main.py --imoveis --intencao compra --quartos 2 --preco-max 500000` | Consulta o catálogo |
| `python main.py --crm-servidor [--crm-porta 8001]` | Sobe o CRM simulado |
| `python main.py --crm-reenviar` | Reenvia eventos que falharam ao CRM |
| `python main.py --agenda-auth google` / `outlook` | Conecta a agenda do corretor (autorização única) |

### Exemplo de resumo para o corretor

```markdown
# Resumo do lead LEAD-001

**Prioridade:** QUENTE (score 95/100)
**Encaminhar para:** corretor
**Ação sugerida:** Lead qualificado: oferecer horários de visita/reunião.

## Sinopse
Lead com interesse em compra na região zona sul com 2+ quartos e orçamento
de até 500.000. Urgência alta. Classificado como quente (score 95).

## Por que essa prioridade
- Necessidade: 20/20 — Intenção identificada: compra.
- Detalhamento: 25/25 — Informou região, quartos.
- Orçamento: 20/20 — Orçamento informado: 500.000.
- Prazo: 20/20 — Urgência alta.
- Engajamento: 10/15 — 2 mensagem(ns) enviada(s) pelo lead.

## Pontos de atenção
- Lead quente com urgência alta: retornar ainda hoje.
```

## Testes

```bash
python -m pytest -q
```

Os testes rodam **sem internet, sem LLM e sem banco**: o catálogo é simulado, a chave da OpenAI é desligada e o PostgreSQL é trocado por uma memória em RAM. Eles cobrem:

- **Qualificação:** score, pesos, encaminhamento, merge entre regras e LLM.
- **Resumo:** conteúdo, objeções, pontos de atenção, exportação.
- **CRM:** envio HTTP real contra o CRM simulado, upsert, fila de pendentes, token e eventos disparados pelo agente.
- **LLM simulado:** cliente OpenAI falso para validar parsing, validação Pydantic e fallback.
- **Agenda:** leitura de horários em linguagem natural (sem falso positivo em "2 quartos" ou "900 mil"), horários livres, links Google/Outlook, `.ics` (RFC 5545), provedores Google/Microsoft com HTTP simulado, agendar/remarcar/cancelar pelo chat, contador do dashboard e rota `.ics`.
- **Validação ponta a ponta:** 12 conversas realistas pelo fluxo completo. Os casos marcados como `xfail` são **defeitos conhecidos** da extração por regex (ver [Limitações conhecidas](#limitações-conhecidas)). Quando um deles for corrigido, o teste acusa XPASS, avisando para remover a marcação.

## Configuração (.env)

| Variável | Obrigatória | Padrão | Descrição |
|---|---|---|---|
| `DATABASE_URL` | Não | `postgresql+psycopg://sdr:sdr@localhost:5432/sdr` | Conexão com o PostgreSQL (igual ao `docker-compose.yml`) |
| `OPENAI_API_KEY` | Não | — | Liga o LLM (resposta, extração e sinopse). Sem ela, o modo é por regras. |
| `LLM_MODEL` | Não | `gpt-4o-mini` | Modelo da OpenAI |
| `IMOVEIS_SOURCE` | Não | `br` | `br` = catálogo sintético Brasil (BRL); `fake` = Fake Real Estate API (EUA) |
| `IMOVEIS_API_BASE` | Não | Fake Real Estate API | Base da API externa (só com `IMOVEIS_SOURCE=fake`) |
| `IMOVEIS_API_TIMEOUT` | Não | `20` | Timeout da API de imóveis (segundos) |
| `CORS_ORIGINS` | Não | `http://localhost:5173,http://127.0.0.1:5173` | Origens liberadas para o front |
| `CRM_WEBHOOK_URL` | Não | — | URL do webhook do CRM. Vazio desabilita. |
| `CRM_WEBHOOK_TOKEN` | Não | — | Token Bearer exigido pelo CRM |
| `CRM_TIMEOUT` | Não | `3` | Timeout do envio ao CRM (segundos) |
| `AGENDA_TZ` | Não | `America/Sao_Paulo` | Fuso dos horários oferecidos |
| `AGENDA_DURACAO_MIN` | Não | `60` | Duração da visita (minutos) |
| `AGENDA_IMOBILIARIA` | Não | `Imobiliária` | Nome usado no título do evento |
| `AGENDA_CORRETOR_EMAIL` | Não | — | Contato exibido no convite do lead |
| `GOOGLE_CLIENT_ID` / `GOOGLE_CLIENT_SECRET` | Não | — | Credencial OAuth (App para computador) do Google |
| `GOOGLE_CALENDAR_ID` | Não | `primary` | Agenda do corretor no Google |
| `MS_CLIENT_ID` / `MS_TENANT` | Não | — / `common` | App do Microsoft Entra para o Outlook |

## Segurança e privacidade

- As credenciais ficam só no `.env`, que **não é versionado**.
- O catálogo usa dados **sintéticos** (catálogo BR gerado ou API fake pública).
- O webhook do CRM aceita autenticação por token Bearer, e o CRM simulado responde 401 se o token não bater.
- As conversas ficam no PostgreSQL local, e as saídas geradas em `dados/`, fora do Git.
- Os tokens da agenda ficam em `dados/agenda_tokens.json` (permissão 600, fora do Git). Os escopos pedidos são só os de eventos e disponibilidade da agenda.
- O evento enviado ao lead não leva score nem prioridade: só os dados que ele mesmo informou.
- O agente **não fecha negócio sozinho**: ele qualifica e resume, e a decisão é do corretor.

## Limitações conhecidas

- **Extração por regex** (usada quando não há LLM ou ele falha) erra em alguns formatos:
  - "800k" não é reconhecido;
  - "dois quartos" (por extenso) não é lido;
  - bairros fora da lista fixa são ignorados;
  - prazos como "esse mês" e "em 3 meses" não viram urgência;
  - "agora estou só olhando" marca urgência alta;
  - "minha renda é…" junto com "alugar" vira investimento.

  Todos estão documentados em `tests/test_validacao_qualificacao.py`. Com o LLM ligado, a extração dele tem precedência e corrige boa parte desses casos.
- **Com `IMOVEIS_SOURCE=fake`, uma falha na API externa interrompe a conversa.** O catálogo BR (padrão) é local e não tem esse risco.
- **O CRM é simulado.** A integração (HTTP, token, eventos) é real, mas o destino é um servidor local.
- **Agenda:** sem credenciais, os horários oferecidos são janelas padrão (10h, 14h e 16h, sem domingo) e não há checagem de conflito. A agenda é de um único corretor, sem rodízio entre corretores.
- **O webhook de canal (`POST /webhooks/canal`) é um stub**, ou seja, um gancho preparado para WhatsApp/Chatwoot, sem integração ativa.

## Roadmap

- RAG sobre FAQs da imobiliária
- Canal WhatsApp / Chatwoot (gancho em `POST /webhooks/canal`)
- Multiagentes (qualificador, buscador, agendador)
- Voice AI
- CRM real (ex.: HubSpot, via novo adapter)
- Observabilidade e deploy em cloud

## Solução de problemas

### macOS: `CERTIFICATE_VERIFY_FAILED` ao consultar a API de imóveis

> Só ocorre com a API externa (`IMOVEIS_SOURCE=fake`). O catálogo BR padrão não acessa a internet.

Se o `python3 main.py --demo` falhar com
`ssl.SSLCertVerificationError: [SSL: CERTIFICATE_VERIFY_FAILED] certificate verify failed: unable to get local issuer certificate`,
o Python foi instalado pelo site python.org e ainda não tem os certificados configurados.
O problema é do ambiente, não do código.

Rode uma única vez (troque `3.14` pela sua versão do Python):

```bash
"/Applications/Python 3.14/Install Certificates.command"
```

Ou abra **Aplicativos → Python 3.x** e dê dois cliques em **Install Certificates.command**.
Depois, rode a demo de novo.

## Equipe

| Integrante | Contribuição |
|---|---|
| Thiago Marques | Estrutura do agente, conversa humanizada e guardrails, catálogo BR, API FastAPI, front React, PostgreSQL |
| Letícia | Qualificação de leads, resumo para corretores, integração com CRM, testes |

<!-- Completar com os demais integrantes e suas contribuições. -->

---

Projeto acadêmico — FIAP PosTech, IA para Devs, Fase 5 (Hackathon).
