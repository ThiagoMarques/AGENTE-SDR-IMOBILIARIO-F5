# Agente SDR Imobiliário com IA — Fase 5

Prova de conceito (POC) de um **SDR imobiliário com IA generativa**, desenvolvida no Hackathon da Fase 5 da pós-graduação **IA para Devs (FIAP PosTech)**.

O agente atende leads automaticamente e identifica se o cliente quer comprar, alugar ou investir. Ele qualifica o lead com um score explicável, sugere imóveis de uma base simulada, faz follow-up, propõe horários de visita, gera um resumo para o corretor e sincroniza o lead com um CRM.

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
| Atender leads automaticamente | ✅ | `src/agente/sdr.py` |
| Conversa humanizada | ✅ LLM (se configurado) ou respostas por regras | `src/agente/sdr.py` |
| Identificar intenção (compra, aluguel, investimento) | ✅ | `src/agente/sdr.py`, `src/qualificacao/extracao_llm.py` |
| Coletar informações relevantes | ✅ Regras + extração estruturada com LLM | `src/agente/sdr.py`, `src/qualificacao/extracao_llm.py` |
| Qualificar clientes | ✅ Score ponderado 0–100 com justificativa | `src/qualificacao/lead.py` |
| Follow-up automático | ✅ Retoma a conversa com contexto | `src/agente/sdr.py` (`follow_up`) |
| Agendar reuniões ou visitas | ✅ Sugestão e registro de horários | `src/agenda/scheduler.py` |
| Integrar com base simulada de imóveis | ✅ [Fake API for Devs — Real Estate](https://fakeapifordevs.vercel.app/docs/realestate) | `src/imoveis/catalogo.py` |
| Gerar resumos para corretores | ✅ Markdown + JSON, com sinopse por LLM | `src/resumo/corretor.py` |
| Dashboard mínimo | ✅ Leads por prioridade e agendamentos | `src/dashboard/metricas.py` |

**Diferenciais implementados**

| Diferencial | O que foi feito |
|---|---|
| Memória conversacional | Histórico e perfil persistidos por lead (`dados/conversas/*.json`) |
| Integração com CRM | Webhook HTTP por evento + CRM simulado em FastAPI com painel web (`src/crm/`) |
| Segurança | Credenciais só no `.env`, token Bearer no webhook do CRM, dados sintéticos |

## Arquitetura

```
Lead ──► processar_mensagem (src/agente/sdr.py)
           │
           ├─► Memória ............ carrega histórico e perfil (src/memoria)
           ├─► Extração ........... regras (regex) + LLM com schema Pydantic
           ├─► Qualificação ....... score ponderado, prioridade, encaminhamento
           ├─► Catálogo ........... busca na Fake Real Estate API (src/imoveis)
           ├─► Resposta ........... LLM (OpenAI) ou fluxo determinístico
           ├─► Agenda ............. sugere horários quando o lead está pronto
           ├─► Resumo ............. pacote para o corretor (src/resumo)
           └─► CRM ................ webhook por evento ──► CRM simulado (FastAPI)
                                                          └─► painel http://127.0.0.1:8001
```

**Princípios de arquitetura**

- **Componentização:** cada responsabilidade fica num módulo em `src/` (agente, qualificação, catálogo, memória, agenda, resumo, CRM, dashboard).
- **LLM opcional com fallback:** sem `OPENAI_API_KEY` ou com falha na API, tudo continua funcionando no modo por regras.
- **Adapter para o CRM:** o agente depende de uma interface (`CRMAdapter`), não de um fornecedor. Trocar o CRM simulado por um real é só trocar a URL ou a implementação.
- **Resiliência:** uma falha no CRM não interrompe o atendimento. Os eventos ficam numa fila local e podem ser reenviados.

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

Prioridade: **quente** ≥ 70 · **morno** ≥ 40 · **frio** < 40. Investidores são encaminhados para o **especialista em investimentos**.

## Estrutura do projeto

```
.
├── main.py                     # CLI: demo, chat, resumo, dashboard, CRM
├── config.py                   # Configuração central (lê o .env)
├── requirements.txt
├── .env.example                # Modelo de variáveis de ambiente
├── docs/
│   ├── ARQUITETURA.txt
│   └── QUALIFICACAO_E_RESUMO.md
├── src/
│   ├── agente/sdr.py           # Orquestração da conversa
│   ├── qualificacao/
│   │   ├── lead.py             # Score, prioridade, próxima pergunta
│   │   └── extracao_llm.py     # Extração estruturada com LLM
│   ├── imoveis/catalogo.py     # Cliente da Fake Real Estate API
│   ├── memoria/conversa.py     # Persistência de histórico e perfil
│   ├── agenda/scheduler.py     # Horários de visita/reunião
│   ├── resumo/corretor.py      # Resumo para o corretor (.md e .json)
│   ├── crm/
│   │   ├── cliente.py          # Webhook, eventos, fila de pendentes
│   │   └── servidor_mock.py    # CRM simulado (FastAPI + painel)
│   └── dashboard/metricas.py   # Métricas agregadas
├── tests/                      # pytest (sem internet e sem LLM)
└── dados/                      # Gerado em runtime (fora do Git)
```

## Instalação

**Pré-requisitos:** Python 3.10+ e acesso à internet (para a API de imóveis).

```bash
git clone https://github.com/ThiagoMarques/AGENTE-SDR-IMOBILIARIO-F5.git
cd AGENTE-SDR-IMOBILIARIO-F5

python3 -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate

pip install -r requirements.txt
cp .env.example .env             # preencha OPENAI_API_KEY (opcional)

python main.py --checar          # valida ambiente, API de imóveis e CRM
```

> No macOS, se aparecer `CERTIFICATE_VERIFY_FAILED`, veja [Solução de problemas](#solução-de-problemas).

## Como usar

### Demonstração completa (3 cenários do desafio)

Use dois terminais:

```bash
# Terminal 1 — CRM simulado (abra http://127.0.0.1:8001 no navegador)
python main.py --crm-servidor

# Terminal 2 — agente
python main.py --demo
```

A demo roda três cenários: **compra** ("apartamento na zona sul"), **investimento** ("investir para renda") e **follow-up** (lead que parou de responder). Ela também gera o resumo do `LEAD-001` em `dados/saidas/`. Os leads aparecem no painel do CRM, ordenados por score.

### Comandos

| Comando | O que faz |
|---|---|
| `python main.py --checar` | Valida pastas, API de imóveis, LLM e CRM |
| `python main.py --demo` | Roda os 3 cenários do desafio |
| `python main.py --chat "Quero alugar em Pinheiros" --lead LEAD-10` | Envia uma mensagem como o lead informado |
| `python main.py --resumo LEAD-10` | Gera o resumo do corretor (`.md` e `.json`) e envia ao CRM |
| `python main.py --dashboard` | Mostra as métricas: leads por prioridade e agendamentos |
| `python main.py --imoveis --intencao compra --quartos 2 --preco-max 500000` | Consulta o catálogo |
| `python main.py --crm-servidor [--crm-porta 8001]` | Sobe o CRM simulado |
| `python main.py --crm-reenviar` | Reenvia eventos que falharam ao CRM |

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

Os testes rodam **sem internet e sem LLM**: o catálogo é simulado e a chave da OpenAI é desligada. Eles cobrem:

- **Qualificação:** score, pesos, encaminhamento, merge entre regras e LLM.
- **Resumo:** conteúdo, objeções, pontos de atenção, exportação.
- **CRM:** envio HTTP real contra o CRM simulado, upsert, fila de pendentes, token.
- **Validação ponta a ponta:** 12 conversas realistas pelo fluxo completo. Os casos marcados como `xfail` são **defeitos conhecidos** da extração por regex (ver [Limitações conhecidas](#limitações-conhecidas)). Quando um deles for corrigido, o teste acusa XPASS, avisando para remover a marcação.

## Configuração (.env)

| Variável | Obrigatória | Padrão | Descrição |
|---|---|---|---|
| `OPENAI_API_KEY` | Não | — | Liga o LLM (resposta, extração e sinopse). Sem ela, o modo é por regras. |
| `LLM_MODEL` | Não | `gpt-4o-mini` | Modelo da OpenAI |
| `IMOVEIS_API_BASE` | Não | Fake Real Estate API | Base da API de imóveis |
| `IMOVEIS_API_TIMEOUT` | Não | `20` | Timeout da API de imóveis (segundos) |
| `CRM_WEBHOOK_URL` | Não | — | URL do webhook do CRM. Vazio desabilita. |
| `CRM_WEBHOOK_TOKEN` | Não | — | Token Bearer exigido pelo CRM |
| `CRM_TIMEOUT` | Não | `3` | Timeout do envio ao CRM (segundos) |

## Segurança e privacidade

- As credenciais ficam só no `.env`, que **não é versionado**.
- O catálogo usa dados **sintéticos** (API fake pública).
- O webhook do CRM aceita autenticação por token Bearer, e o CRM simulado responde 401 se o token não bater.
- Os dados de conversa ficam em `dados/`, fora do Git.
- O agente **não fecha negócio sozinho**: ele qualifica e resume, e a decisão é do corretor.

## Limitações conhecidas

- **Extração por regex** (usada quando não há LLM ou ele falha) erra em alguns formatos:
  - "1,5 milhão" vira orçamento 1;
  - "800k" não é reconhecido;
  - "dois quartos" (por extenso) não é lido;
  - bairros fora da lista fixa são ignorados;
  - prazos como "esse mês" e "em 3 meses" não viram urgência;
  - "agora estou só olhando" marca urgência alta;
  - "minha renda é…" junto com "alugar" vira investimento.

  Todos estão documentados em `tests/test_validacao_qualificacao.py`. Com o LLM ligado, a extração dele tem precedência e corrige boa parte desses casos.
- **Falha na API de imóveis interrompe a conversa.** Hoje o erro sobe até a CLI.
- **O CRM é simulado.** A integração (HTTP, token, eventos) é real, mas o destino é um servidor local.
- **Os preços do catálogo estão em USD** (dados da API fake), enquanto a conversa é em português.
- **O agendamento sugere horários fixos** e não consulta uma agenda real.

## Roadmap

- RAG sobre FAQs da imobiliária
- Canal WhatsApp
- Multiagentes (qualificador, buscador, agendador)
- Voice AI
- CRM real (ex.: HubSpot, via novo adapter)
- Observabilidade e deploy em cloud

## Solução de problemas

### macOS: `CERTIFICATE_VERIFY_FAILED` ao consultar a API de imóveis

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
| Thiago Marques | Estrutura inicial do agente e dos módulos |
| Letícia | Qualificação de leads, resumo para corretores, integração com CRM, testes |

<!-- Completar com os demais integrantes e suas contribuições. -->

---

Projeto acadêmico — FIAP PosTech, IA para Devs, Fase 5 (Hackathon).
