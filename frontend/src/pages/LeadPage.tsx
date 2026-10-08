import { Alert, Avatar, Button, ScrollShadow, Spinner, TextArea } from "@heroui/react";
import { FormEvent, useEffect, useRef, useState } from "react";
import { Agendamento, api, Mensagem } from "../api";
import { AgendamentoCard } from "../components/AgendamentoCard";
import { PropertyCards } from "../components/PropertyCards";

const CHAVE_LEAD = "sdr-lead-id";

function novoLeadId() {
  return `SITE-${Date.now().toString(36).slice(-4)}${Math.random().toString(36).slice(2, 4)}`.toUpperCase();
}

function leadDoNavegador() {
  const salvo = localStorage.getItem(CHAVE_LEAD);
  if (salvo) return salvo;
  const id = novoLeadId();
  localStorage.setItem(CHAVE_LEAD, id);
  return id;
}

const SUGESTOES = [
  "Quero comprar um apartamento",
  "Procuro imóvel para alugar",
  "Quero investir em imóveis",
];

/** O que o lead vê: só a conversa, imóveis e a visita — sem score, perfil ou outros leads. */
export default function LeadPage() {
  const [leadId, setLeadId] = useState(leadDoNavegador);
  const [mensagens, setMensagens] = useState<Mensagem[]>([]);
  const [imoveis, setImoveis] = useState<Record<string, unknown>[]>([]);
  const [matchBusca, setMatchBusca] = useState("vazio");
  const [agendamento, setAgendamento] = useState<Agendamento | null>(null);
  const [texto, setTexto] = useState("");
  const [loading, setLoading] = useState(false);
  const [boot, setBoot] = useState(true);
  const [erro, setErro] = useState<string | null>(null);
  const fimRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    let cancel = false;
    setBoot(true);
    api
      .lead(leadId)
      .then((lead) => {
        if (cancel) return;
        setMensagens(lead.mensagens || []);
        setAgendamento([...(lead.agendamentos || [])].reverse().find((a) => a.status === "agendado") ?? null);
      })
      .catch(() => {
        if (!cancel) setMensagens([]);
      })
      .finally(() => {
        if (!cancel) setBoot(false);
      });
    return () => {
      cancel = true;
    };
  }, [leadId]);

  useEffect(() => {
    fimRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [mensagens, imoveis, agendamento, loading]);

  async function enviar(msg: string) {
    const limpa = msg.trim();
    if (!limpa || loading) return;
    setLoading(true);
    setErro(null);
    setMensagens((m) => [...m, { papel: "lead", texto: limpa }]);
    setTexto("");
    try {
      const out = await api.chat(leadId, limpa);
      setMensagens((m) => [...m, { papel: "agente", texto: out.resposta }]);
      setImoveis(out.exibir_imoveis === false ? [] : out.imoveis || []);
      setMatchBusca(out.match_busca || "vazio");
      setAgendamento(out.agendamento ?? null);
    } catch {
      setErro("Não consegui enviar sua mensagem agora. Tente de novo em instantes.");
    } finally {
      setLoading(false);
    }
  }

  function onSubmit(e: FormEvent) {
    e.preventDefault();
    void enviar(texto);
  }

  function novaConversa() {
    const id = novoLeadId();
    localStorage.setItem(CHAVE_LEAD, id);
    setLeadId(id);
    setMensagens([]);
    setImoveis([]);
    setMatchBusca("vazio");
    setAgendamento(null);
    setErro(null);
  }

  return (
    <div className="mx-auto flex h-full min-h-0 w-full max-w-3xl flex-col overflow-hidden rounded-[1.75rem] border border-white/60 bg-white/90 shadow-sm backdrop-blur">
      <div className="flex items-center justify-between gap-3 border-b border-slate-100 px-4 py-3 sm:px-5">
        <div className="flex items-center gap-3">
          <Avatar className="bg-navy text-white">
            <Avatar.Fallback>AI</Avatar.Fallback>
          </Avatar>
          <div>
            <p className="font-semibold text-slate-900">Atendimento da imobiliária</p>
            <p className="flex items-center gap-1.5 text-xs text-slate-500">
              <span className="inline-block h-2 w-2 rounded-full bg-lime" />
              Assistente virtual · responde na hora
            </p>
          </div>
        </div>
        <Button size="sm" variant="outline" className="rounded-full" isDisabled={loading} onPress={novaConversa}>
          Nova conversa
        </Button>
      </div>

      <ScrollShadow className="min-h-0 flex-1 bg-gradient-to-b from-mint/40 to-transparent px-4 py-4 sm:px-5">
        {boot ? (
          <div className="flex h-full items-center justify-center gap-2 text-slate-500">
            <Spinner size="sm" />
            <span className="text-sm">Carregando…</span>
          </div>
        ) : mensagens.length === 0 ? (
          <div className="flex h-full flex-col items-center justify-center gap-4 text-center">
            <div>
              <p className="text-base font-semibold text-slate-900">Olá! Como posso ajudar?</p>
              <p className="mt-1 text-sm text-slate-500">
                Encontro imóveis para comprar, alugar ou investir e marco sua visita com um corretor.
              </p>
            </div>
            <div className="flex flex-wrap justify-center gap-2">
              {SUGESTOES.map((s) => (
                <button
                  key={s}
                  type="button"
                  onClick={() => void enviar(s)}
                  className="rounded-full border border-slate-200 bg-white px-3 py-1.5 text-xs font-medium text-slate-700 transition hover:border-slate-300 hover:bg-slate-50"
                >
                  {s}
                </button>
              ))}
            </div>
          </div>
        ) : (
          <div className="mx-auto flex max-w-2xl flex-col gap-3">
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
            {loading && (
              <div className="flex justify-start">
                <div className="bubble-agent flex items-center gap-2 px-4 py-2.5 shadow-sm">
                  <Spinner size="sm" color="current" />
                  <span className="text-sm">digitando…</span>
                </div>
              </div>
            )}
            <PropertyCards imoveis={imoveis} matchBusca={matchBusca} />
            {agendamento && <AgendamentoCard agendamento={agendamento} paraLead />}
            <div ref={fimRef} />
          </div>
        )}
      </ScrollShadow>

      {erro && (
        <div className="px-4 pb-2">
          <Alert status="danger">
            <Alert.Content>
              <Alert.Description>{erro}</Alert.Description>
            </Alert.Content>
          </Alert>
        </div>
      )}

      <form className="flex items-end gap-2 border-t border-slate-100 bg-white/95 p-3 sm:p-4" onSubmit={onSubmit}>
        <TextArea
          className="min-h-[48px] flex-1 rounded-2xl bg-slate-50 px-4 py-3"
          placeholder="Digite sua mensagem"
          value={texto}
          onChange={(e) => setTexto(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter" && !e.shiftKey) {
              e.preventDefault();
              void enviar(texto);
            }
          }}
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
          ↑
        </Button>
      </form>
    </div>
  );
}
