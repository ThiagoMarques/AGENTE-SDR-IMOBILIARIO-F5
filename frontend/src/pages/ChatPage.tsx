import {
  Alert,
  Avatar,
  Button,
  Chip,
  EmptyState,
  Input,
  ScrollShadow,
  Spinner,
  TextArea,
} from "@heroui/react";
import { FormEvent, useCallback, useEffect, useMemo, useRef, useState } from "react";
import { api, Dashboard, Mensagem, Qualificacao } from "../api";
import { PriorityChip } from "../components/PriorityChip";

type LeadRow = Dashboard["leads"][number];

function initials(id: string) {
  const clean = id.replace(/[^A-Za-z0-9]/g, "");
  return (clean.slice(0, 2) || "LD").toUpperCase();
}

export default function ChatPage() {
  const [leads, setLeads] = useState<LeadRow[]>([]);
  const [leadId, setLeadId] = useState("LEAD-001");
  const [busca, setBusca] = useState("");
  const [texto, setTexto] = useState("");
  const [mensagens, setMensagens] = useState<Mensagem[]>([]);
  const [perfil, setPerfil] = useState<Record<string, unknown>>({});
  const [imoveis, setImoveis] = useState<Record<string, unknown>[]>([]);
  const [matchBusca, setMatchBusca] = useState<string>("vazio");
  const [qual, setQual] = useState<Qualificacao | null>(null);
  const [loading, setLoading] = useState(false);
  const [boot, setBoot] = useState(true);
  const [erro, setErro] = useState<string | null>(null);
  const [novoLead, setNovoLead] = useState("");
  const fimRef = useRef<HTMLDivElement>(null);

  const carregarLista = useCallback(async () => {
    try {
      const dash = await api.dashboard();
      setLeads(dash.leads || []);
      if (!(dash.leads || []).some((l) => l.lead_id === leadId) && (dash.leads || []).length) {
        // keep current leadId even if new
      }
    } catch {
      /* lista vazia ok */
    }
  }, [leadId]);

  useEffect(() => {
    void carregarLista();
  }, [carregarLista]);

  useEffect(() => {
    fimRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [mensagens, imoveis]);

  useEffect(() => {
    let cancel = false;
    (async () => {
      setBoot(true);
      try {
        const lead = await api.lead(leadId);
        if (!cancel) {
          setMensagens(lead.mensagens || []);
          setPerfil(lead.perfil || {});
          setQual(
            lead.score != null
              ? {
                  score: Number(lead.score),
                  prioridade: String(lead.prioridade || "frio"),
                  campos_faltantes: [],
                  pronto_para_agendar: false,
                }
              : null,
          );
          setImoveis([]);
          setMatchBusca("vazio");
          setErro(null);
        }
      } catch {
        if (!cancel) {
          setMensagens([]);
          setPerfil({});
          setQual(null);
          setImoveis([]);
          setMatchBusca("vazio");
        }
      } finally {
        if (!cancel) setBoot(false);
      }
    })();
    return () => {
      cancel = true;
    };
  }, [leadId]);

  const filtrados = useMemo(() => {
    const q = busca.trim().toLowerCase();
    const base = [...leads];
    if (!base.some((l) => l.lead_id === leadId)) {
      base.unshift({
        lead_id: leadId,
        score: qual?.score ?? 0,
        prioridade: qual?.prioridade ?? "frio",
        mensagens: mensagens.length,
        intencao: String(perfil.intencao || ""),
      });
    }
    if (!q) return base;
    return base.filter(
      (l) =>
        l.lead_id.toLowerCase().includes(q) ||
        String(l.intencao || "")
          .toLowerCase()
          .includes(q),
    );
  }, [leads, busca, leadId, qual, mensagens.length, perfil.intencao]);

  async function enviar(e?: FormEvent) {
    e?.preventDefault();
    const msg = texto.trim();
    if (!msg || loading) return;
    setLoading(true);
    setErro(null);
    setMensagens((m) => [...m, { papel: "lead", texto: msg }]);
    setTexto("");
    try {
      const out = await api.chat(leadId, msg);
      setMensagens((m) => [...m, { papel: "agente", texto: out.resposta }]);
      setQual(out.qualificacao);
      setPerfil(out.perfil || {});
      setImoveis(out.exibir_imoveis === false ? [] : out.imoveis || []);
      setMatchBusca(out.match_busca || "vazio");
      await carregarLista();
    } catch (err) {
      setErro(err instanceof Error ? err.message : "Falha ao enviar");
    } finally {
      setLoading(false);
    }
  }

  async function followUp() {
    setLoading(true);
    setErro(null);
    try {
      const out = await api.followUp(leadId);
      setMensagens((m) => [...m, { papel: "agente", texto: out.resposta }]);
      setQual(out.qualificacao);
      await carregarLista();
    } catch (err) {
      setErro(err instanceof Error ? err.message : "Falha no follow-up");
    } finally {
      setLoading(false);
    }
  }

  function criarLead() {
    const id = (novoLead.trim() || `LEAD-${Date.now().toString().slice(-4)}`).toUpperCase();
    setLeadId(id);
    setNovoLead("");
    setMensagens([]);
    setPerfil({});
    setQual(null);
    setImoveis([]);
    setMatchBusca("vazio");
  }

  return (
    <div className="grid h-full min-h-0 grid-cols-1 gap-3 lg:grid-cols-[320px_minmax(0,1fr)]">
      {/* Inbox */}
      <section className="flex min-h-0 flex-col overflow-hidden rounded-[1.75rem] border border-white/60 bg-white/85 shadow-sm backdrop-blur">
        <div className="space-y-3 border-b border-slate-100 p-4">
          <div className="relative">
            <span className="pointer-events-none absolute left-3 top-1/2 -translate-y-1/2 text-slate-400">
              ⌕
            </span>
            <Input
              className="w-full rounded-full bg-slate-100/80 pl-9"
              placeholder="Buscar"
              value={busca}
              onChange={(e) => setBusca(e.target.value)}
              aria-label="Buscar leads"
            />
          </div>
          <div className="flex items-center justify-between">
            <h2 className="text-lg font-semibold tracking-tight">Mensagens</h2>
            <Chip size="sm" variant="soft" color="success">
              <Chip.Label>{filtrados.length}</Chip.Label>
            </Chip>
          </div>
          <div className="flex gap-2">
            <Input
              className="flex-1 rounded-xl bg-slate-50"
              placeholder="Novo lead (ex. LEAD-010)"
              value={novoLead}
              onChange={(e) => setNovoLead(e.target.value)}
            />
            <Button size="sm" variant="primary" className="rounded-xl bg-lime" onPress={criarLead}>
              +
            </Button>
          </div>
        </div>

        <ScrollShadow className="min-h-0 flex-1 p-2">
          {filtrados.length === 0 ? (
            <EmptyState className="px-4 py-10 text-center">
              <p className="text-sm font-medium">Nenhum lead</p>
              <p className="mt-1 text-xs text-slate-500">Crie um lead ou envie a primeira mensagem.</p>
            </EmptyState>
          ) : (
            <ul className="space-y-1">
              {filtrados.map((l) => {
                const active = l.lead_id === leadId;
                return (
                  <li key={l.lead_id}>
                    <button
                      type="button"
                      onClick={() => setLeadId(l.lead_id)}
                      className={`flex w-full items-center gap-3 rounded-2xl px-3 py-2.5 text-left transition ${
                        active ? "bg-slate-100" : "hover:bg-slate-50"
                      }`}
                    >
                      <div className="relative">
                        <Avatar size="md" className="bg-navy text-white">
                          <Avatar.Fallback>{initials(l.lead_id)}</Avatar.Fallback>
                        </Avatar>
                        <span
                          className={`absolute bottom-0 right-0 h-2.5 w-2.5 rounded-full border-2 border-white ${
                            l.prioridade === "quente"
                              ? "bg-red-500"
                              : l.prioridade === "morno"
                                ? "bg-amber-400"
                                : "bg-lime"
                          }`}
                        />
                      </div>
                      <div className="min-w-0 flex-1">
                        <div className="flex items-center justify-between gap-2">
                          <p className="truncate text-sm font-semibold text-slate-900">{l.lead_id}</p>
                          <span className="shrink-0 text-[10px] text-slate-400">{l.score}</span>
                        </div>
                        <p className="truncate text-xs text-slate-500">
                          {l.intencao || "sem intenção"} · {l.mensagens} msgs
                        </p>
                      </div>
                    </button>
                  </li>
                );
              })}
            </ul>
          )}
        </ScrollShadow>
      </section>

      {/* Chat */}
      <section className="flex min-h-0 flex-col overflow-hidden rounded-[1.75rem] border border-white/60 bg-white/90 shadow-sm backdrop-blur">
        <div className="flex items-center justify-between gap-3 border-b border-slate-100 px-4 py-3 sm:px-5">
          <div className="flex items-center gap-3">
            <Avatar className="bg-navy text-white">
              <Avatar.Fallback>{initials(leadId)}</Avatar.Fallback>
            </Avatar>
            <div>
              <p className="font-semibold text-slate-900">{leadId}</p>
              <p className="flex items-center gap-1.5 text-xs text-slate-500">
                <span className="inline-block h-2 w-2 rounded-full bg-lime" />
                Disponível · SDR automático
              </p>
            </div>
          </div>
          <div className="flex flex-wrap items-center justify-end gap-2">
            {qual && (
              <>
                <PriorityChip prioridade={qual.prioridade} />
                <Chip size="sm" variant="soft">
                  <Chip.Label>pontuação {qual.score}</Chip.Label>
                </Chip>
              </>
            )}
            <Button size="sm" variant="outline" className="rounded-full" isDisabled={loading} onPress={followUp}>
              Retomar contato
            </Button>
          </div>
        </div>

        <ScrollShadow className="min-h-0 flex-1 bg-gradient-to-b from-mint/40 to-transparent px-4 py-4 sm:px-5">
          {boot ? (
            <div className="flex h-full items-center justify-center gap-2 text-slate-500">
              <Spinner size="sm" />
              <span className="text-sm">Carregando conversa…</span>
            </div>
          ) : mensagens.length === 0 ? (
            <div className="flex h-full items-center justify-center">
              <EmptyState className="max-w-sm text-center">
                <p className="text-base font-semibold">Comece o atendimento</p>
                <p className="mt-1 text-sm text-slate-500">
                  Ex.: “Estou procurando apartamento na zona sul.”
                </p>
              </EmptyState>
            </div>
          ) : (
            <div className="mx-auto flex max-w-3xl flex-col gap-3">
              {mensagens.map((m, i) => {
                const isLead = m.papel === "lead";
                return (
                  <div key={`${m.papel}-${i}`} className={`flex ${isLead ? "justify-end" : "justify-start"}`}>
                    <div className={`max-w-[min(92%,34rem)] px-4 py-2.5 shadow-sm ${isLead ? "bubble-lead" : "bubble-agent"}`}>
                      <p className="whitespace-pre-wrap text-sm leading-relaxed">{m.texto}</p>
                    </div>
                  </div>
                );
              })}
              {imoveis.length > 0 && (
                <div className="rounded-[1.5rem] bg-navy p-3 text-white shadow-md">
                  <p className="mb-2 text-xs font-medium text-white/70">
                    {matchBusca === "aproximado" ? "Opções próximas" : "Imóveis sugeridos"}
                  </p>
                  <div className="grid gap-2 sm:grid-cols-3">
                    {imoveis.slice(0, 3).map((im) => (
                      <div key={String(im.id)} className="rounded-xl bg-white p-3 text-slate-900">
                        <p className="line-clamp-2 text-xs font-semibold">
                          {String(im.endereco || im.titulo || im.id)}
                        </p>
                        <p className="mt-1 text-[11px] text-slate-500">
                          {String(im.quartos ?? "—")} quartos · {String(im.cidade || "—")}
                        </p>
                        {matchBusca === "aproximado" && im.match_motivo ? (
                          <p className="mt-1 line-clamp-2 text-[10px] leading-snug text-slate-400">
                            {String(im.match_motivo)}
                          </p>
                        ) : null}
                        <p className="mt-2 text-sm font-bold text-lime-dark">
                          {String(im.moeda || "BRL")}{" "}
                          {Number(im.preco || 0).toLocaleString("pt-BR", { maximumFractionDigits: 0 })}
                        </p>
                      </div>
                    ))}
                  </div>
                </div>
              )}
              {Object.keys(perfil).length > 0 && (
                <div className="rounded-2xl border border-slate-200 bg-white/90 p-3 text-xs text-slate-600">
                  <span className="font-semibold text-slate-800">Perfil: </span>
                  {Object.entries(perfil)
                    .map(([k, v]) => `${k}=${String(v)}`)
                    .join(" · ")}
                </div>
              )}
              <div ref={fimRef} />
            </div>
          )}
        </ScrollShadow>

        {erro && (
          <div className="px-4 pb-2">
            <Alert status="danger">
              <Alert.Content>
                <Alert.Title>Erro</Alert.Title>
                <Alert.Description>{erro}</Alert.Description>
              </Alert.Content>
            </Alert>
          </div>
        )}

        <form
          className="flex items-end gap-2 border-t border-slate-100 bg-white/95 p-3 sm:p-4"
          onSubmit={enviar}
        >
          <TextArea
            className="min-h-[48px] flex-1 rounded-2xl bg-slate-50 px-4 py-3"
            placeholder="Escreva uma mensagem"
            value={texto}
            onChange={(e) => setTexto(e.target.value)}
            rows={2}
            disabled={loading}
            aria-label="Mensagem"
          />
          <Button
            type="submit"
            isIconOnly
            className="h-12 w-12 shrink-0 rounded-full bg-navy text-white"
            isDisabled={loading || !texto.trim()}
            aria-label="Enviar"
          >
            {loading ? <Spinner size="sm" color="current" /> : "↑"}
          </Button>
        </form>
      </section>
    </div>
  );
}
