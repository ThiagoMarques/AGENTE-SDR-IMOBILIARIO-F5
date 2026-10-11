# Agente SDR Imobiliário com IA — Fase 5

Prova de conceito (POC) de um **SDR imobiliário com IA generativa**, desenvolvida no Hackathon da Fase 5 da pós-graduação **IA para Devs (FIAP PosTech)**.

O agente atende leads por um **chat web** (e, como demonstração educativa, por um bot do Telegram), identifica se o cliente quer comprar, alugar ou investir e qualifica o lead com um score explicável. Ele também sugere imóveis de um catálogo simulado, faz follow-up, **agenda visitas pelo próprio chat (com integração ao Google Agenda e ao Outlook)**, gera um resumo para o corretor e sincroniza o lead com um CRM. O corretor acompanha tudo por um **dashboard**.

Para melhorar o agente de forma contínua, o projeto tem um **treinador**: leads simulados por IA (personas prontas ou descritas em texto livre) conversam com o agente, um juiz com IA avalia cada conversa e as falhas encontradas viram testes de regressão. Tudo isso pode ser disparado e acompanhado por uma tela no próprio front.

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
| Atender leads automaticamente | ✅ Chat web (React) na visão do lead e na inbox do corretor, e API REST | `frontend/`, `api/app.py`, `src/agente/sdr.py` |
| Conversa humanizada | ✅ Confirma o que entendeu e faz uma pergunta por vez; aceita dados fora de ordem, correções ("na verdade 3 quartos"), mudança de ideia, dúvidas no meio da conversa e mensagens fora de escopo | `src/agente/sdr.py` |
| Identificar intenção (compra, aluguel, investimento) | ✅ Tolerante a erro de digitação ("alugr", "zuna sul") | `src/qualificacao/interpretador.py` |
| Coletar informações relevantes | ✅ Motor de fluxo que recalcula o próximo dado faltante a cada mensagem + interpretação por regras com LLM opcional | `src/qualificacao/fluxo_conversa.py`, `src/qualificacao/interpretador.py` |
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
| Canal de mensagem (demonstração educativa) | Bot do Telegram que leva o lead ao mesmo agente do chat web, com horários em botões e convite `.ics` no chat. O WhatsApp entra pelo mesmo caminho (ver [Canal Telegram](#canal-telegram-demonstração-educativa)) |
| Treinador do agente (avaliação contínua) | Leads simulados por LLM conversam com o agente; verificações automáticas e um LLM juiz com rubrica dão nota a cada conversa; as falhas viram casos de regressão no `pytest`. Tela própria no front (`/treinador`) e CLI (`python -m treinador`) |

## Arquitetura

![Diagrama de arquitetura](docs/img/arquitetura.png)

```
Frontend React (lead, inbox, dashboard, treinador) ──► API FastAPI (api/app.py) ──► processar_mensagem (src/agente/sdr.py)
                                                                      │
      ├─► Memória ............ histórico e perfil no PostgreSQL (src/memoria, src/db)
      ├─► Contato ............ nome, e-mail e escolha de horário (src/qualificacao/contato.py)
      ├─► Interpretação ...... regras tolerantes a erro + LLM opcional que só devolve dados estruturados
      ├─► Fluxo .............. próximo dado faltante, recalculado a cada mensagem (fluxo_conversa.py)
      ├─► Guardrails ......... fora de escopo não polui o perfil nem busca imóveis
      ├─► Qualificação ....... score ponderado, prioridade, encaminhamento
      ├─► Catálogo ........... catálogo BR sintético ou Fake Real Estate API (src/imoveis)
      ├─► Resposta ........... montada pelo Python a partir do estado (sem texto livre do LLM)
      ├─► Agenda ............. horários livres, leitura da escolha, Google Agenda / Outlook (src/agenda)
      ├─► Resumo ............. pacote para o corretor (src/resumo)
      └─► CRM ................ webhook por evento ──► CRM simulado (FastAPI, :8001)

Treinador (processo separado: python -m treinador, disparado pela tela /treinador via api/treinador.py)
      ├─► Lead simulado ...... persona fixa ou contexto em texto livre (LLM) ou roteiro fixo (sem LLM)
      ├─► Agente ............. o mesmo processar_mensagem, com memória em RAM e sem agenda/CRM/e-mail reais
      ├─► Avaliação .......... verificações automáticas + LLM juiz com rubrica (5 critérios, nota 1–5)
      └─► Saídas ............. treinador/saidas/<rodada>/ e casos de regressão em tests/regressao/casos/
```

A CLI (`main.py`) usa o mesmo núcleo e serve para demonstrar os cenários do enunciado pelo terminal.

**Princípios de arquitetura**

- **Componentização:** front, API e núcleo são separados, e cada responsabilidade do núcleo fica num módulo em `src/` (agente, coleta, qualificação, catálogo, memória, agenda, resumo, CRM, dashboard).
- **O código controla a conversa, o LLM só interpreta:** o estado da conversa e a próxima pergunta são decididos pelo Python. Isso evita que o modelo invente imóveis, pule etapas ou perca dados já informados.
- **LLM opcional com fallback:** sem `OPENAI_API_KEY` ou com falha na API, tudo continua funcionando no modo por regras.
- **Treinador desacoplado:** roda em outro processo, conversa com o agente pela mesma função (ou pelo `POST /chat`, no modo `api`) e nunca grava em agenda, CRM ou e-mail reais.
- **Adapter para o CRM:** o agente depende de uma interface (`CRMAdapter`), não de um fornecedor. Trocar o CRM simulado por um real é só trocar a URL ou a implementação.
- **Resiliência:** uma falha no CRM não interrompe o atendimento. Os eventos ficam numa fila local e podem ser reenviados.
- **Adapter para a agenda:** Google e Outlook implementam a mesma interface (`criar`, `adicionar_convidados`, `cancelar`, `ocupados`). Se a API da agenda falhar, a visita continua registrada e os links/.ics continuam valendo.

Mais detalhes em [`docs/ARQUITETURA.txt`](docs/ARQUITETURA.txt) e [`docs/QUALIFICACAO_E_RESUMO.md`](docs/QUALIFICACAO_E_RESUMO.md).

## Como a IA é usada

| Onde | Técnica | Por quê |
|---|---|---|
| Interpretação da mensagem | Regras tolerantes a erro (comparação aproximada, números por extenso, correções) + LLM (`gpt-4o-mini` por padrão) com `temperature=0` e saída JSON, usado só para extrair dados | O modelo entende frases que as regras não cobrem, sem controlar a conversa |
| Merge regras + LLM | As regras têm prioridade no que já entenderam. O LLM completa campos vazios e só altera um dado já informado se a mensagem citar aquele dado; a intenção nunca é trocada pelo LLM. Valores inválidos (nome no lugar do foco, cidade inteira como região) são descartados | Evita que um palpite do modelo apague o que o lead disse |
| Resposta ao lead | Montada pelo Python a partir do estado: confirma o que mudou, responde dúvidas comuns e faz a próxima pergunta | Respostas consistentes e sem dados inventados |
| Qualificação | Score **ponderado e explicável** (inspirado em BANT) | O corretor vê *por que* o lead é quente |
| Resumo para o corretor | LLM gera sinopse, objeções e próximo passo (schema Pydantic); fallback por regras | Corretor entende o lead em 30 segundos |
| Treinador: lead simulado | LLM interpreta uma persona (descrição + objetivo + jeito de falar) e conversa com o agente até o objetivo ou o limite de turnos | Testa o agente com conversas variadas, que ninguém escreveria à mão |
| Treinador: juiz | LLM com rubrica (compreensão, naturalidade, progresso, veracidade, dúvidas) aponta falhas por turno e sugere a resposta certa | Mede a qualidade da conversa, não só se o código roda |

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
├── api/
│   ├── app.py                  # API REST (FastAPI) usada pelo front
│   └── treinador.py            # Rotas /treinador/* (rodadas, contextos, casos)
├── frontend/src/pages/         # React + Vite + TypeScript
│   ├── LeadPage.tsx            # /atendimento: chat como o lead vê no site
│   ├── ChatPage.tsx            # /: inbox do corretor (conversa + perfil + score)
│   ├── DashboardPage.tsx       # /dashboard: leads por prioridade
│   └── TreinadorPage.tsx       # /treinador: rodadas, contextos e casos de regressão
├── docs/
│   ├── ARQUITETURA.txt
│   ├── QUALIFICACAO_E_RESUMO.md
│   └── ROTEIRO_TESTES_TELA.md
├── treinador/                  # Treinador do agente (python -m treinador)
│   ├── personas.py             # 10 leads simulados com objetivo e roteiro
│   ├── contextos.py            # Leads descritos em texto livre (salvos em contextos.json, fora do Git)
│   ├── simulador.py            # Conversa lead simulado ⇄ agente
│   ├── verificacoes.py         # Falhas detectáveis sem LLM (repetição, loop, jargão, texto quebrado…)
│   ├── avaliador.py            # LLM juiz com rubrica
│   ├── regressao.py            # Gera casos em tests/regressao/casos/
│   └── execucao.py, relatorio.py, canal.py, llm.py
├── src/
│   ├── agente/sdr.py           # Orquestração da conversa
│   ├── coleta/perfil.py        # Campos por intenção e perguntas do funil
│   ├── qualificacao/
│   │   ├── interpretador.py    # Interpretação da mensagem (regras + LLM opcional)
│   │   ├── fluxo_conversa.py   # Próximo dado faltante e pergunta correspondente
│   │   ├── lead.py             # Score, prioridade, encaminhamento
│   │   ├── extracao_llm.py     # Extração estruturada com LLM (legado, coberta por testes)
│   │   └── contato.py          # Nome, correção de e-mail e respostas sim/não
│   ├── imoveis/
│   │   ├── catalogo.py         # Busca (escolhe a fonte pelo IMOVEIS_SOURCE)
│   │   └── catalogo_br.py      # Catálogo sintético Brasil (BRL)
│   ├── memoria/conversa.py     # Memória do lead (usa src/db)
│   ├── db/                     # SQLAlchemy: modelos, sessão, repositórios
│   ├── agenda/
│   │   ├── scheduler.py        # Horários livres, leitura da escolha, agendar/remarcar/cancelar
│   │   ├── calendario.py       # Links Google/Outlook, .ics, Google Calendar API, Microsoft Graph
│   │   ├── email_convite.py    # Convite por e-mail (Resend/SendGrid) com .ics de RSVP
│   │   └── oauth.py            # Autorização única (--agenda-auth google|outlook)
│   ├── canais/telegram.py      # Bot do Telegram (demonstração educativa; mesmo agente do chat web)
│   ├── resumo/corretor.py      # Resumo para o corretor (.md e .json)
│   ├── crm/
│   │   ├── cliente.py          # Webhook, eventos, fila de pendentes
│   │   └── servidor_mock.py    # CRM simulado (FastAPI + painel)
│   └── dashboard/metricas.py   # Métricas agregadas
├── tests/                      # pytest (sem internet, sem LLM e sem banco)
│   └── regressao/              # Casos gerados pelo treinador
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

O front acessa a API pelo proxy `/api` do Vite. O seletor **Lead | Corretor** no topo alterna as visões:

| Tela | Endereço | Para quê |
|---|---|---|
| Visão do lead | http://localhost:5173/atendimento | Chat como no site da imobiliária: só conversa, imóveis e visita, sem score nem dados internos |
| Inbox do corretor | http://localhost:5173/ | Conversa com qualquer lead, com perfil, score e resumo ao lado |
| Dashboard | http://localhost:5173/dashboard | Leads por prioridade, contatos capturados e convites |
| Treinador | http://localhost:5173/treinador | Rodadas de avaliação do agente (ver [Treinador do agente](#treinador-do-agente)) |

**Principais rotas da API:** `POST /chat`, `GET /leads`, `GET /leads/{id}`, `GET /leads/{id}/resumo`, `POST /leads/{id}/follow-up`, `POST /leads/{id}/agendar`, `GET /leads/{id}/agendamentos/{n}/convite.ics`, `GET /dashboard`, `GET /health`. A documentação interativa fica em http://127.0.0.1:8000/docs.

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

### Captura de nome e e-mail e agendamento em um toque

O agente coleta o contato ao longo da conversa, sem formulário:

1. **Nome:** na primeira resposta ele pergunta "como posso te chamar?" e entende tanto frases ("meu nome é Ana", "me chamo João", "aqui é a Bia") quanto a resposta curta ("Ana"). Uma resposta curta que na verdade responde outra pergunta ("comprar", "Pinheiros") não vira nome.
2. **E-mail:** ao oferecer horários, pede o e-mail explicando o uso ("uso só para o convite e o contato do corretor"). Se o domínio parecer digitado errado (`gmial.com`, `hotmal.com`), confirma antes: "seu e-mail é ana@gmail.com?". Se o lead disser "não" e redigitar o mesmo endereço, vale o que ele digitou.
3. **Um toque:** com o e-mail em mãos, o agente propõe o primeiro horário livre ("Posso reservar a visita para quarta, 30/09/2026 às 10:00?"). Basta responder "sim": a visita é registrada e o convite sai na hora.

O convite chega por um destes caminhos, sem duplicar:

| Situação | Como o lead recebe |
|---|---|
| Agenda do corretor conectada (Google/Outlook) | Convite enviado pela própria agenda |
| Sem agenda, com Resend ou SendGrid configurado | E-mail com `.ics` (`METHOD:REQUEST`): Gmail e Outlook mostram os botões Sim/Não/Talvez e colocam a visita na agenda. Remarcar ou cancelar manda `METHOD:CANCEL` com o mesmo UID |
| Nada configurado | Botões "adicionar à agenda" e `.ics` no chat |

**Configurar o envio:** crie uma chave no [Resend](https://resend.com/) ou no [SendGrid](https://sendgrid.com/) e preencha `EMAIL_FROM` e `RESEND_API_KEY` (ou `SENDGRID_API_KEY`) no `.env`. No Resend, sem domínio verificado, só é possível enviar para o e-mail dono da conta, o que basta para a demo. Confira com `python main.py --checar` (linha `convite por e-mail:`).

O dashboard mostra quantos leads deixaram nome e e-mail e quantos convites foram enviados.

### Canal Telegram (demonstração educativa)

Para fins educativos, o agente também atende por um bot do Telegram. O objetivo é mostrar que ele não depende do canal: cada mensagem do bot passa pela mesma função do chat web (`processar_mensagem`), e o lead aparece na inbox e no dashboard do corretor como `TG-<id do chat>`.

1. No Telegram, abra o [@BotFather](https://t.me/BotFather), envie `/newbot` e copie o token.
2. Preencha `TELEGRAM_BOT_TOKEN` no `.env`.
3. Com o PostgreSQL no ar, rode `python main.py --telegram` e converse com o bot.

O bot busca as mensagens por *long polling*, então roda na máquina local, sem URL pública. Os horários de visita viram botões, e a visita marcada chega com os atalhos do Google Agenda e do Outlook e o arquivo `.ics`. No `/start`, o bot avisa que é uma demonstração e que os imóveis são fictícios.

**E o WhatsApp?** É possível integrar pelo mesmo caminho: muda só o formato da mensagem recebida e a chamada de envio, e o agente continua igual. As opções são a [WhatsApp Cloud API](https://developers.facebook.com/docs/whatsapp/cloud-api) da Meta (oficial, com número de teste gratuito) ou o Twilio. O WhatsApp tem regras que o Telegram não tem:

- o agente só manda texto livre até 24 h depois da última mensagem do lead, e o follow-up fora dessa janela exige um modelo de mensagem aprovado pela Meta;
- o número de produção exige verificação da empresa na Meta;
- o webhook precisa de URL pública com HTTPS e validação da assinatura de cada requisição.

Bibliotecas não oficiais (que simulam o WhatsApp Web) violam os termos de uso e podem levar ao banimento do número.

### Demonstração pela CLI (3 cenários do desafio)

Com o PostgreSQL e o CRM simulado no ar:

```bash
python main.py --demo
```

A demo roda três cenários: **compra** ("apartamento na zona sul"), **investimento** ("investir para renda") e **follow-up** (lead que parou de responder). Ela também gera o resumo do `LEAD-001` em `dados/saidas/`. Os leads aparecem no painel do CRM, ordenados por score.

### Treinador do agente

O treinador coloca leads simulados para conversar com o agente e avalia cada conversa. Ele serve para achar falhas que testes escritos à mão não pegam (por exemplo, um lead idoso que se confunde, ou alguém que muda de ideia três vezes).

**Pela tela** (`/treinador`, com a API no ar):

1. Escolha as personas: são 10 prontas (investidor direto, inquilina que digita errado, quem muda de ideia, quem só responde "sim", curioso com dúvidas, fora de escopo, monossilábico…).
2. Opcionalmente, descreva um lead em **Contextos para teste**, por exemplo: "simule uma conversa de um senhor de idade que fala pausadamente e possui confusões e dúvidas". O contexto fica salvo e pode ser reusado.
3. Defina quantas conversas por persona e o máximo de turnos, e se o lead e o juiz usam IA. Sem IA, as personas seguem roteiros fixos e só as verificações automáticas rodam: é rápido e não tem custo, mas os contextos exigem IA.
4. Acompanhe o progresso ao vivo. No fim, a tela mostra as aprovadas, a média do juiz por critério e cada conversa em balões, com a falha marcada no turno e a sugestão do juiz.

**Pelo terminal:**

```bash
python -m treinador --sem-llm                                   # roteiros fixos, sem custo
python -m treinador --personas muda_de_ideia,curioso_duvidas    # com IA (precisa de OPENAI_API_KEY)
python -m treinador --contexto "senhor de idade que fala pausadamente e tem dúvidas"
python -m treinador --modo api --url http://localhost:8000      # conversa pelo POST /chat e grava no banco
python -m treinador --limpar                                    # remove do banco os leads TREINO-*
```

**Como uma conversa é avaliada:** uma conversa é aprovada quando não tem falha automática e a média do juiz é pelo menos 3,5.

- **Falhas automáticas** (sem LLM): resposta repetida, pergunta em loop, cidades misturadas na mesma sugestão, texto quebrado, jargão de sistema e resposta vazia.
- **Juiz:** dá nota de 1 a 5 em compreensão, naturalidade, progresso, veracidade e dúvidas.

**Regressão:** conversas com falha automática viram um caso em `tests/regressao/casos/`. O `pytest` repete as falas do lead e falha até o agente responder sem aquela falha. Cada rodada gera `treinador/saidas/<rodada>/` com status, conversas e um relatório em Markdown (fora do Git).

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
| `python main.py --telegram` | Atende leads pelo bot do Telegram (demonstração educativa) |
| `python -m treinador [--personas a,b] [--contexto "…"] [--rodadas N] [--sem-llm]` | Roda o treinador do agente (ver acima) |

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
- **Captura e convite:** extração de nome, correção de domínio do e-mail, "sim" de um toque, `.ics` REQUEST/CANCEL, envio pelo Resend e pelo SendGrid com HTTP simulado e ausência de convite duplicado quando a agenda do corretor já convidou.
- **Fluxo de conversa:** erro de digitação, dados fora de ordem, mudança de ideia, correções, preço por extenso ("2 mil e quinhentos"), kitnet/studio, dúvidas no meio, pedido de visita antes da hora, adiar a agenda e insistência sem dado novo (nunca repetir a mesma resposta).
- **Canal Telegram:** bot falso, sem rede: mensagem vira lead `TG-*`, horários em botões, clique que agenda, `.ics` enviado uma vez, grupos ignorados, texto longo dividido e token fora das mensagens de erro.
- **Treinador:** personas e contextos, execução sem LLM, API da tela (`/treinador/*`) e os casos de regressão gerados pelas rodadas (`tests/regressao/`).
- **Validação ponta a ponta:** 12 conversas realistas pelo fluxo completo. Os casos marcados como `xfail` são **defeitos conhecidos** da extração por regex (ver [Limitações conhecidas](#limitações-conhecidas)). Quando um deles for corrigido, o teste acusa XPASS, avisando para remover a marcação.

## Configuração (.env)

| Variável | Obrigatória | Padrão | Descrição |
|---|---|---|---|
| `DATABASE_URL` | Não | `postgresql+psycopg://sdr:sdr@localhost:5432/sdr` | Conexão com o PostgreSQL (igual ao `docker-compose.yml`) |
| `OPENAI_API_KEY` | Não | — | Liga o LLM (interpretação da mensagem, sinopse do resumo e, no treinador, lead simulado e juiz). Sem ela, o agente funciona por regras e o treinador só roda com `--sem-llm`. |
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
| `EMAIL_PROVIDER` | Não | automático | `resend` ou `sendgrid`; vazio usa o que tiver chave |
| `EMAIL_FROM` | Não | — | Remetente do convite, ex.: `Imobiliária <visitas@seudominio.com.br>` |
| `RESEND_API_KEY` / `SENDGRID_API_KEY` | Não | — | Chave do serviço de e-mail transacional. Sem chave, o envio fica desligado |
| `TELEGRAM_BOT_TOKEN` | Não | — | Token do bot criado no @BotFather (só para `python main.py --telegram`) |

## Segurança e privacidade

- As credenciais ficam só no `.env`, que **não é versionado**.
- O catálogo usa dados **sintéticos** (catálogo BR gerado ou API fake pública).
- O webhook do CRM aceita autenticação por token Bearer, e o CRM simulado responde 401 se o token não bater.
- As conversas ficam no PostgreSQL local, e as saídas geradas em `dados/`, fora do Git.
- Os tokens da agenda ficam em `dados/agenda_tokens.json` (permissão 600, fora do Git). Os escopos pedidos são só os de eventos e disponibilidade da agenda.
- O evento enviado ao lead não leva score nem prioridade: só os dados que ele mesmo informou.
- O e-mail só é pedido com a finalidade explicada ao lead (convite e contato do corretor), e o convite traz um aviso de por que ele foi enviado (LGPD).
- O agente **não fecha negócio sozinho**: ele qualifica e resume, e a decisão é do corretor.
- O treinador usa leads fictícios e, no modo padrão, memória em RAM: não cria eventos na agenda, não envia e-mail nem dispara o CRM. Os contextos de teste e as saídas das rodadas ficam fora do Git.

## Limitações conhecidas

- **A interpretação por regras** (usada sempre, com o LLM só complementando) ainda erra em alguns formatos:
  - "800k" não é reconhecido;
  - quartos por extenso ("dois quartos", "um ou dois quartos") não são lidos;
  - bairros fora da lista fixa (ex.: Mooca) são ignorados, e referências como "perto do Ibirapuera" não viram um bairro atendido;
  - "agora" no meio da frase ("agora estou só olhando", "espero que tenha entendido agora") marca urgência alta.

  Os casos com teste estão marcados como `xfail` em `tests/test_validacao_qualificacao.py`: quando um for corrigido, o teste acusa XPASS. Com o LLM ligado, parte deles é coberta pela interpretação do modelo.
- **Lead que não sabe o bairro:** quando o lead pede sugestão de região, o agente ainda não lista as regiões atendidas e responde que deixa a pergunta para o corretor.
- **Treinador:** o juiz é um LLM (`gpt-4o-mini`) e às vezes erra; o prompt foi calibrado, mas as notas são indicativas. Só as falhas automáticas viram teste de regressão, e roda uma rodada por vez.
- **Com `IMOVEIS_SOURCE=fake`, uma falha na API externa interrompe a conversa.** O catálogo BR (padrão) é local e não tem esse risco.
- **O CRM é simulado.** A integração (HTTP, token, eventos) é real, mas o destino é um servidor local.
- **Agenda:** sem credenciais, os horários oferecidos são janelas padrão (10h, 14h e 16h, sem domingo) e não há checagem de conflito. A agenda é de um único corretor, sem rodízio entre corretores.
- **Canais:** o Telegram é uma demonstração educativa, rodando por *long polling* num único processo. O WhatsApp não está integrado. O webhook de canal (`POST /webhooks/canal`) é um gancho genérico, sem o formato de nenhum provedor.

## Roadmap

- RAG sobre FAQs da imobiliária
- Canal WhatsApp (Cloud API da Meta ou Twilio) ou Chatwoot, no mesmo molde do canal Telegram
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

---

Projeto acadêmico — FIAP PosTech, IA para Devs, Fase 5 (Hackathon).
