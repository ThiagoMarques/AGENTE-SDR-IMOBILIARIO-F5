const API_BASE = import.meta.env.VITE_API_URL || "/api";

export const apiUrl = (path: string) => `${API_BASE}${path}`;

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${API_BASE}${path}`, {
    headers: { "Content-Type": "application/json", ...(init?.headers || {}) },
    ...init,
  });
  if (!res.ok) {
    const text = await res.text();
    throw new Error(text || res.statusText);
  }
  return res.json() as Promise<T>;
}

export type Qualificacao = {
  score: number;
  prioridade: string;
  campos_faltantes: string[];
  pronto_para_agendar: boolean;
};

export type Mensagem = {
  papel: string;
  texto: string;
  em?: string;
};

/** Visita/reunião com atalhos de agenda — src/agenda/scheduler.py:publico */
export type Agendamento = {
  indice: number;
  tipo: "visita" | "reuniao" | string;
  horario: string;
  inicio?: string;
  quando: string;
  status: "agendado" | "remarcado" | "cancelado" | string;
  imovel_id?: string | null;
  imovel_titulo?: string | null;
  local?: string;
  convidados: string[];
  convite_enviado?: boolean;
  calendarios: Array<{ provedor: "google" | "outlook" | string; status: string; link?: string | null }>;
  links: { google: string; outlook: string; outlook_365: string; ics: string };
};

export type Lead = {
  lead_id: string;
  perfil: Record<string, unknown>;
  mensagens: Mensagem[];
  agendamentos: Agendamento[];
  imoveis_sugeridos: string[];
  score?: number;
  prioridade?: string;
  atualizado_em?: string;
};

export type Dashboard = {
  total_conversas: number;
  por_prioridade: Record<string, number>;
  agendamentos: number;
  captura?: { com_nome: number; com_email: number; convites_enviados: number };
  leads: Array<{
    lead_id: string;
    nome?: string | null;
    score: number;
    prioridade: string;
    mensagens: number;
    intencao?: string;
    atualizado_em?: string;
  }>;
};

export type CriterioScore = {
  criterio: string;
  pontos: number;
  maximo: number;
  motivo: string;
};

/** Pacote do corretor (GET /leads/{id}/resumo) — src/resumo/corretor.py */
export type ResumoCorretor = {
  lead_id: string;
  gerado_em?: string;
  gerado_por?: "regras" | "llm" | string;
  sinopse?: string;
  perfil: Record<string, unknown>;
  qualificacao: Qualificacao & {
    encaminhamento?: string;
    criterios?: CriterioScore[];
    justificativa?: string;
  };
  encaminhamento?: string;
  objecoes?: string[];
  pontos_atencao?: string[];
  imoveis_sugeridos?: string[];
  agendamentos?: Agendamento[];
  acao_sugerida?: string;
};

export type ChatResponse = {
  lead_id: string;
  resposta: string;
  perfil: Record<string, unknown>;
  qualificacao: Qualificacao;
  imoveis: Array<Record<string, unknown>>;
  exibir_imoveis?: boolean;
  match_busca?: "exato" | "aproximado" | "vazio" | string;
  motivo_busca?: string;
  agendamento?: Agendamento | null;
  fora_de_escopo?: boolean;
  usou_llm: boolean;
};

export const api = {
  chat: (lead_id: string, mensagem: string) =>
    request<ChatResponse>("/chat", {
      method: "POST",
      body: JSON.stringify({ lead_id, mensagem }),
    }),
  dashboard: () => request<Dashboard>("/dashboard"),
  lead: (id: string) => request<Lead>(`/leads/${encodeURIComponent(id)}`),
  resumo: (id: string) => request<ResumoCorretor>(`/leads/${encodeURIComponent(id)}/resumo`),
  followUp: (id: string) =>
    request<{ resposta: string; qualificacao: Qualificacao }>(
      `/leads/${encodeURIComponent(id)}/follow-up`,
      { method: "POST" },
    ),
  health: () => request<Record<string, unknown>>("/health"),
};
