const API_BASE = import.meta.env.VITE_API_URL || "/api";

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

export type Lead = {
  lead_id: string;
  perfil: Record<string, unknown>;
  mensagens: Mensagem[];
  agendamentos: unknown[];
  imoveis_sugeridos: string[];
  score?: number;
  prioridade?: string;
  atualizado_em?: string;
};

export type Dashboard = {
  total_conversas: number;
  por_prioridade: Record<string, number>;
  agendamentos: number;
  leads: Array<{
    lead_id: string;
    score: number;
    prioridade: string;
    mensagens: number;
    intencao?: string;
    atualizado_em?: string;
  }>;
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
  resumo: (id: string) => request<Record<string, unknown>>(`/leads/${encodeURIComponent(id)}/resumo`),
  followUp: (id: string) =>
    request<{ resposta: string; qualificacao: Qualificacao }>(
      `/leads/${encodeURIComponent(id)}/follow-up`,
      { method: "POST" },
    ),
  health: () => request<Record<string, unknown>>("/health"),
};
