import {
  Alert,
  Avatar,
  Button,
  Card,
  EmptyState,
  Spinner,
} from "@heroui/react";
import { useEffect, useState } from "react";
import { api, Dashboard, Lead, ResumoCorretor as ResumoTipo } from "../api";
import { MetricCard } from "../components/MetricCard";
import { PriorityChip } from "../components/PriorityChip";
import { ResumoCorretor } from "../components/ResumoCorretor";

export default function DashboardPage() {
  const [dash, setDash] = useState<Dashboard | null>(null);
  const [selecionado, setSelecionado] = useState<Lead | null>(null);
  const [resumo, setResumo] = useState<ResumoTipo | null>(null);
  const [erro, setErro] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  async function carregar() {
    setLoading(true);
    setErro(null);
    try {
      setDash(await api.dashboard());
    } catch (err) {
      setErro(err instanceof Error ? err.message : "Falha ao carregar dashboard");
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    void carregar();
  }, []);

  async function abrirLead(id: string) {
    setErro(null);
    try {
      const [lead, r] = await Promise.all([api.lead(id), api.resumo(id)]);
      setSelecionado(lead);
      setResumo(r);
    } catch (err) {
      setErro(err instanceof Error ? err.message : "Falha ao abrir lead");
    }
  }

  const pri = dash?.por_prioridade || { quente: 0, morno: 0, frio: 0 };
  const leads = dash?.leads || [];
  const total = dash?.total_conversas || 0;
  const stages = [
    { label: "Novos", value: total, color: "bg-lime" },
    { label: "Frios", value: pri.frio ?? 0, color: "bg-slate-400" },
    { label: "Mornos", value: pri.morno ?? 0, color: "bg-sky-400" },
    { label: "Quentes", value: pri.quente ?? 0, color: "bg-orange-400" },
    { label: "Agendados", value: dash?.agendamentos ?? 0, color: "bg-navy" },
  ];
  const captura = dash?.captura;
  const pct = (n: number) => (total ? `${Math.round((n / total) * 100)}%` : "—");
  const capturaItens = captura
    ? [
        { label: "Com nome", value: captura.com_nome },
        { label: "Com e-mail", value: captura.com_email },
        { label: "Convites enviados", value: captura.convites_enviados },
      ]
    : [];

  return (
    <div className="flex h-full min-h-0 flex-col gap-3 overflow-auto">
      <div className="flex flex-col gap-3 rounded-[1.75rem] border border-white/60 bg-white/85 p-4 shadow-sm backdrop-blur sm:flex-row sm:items-center sm:justify-between sm:p-5">
        <div>
          <h1 className="text-xl font-semibold tracking-tight sm:text-2xl">Gestão de leads</h1>
          <p className="text-sm text-slate-500">Funil, prioridade e encaminhamento ao corretor</p>
        </div>
        <Button
          variant="primary"
          className="rounded-full bg-lime"
          isDisabled={loading}
          onPress={() => void carregar()}
        >
          {loading ? (
            <span className="inline-flex items-center gap-2">
              <Spinner size="sm" color="current" /> Atualizando
            </span>
          ) : (
            "Atualizar"
          )}
        </Button>
      </div>

      {erro && (
        <Alert status="danger">
          <Alert.Content>
            <Alert.Title>Erro</Alert.Title>
            <Alert.Description>{erro}</Alert.Description>
          </Alert.Content>
        </Alert>
      )}

      <div className="grid grid-cols-2 gap-3 lg:grid-cols-5">
        <MetricCard label="Total" value={dash?.total_conversas ?? "—"} />
        <MetricCard label="Quentes" value={pri.quente ?? 0} tone="quente" />
        <MetricCard label="Mornos" value={pri.morno ?? 0} tone="morno" />
        <MetricCard label="Frios" value={pri.frio ?? 0} tone="frio" />
        <MetricCard label="Agendamentos" value={dash?.agendamentos ?? 0} />
      </div>

      <Card className="rounded-[1.75rem] border border-white/60 bg-white/90 shadow-sm">
        <Card.Header>
          <Card.Title className="text-lg">Funil</Card.Title>
          <Card.Description>Visão rápida a partir das prioridades do agente</Card.Description>
        </Card.Header>
        <Card.Content>
          <div className="flex flex-wrap items-center gap-2 sm:gap-3">
            {stages.map((s, i) => (
              <div key={s.label} className="flex items-center gap-2 sm:gap-3">
                <div className="flex min-w-[4.5rem] flex-col items-center rounded-2xl border border-slate-100 bg-slate-50 px-3 py-2">
                  <span className={`mb-1 h-2.5 w-2.5 rounded-full ${s.color}`} />
                  <span className="text-lg font-bold text-slate-900">{s.value}</span>
                  <span className="text-[10px] uppercase tracking-wide text-slate-500">{s.label}</span>
                </div>
                {i < stages.length - 1 && (
                  <div className="hidden h-1 w-6 rounded-full bg-gradient-to-r from-lime/80 to-sky-300 sm:block" />
                )}
              </div>
            ))}
          </div>
          {capturaItens.length > 0 && (
            <div className="mt-4 border-t border-slate-100 pt-3">
              <p className="mb-2 text-xs font-semibold uppercase tracking-wide text-slate-500">Captura de contato</p>
              <div className="flex flex-wrap gap-2">
                {capturaItens.map((c) => (
                  <div key={c.label} className="flex items-baseline gap-2 rounded-2xl border border-slate-100 bg-slate-50 px-3 py-2">
                    <span className="text-lg font-bold text-slate-900">{c.value}</span>
                    <span className="text-xs text-slate-500">
                      {c.label} · {pct(c.value)}
                    </span>
                  </div>
                ))}
              </div>
            </div>
          )}
        </Card.Content>
      </Card>

      <div className="grid min-h-0 flex-1 gap-3 lg:grid-cols-[1.4fr_1fr]">
        <Card className="rounded-[1.75rem] border border-white/60 bg-white/90 shadow-sm">
          <Card.Header>
            <Card.Title className="text-lg">Conversas</Card.Title>
            <Card.Description>Selecione um lead para o resumo do corretor</Card.Description>
          </Card.Header>
          <Card.Content className="gap-2">
            {loading && leads.length === 0 ? (
              <div className="flex items-center justify-center gap-2 py-12 text-slate-500">
                <Spinner size="sm" />
                <span className="text-sm">Carregando…</span>
              </div>
            ) : leads.length === 0 ? (
              <EmptyState className="py-10 text-center">
                <p className="font-medium">Nenhum lead ainda</p>
                <p className="mt-1 text-sm text-slate-500">Use Mensagens para iniciar conversas.</p>
              </EmptyState>
            ) : (
              <ul className="space-y-1">
                {leads.map((l) => (
                  <li key={l.lead_id}>
                    <button
                      type="button"
                      onClick={() => void abrirLead(l.lead_id)}
                      className={`flex w-full items-center gap-3 rounded-2xl px-3 py-2.5 text-left transition hover:bg-slate-50 ${
                        selecionado?.lead_id === l.lead_id ? "bg-slate-100" : ""
                      }`}
                    >
                      <Avatar className="bg-navy text-white" size="sm">
                        <Avatar.Fallback>{l.lead_id.slice(0, 2)}</Avatar.Fallback>
                      </Avatar>
                      <div className="min-w-0 flex-1">
                        <p className="truncate text-sm font-semibold">
                          {l.nome ? `${l.nome} · ${l.lead_id}` : l.lead_id}
                        </p>
                        <p className="truncate text-xs text-slate-500">
                          {l.intencao || "—"} · {l.mensagens} msgs
                        </p>
                      </div>
                      <PriorityChip prioridade={l.prioridade} />
                      <span className="w-8 text-right text-sm font-semibold text-slate-700">{l.score}</span>
                    </button>
                  </li>
                ))}
              </ul>
            )}
          </Card.Content>
        </Card>

        <Card className="rounded-[1.75rem] border border-white/60 bg-white/90 shadow-sm">
          <Card.Header>
            <Card.Title className="text-lg">
              {selecionado ? selecionado.lead_id : "Detalhe"}
            </Card.Title>
            <Card.Description>
              {selecionado ? "Resumo para o corretor" : "Escolha um lead na lista"}
            </Card.Description>
          </Card.Header>
          <Card.Content className="gap-4">
            {!selecionado ? (
              <EmptyState className="py-8 text-center">
                <p className="font-medium">Nada selecionado</p>
              </EmptyState>
            ) : (
              <>
                {resumo && <ResumoCorretor resumo={resumo} />}
                <h3 className="pt-1 text-xs font-semibold uppercase tracking-wide text-slate-500">
                  Últimas mensagens
                </h3>
                <ul className="space-y-2 text-sm">
                  {(selecionado.mensagens || []).slice(-6).map((m, i) => (
                    <li key={i} className="rounded-xl border border-slate-100 px-3 py-2">
                      <span className="font-semibold capitalize text-slate-600">{m.papel}: </span>
                      {m.texto}
                    </li>
                  ))}
                </ul>
              </>
            )}
          </Card.Content>
        </Card>
      </div>
    </div>
  );
}
