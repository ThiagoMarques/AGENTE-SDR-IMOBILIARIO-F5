import { Alert, Button, Card, Chip, EmptyState, Spinner } from "@heroui/react";
import { useCallback, useEffect, useMemo, useState } from "react";
import {
  api,
  CasoRegressao,
  ContextoTreino,
  ExecucaoTreino,
  FalhaAutomatica,
  FalhaJuiz,
  Rodada,
  TreinadorConfig,
} from "../api";
import { MetricCard } from "../components/MetricCard";

const CRITERIOS: Record<string, string> = {
  compreensao: "Compreensão",
  naturalidade: "Naturalidade",
  progresso: "Progresso",
  veracidade: "Veracidade",
  duvidas: "Dúvidas",
};

const ESTADOS: Record<Rodada["estado"], { label: string; color: "default" | "accent" | "success" | "warning" | "danger" }> = {
  iniciando: { label: "Iniciando", color: "default" },
  rodando: { label: "Rodando", color: "accent" },
  concluida: { label: "Concluída", color: "success" },
  erro: { label: "Erro", color: "danger" },
  interrompida: { label: "Interrompida", color: "warning" },
};

const emAndamento = (r?: Rodada | null) => r?.estado === "rodando" || r?.estado === "iniciando";

const nomePersona = (id: string, nome?: string | null) => nome || id.replace(/_/g, " ");

const EXEMPLO_CONTEXTO =
  "Ex.: simule uma conversa de um senhor de idade que fala pausadamente e possui confusões e dúvidas";

function quando(iso?: string | null) {
  if (!iso) return "—";
  return new Date(iso).toLocaleString("pt-BR", { day: "2-digit", month: "2-digit", hour: "2-digit", minute: "2-digit" });
}

function EstadoChip({ estado }: { estado: Rodada["estado"] }) {
  const e = ESTADOS[estado] ?? ESTADOS.iniciando;
  return (
    <Chip color={e.color} variant="soft" size="sm">
      <Chip.Label>{e.label}</Chip.Label>
    </Chip>
  );
}

function Toggle({
  checked,
  onChange,
  label,
  hint,
  disabled,
}: {
  checked: boolean;
  onChange: (v: boolean) => void;
  label: string;
  hint?: string;
  disabled?: boolean;
}) {
  return (
    <label className={`flex items-start gap-3 ${disabled ? "opacity-50" : "cursor-pointer"}`}>
      <input
        type="checkbox"
        className="peer sr-only"
        checked={checked}
        disabled={disabled}
        onChange={(e) => onChange(e.target.checked)}
      />
      <span className="mt-0.5 flex h-5 w-9 shrink-0 items-center rounded-full bg-slate-300 p-0.5 transition peer-checked:bg-lime peer-focus-visible:ring-2 peer-focus-visible:ring-navy/40 peer-checked:[&>span]:translate-x-4">
        <span className="h-4 w-4 rounded-full bg-white shadow transition" />
      </span>
      <span>
        <span className="block text-sm font-medium text-slate-800">{label}</span>
        {hint && <span className="block text-xs text-slate-500">{hint}</span>}
      </span>
    </label>
  );
}

function Numero({
  label,
  value,
  min,
  max,
  onChange,
}: {
  label: string;
  value: number;
  min: number;
  max: number;
  onChange: (v: number) => void;
}) {
  return (
    <label className="flex flex-col gap-1">
      <span className="text-xs font-semibold uppercase tracking-wide text-slate-500">{label}</span>
      <input
        type="number"
        min={min}
        max={max}
        value={value}
        onChange={(e) => onChange(Math.min(max, Math.max(min, Number(e.target.value) || min)))}
        className="w-full rounded-xl border border-slate-200 bg-white px-3 py-2 text-sm outline-none focus:border-navy"
      />
    </label>
  );
}

function BarraNota({ label, nota }: { label: string; nota: number }) {
  const cor = nota >= 4 ? "bg-lime" : nota >= 3 ? "bg-amber-400" : "bg-red-400";
  return (
    <div className="flex items-center gap-3">
      <span className="w-28 shrink-0 text-xs text-slate-600">{label}</span>
      <div className="h-2 flex-1 rounded-full bg-slate-100">
        <div className={`h-2 rounded-full ${cor}`} style={{ width: `${(nota / 5) * 100}%` }} />
      </div>
      <span className="w-8 text-right text-xs font-semibold text-slate-700">{nota.toFixed(1)}</span>
    </div>
  );
}

function Falha({ falha, origem }: { falha: FalhaAutomatica | FalhaJuiz; origem: "automática" | "juiz" }) {
  const sugestao = "sugestao" in falha ? falha.sugestao : "";
  return (
    <div
      className={`rounded-xl border px-3 py-2 text-xs ${
        origem === "automática" ? "border-red-200 bg-red-50 text-red-800" : "border-amber-200 bg-amber-50 text-amber-900"
      }`}
    >
      <p>
        <span className="font-semibold">
          {origem === "automática" ? "Falha automática" : "Juiz"} · {falha.tipo.replace(/_/g, " ")}:
        </span>{" "}
        {falha.descricao}
      </p>
      {sugestao && <p className="mt-1 opacity-80">Sugestão: {sugestao}</p>}
    </div>
  );
}

function Transcricao({ execucao }: { execucao: ExecucaoTreino }) {
  const porTurno = useMemo(() => {
    const mapa = new Map<number, { auto: FalhaAutomatica[]; juiz: FalhaJuiz[] }>();
    const pegar = (t: number) => mapa.get(t) ?? mapa.set(t, { auto: [], juiz: [] }).get(t)!;
    execucao.avaliacao.deterministicas.forEach((f) => pegar(f.turno).auto.push(f));
    execucao.avaliacao.juiz.falhas.forEach((f) => pegar(f.turno).juiz.push(f));
    return mapa;
  }, [execucao]);

  let turno = 0;
  return (
    <div className="space-y-2">
      {execucao.conversa.map((m, i) => {
        const doLead = m.papel === "lead";
        if (doLead) turno += 1;
        const falhas = !doLead ? porTurno.get(turno) : undefined;
        return (
          <div key={i} className={`flex flex-col gap-1 ${doLead ? "items-end" : "items-start"}`}>
            <div
              className={`max-w-[85%] whitespace-pre-line rounded-2xl px-3 py-2 text-sm ${
                doLead ? "bg-navy text-white" : "border border-slate-100 bg-white text-slate-800"
              }`}
            >
              {m.texto || <span className="italic opacity-60">(sem resposta)</span>}
            </div>
            {falhas && (falhas.auto.length > 0 || falhas.juiz.length > 0) && (
              <div className="w-full max-w-[85%] space-y-1">
                {falhas.auto.map((f, j) => (
                  <Falha key={`a${j}`} falha={f} origem="automática" />
                ))}
                {falhas.juiz.map((f, j) => (
                  <Falha key={`j${j}`} falha={f} origem="juiz" />
                ))}
              </div>
            )}
          </div>
        );
      })}
      {execucao.erro && <Falha falha={{ tipo: "erro_no_agente", turno, descricao: execucao.erro }} origem="automática" />}
    </div>
  );
}

function LinhaExecucao({ execucao, aberta, onToggle }: { execucao: ExecucaoTreino; aberta: boolean; onToggle: () => void }) {
  const av = execucao.avaliacao;
  const falhas = av.deterministicas.length + av.juiz.falhas.length;
  return (
    <li className="rounded-2xl border border-slate-100 bg-slate-50/60">
      <button type="button" onClick={onToggle} className="flex w-full items-center gap-3 px-3 py-2.5 text-left">
        <span className={`h-2.5 w-2.5 shrink-0 rounded-full ${av.aprovada ? "bg-lime" : "bg-red-400"}`} />
        <div className="min-w-0 flex-1">
          <p className="truncate text-sm font-semibold">
            {nomePersona(execucao.persona, execucao.persona_nome)}
            {execucao.persona.startsWith("ctx_") && (
              <span className="ml-2 rounded-full bg-sky-100 px-2 py-0.5 text-[10px] font-semibold uppercase text-sky-800">
                contexto
              </span>
            )}
          </p>
          <p className="truncate text-xs text-slate-500">
            {execucao.conversa.length / 2} turnos · {execucao.fim}
          </p>
        </div>
        <span className="text-xs text-slate-500">{falhas} falha{falhas === 1 ? "" : "s"}</span>
        <span className="w-10 text-right text-sm font-semibold text-slate-700">
          {av.media != null ? av.media.toFixed(1) : "—"}
        </span>
        <span className="text-slate-400">{aberta ? "▾" : "▸"}</span>
      </button>
      {aberta && (
        <div className="space-y-3 border-t border-slate-100 px-3 py-3">
          {execucao.persona.startsWith("ctx_") && execucao.persona_descricao && (
            <p className="rounded-xl bg-sky-50 px-3 py-2 text-xs text-sky-900">
              <span className="font-semibold">Contexto:</span> {execucao.persona_descricao}
            </p>
          )}
          {av.juiz.resumo && <p className="text-sm italic text-slate-600">{av.juiz.resumo}</p>}
          <Transcricao execucao={execucao} />
        </div>
      )}
    </li>
  );
}

function DetalheRodada({ rodada }: { rodada: Rodada }) {
  const [aberta, setAberta] = useState<string | null>(null);
  const execucoes = rodada.execucoes ?? [];
  const notas = useMemo(() => {
    const soma: Record<string, number[]> = {};
    execucoes.forEach((e) =>
      Object.entries(e.avaliacao.juiz.notas).forEach(([k, v]) => (soma[k] ??= []).push(v)),
    );
    return Object.keys(CRITERIOS)
      .filter((k) => soma[k]?.length)
      .map((k) => ({ k, media: soma[k].reduce((a, b) => a + b, 0) / soma[k].length }));
  }, [execucoes]);
  const ordenadas = [...execucoes].sort(
    (a, b) => Number(a.avaliacao.aprovada) - Number(b.avaliacao.aprovada) || (a.avaliacao.media ?? 0) - (b.avaliacao.media ?? 0),
  );
  const resumo = rodada.resumo;
  const total = rodada.total ?? 0;

  return (
    <div className="space-y-4">
      {emAndamento(rodada) && (
        <div className="space-y-2 rounded-2xl border border-sky-100 bg-sky-50 px-4 py-3">
          <div className="flex items-center gap-2 text-sm text-sky-900">
            <Spinner size="sm" />
            {rodada.atual
              ? `Conversando como ${nomePersona(rodada.atual.persona, rodada.atual.persona_nome)}…`
              : "Preparando a rodada…"}
            <span className="ml-auto font-semibold">
              {rodada.concluidas ?? 0}/{total || "?"}
            </span>
          </div>
          <div className="h-2 rounded-full bg-white">
            <div
              className="h-2 rounded-full bg-sky-400 transition-all"
              style={{ width: `${total ? ((rodada.concluidas ?? 0) / total) * 100 : 5}%` }}
            />
          </div>
        </div>
      )}

      {rodada.estado === "erro" && (
        <Alert status="danger">
          <Alert.Content>
            <Alert.Title>A rodada falhou</Alert.Title>
            <Alert.Description className="whitespace-pre-line">{rodada.erro}</Alert.Description>
          </Alert.Content>
        </Alert>
      )}
      {rodada.estado === "interrompida" && (
        <Alert status="warning">
          <Alert.Content>
            <Alert.Title>Rodada interrompida</Alert.Title>
            <Alert.Description>O processo do treinador parou antes de terminar. As conversas abaixo foram salvas.</Alert.Description>
          </Alert.Content>
        </Alert>
      )}

      <div className="grid grid-cols-2 gap-3 xl:grid-cols-4">
        <MetricCard label="Aprovadas" value={resumo ? `${resumo.aprovadas}/${execucoes.length}` : "—"} />
        <MetricCard label="Média do juiz" value={resumo?.media != null ? resumo.media.toFixed(1) : "—"} hint="de 1 a 5" />
        <MetricCard label="Falhas automáticas" value={resumo?.falhas_automaticas ?? 0} tone={resumo?.falhas_automaticas ? "quente" : "default"} />
        <MetricCard label="Falhas do juiz" value={resumo?.falhas_juiz ?? 0} tone={resumo?.falhas_juiz ? "morno" : "default"} />
      </div>

      {notas.length > 0 && (
        <div className="space-y-2 rounded-2xl border border-slate-100 bg-white px-4 py-3">
          <p className="text-xs font-semibold uppercase tracking-wide text-slate-500">Notas médias por critério</p>
          {notas.map(({ k, media }) => (
            <BarraNota key={k} label={CRITERIOS[k]} nota={media} />
          ))}
        </div>
      )}

      {rodada.casos && rodada.casos.length > 0 && (
        <p className="rounded-2xl border border-lime/40 bg-lime/10 px-4 py-2 text-sm text-slate-700">
          {rodada.casos.length} conversa{rodada.casos.length === 1 ? "" : "s"} reprovada
          {rodada.casos.length === 1 ? " virou caso" : "s viraram casos"} de regressão em <code>tests/regressao/casos/</code>.
        </p>
      )}

      {ordenadas.length === 0 ? (
        !emAndamento(rodada) && (
          <EmptyState className="py-8 text-center">
            <p className="font-medium">Nenhuma conversa nesta rodada</p>
          </EmptyState>
        )
      ) : (
        <ul className="space-y-2">
          {ordenadas.map((e) => (
            <LinhaExecucao
              key={e.lead_id}
              execucao={e}
              aberta={aberta === e.lead_id}
              onToggle={() => setAberta(aberta === e.lead_id ? null : e.lead_id)}
            />
          ))}
        </ul>
      )}
    </div>
  );
}

function ListaCasos({ casos }: { casos: CasoRegressao[] }) {
  if (casos.length === 0) {
    return (
      <EmptyState className="py-8 text-center">
        <p className="font-medium">Nenhum caso de regressão</p>
        <p className="mt-1 text-sm text-slate-500">Conversas com falha automática viram casos aqui.</p>
      </EmptyState>
    );
  }
  return (
    <ul className="space-y-2">
      {casos.map((c) => (
        <li key={c.arquivo} className="space-y-2 rounded-2xl border border-slate-100 bg-slate-50/60 px-3 py-2.5">
          <div className="flex items-center gap-2">
            <p className="flex-1 truncate text-sm font-semibold">{nomePersona(c.persona, c.persona_nome)}</p>
            <span className="text-xs text-slate-500">{quando(c.criado_em)}</span>
          </div>
          <p className="text-xs text-slate-500">
            Mensagens do lead: {c.mensagens_lead.map((m) => `“${m}”`).join(" → ")}
          </p>
          <div className="space-y-1">
            {c.falhas_detectadas.map((f, i) => (
              <Falha key={i} falha={f} origem="automática" />
            ))}
          </div>
          <p className="text-[11px] text-slate-400">{c.arquivo}</p>
        </li>
      ))}
    </ul>
  );
}

function Contextos({
  contextos,
  selecionados,
  habilitado,
  carregando,
  onAlternar,
  onCriar,
  onRemover,
}: {
  contextos: ContextoTreino[];
  selecionados: Set<string>;
  habilitado: boolean;
  carregando: boolean;
  onAlternar: (id: string) => void;
  onCriar: (contexto: string, nome: string) => Promise<void>;
  onRemover: (id: string) => void;
}) {
  const [texto, setTexto] = useState("");
  const [nome, setNome] = useState("");
  const [salvando, setSalvando] = useState(false);
  const valido = texto.trim().length >= 10;

  async function salvar() {
    setSalvando(true);
    try {
      await onCriar(texto.trim(), nome.trim());
      setTexto("");
      setNome("");
    } finally {
      setSalvando(false);
    }
  }

  return (
    <div className={habilitado ? "" : "opacity-60"}>
      <span className="text-xs font-semibold uppercase tracking-wide text-slate-500">
        Contextos para teste ({selecionados.size}/{contextos.length})
      </span>
      <p className="mb-2 text-xs text-slate-500">
        {habilitado || carregando
          ? "Descreva um lead do seu jeito. A IA interpreta a pessoa e o juiz avalia o agente com esse perfil em mente."
          : "Contextos precisam do lead e do juiz com IA ligados."}
      </p>

      {contextos.length > 0 && (
        <ul className="mb-3 max-h-48 space-y-1 overflow-auto pr-1">
          {contextos.map((c) => (
            <li key={c.id} className="group flex items-start gap-2 rounded-xl px-2 py-1.5 hover:bg-slate-50">
              <label className="flex min-w-0 flex-1 cursor-pointer items-start gap-2">
                <input
                  type="checkbox"
                  className="mt-1 accent-[#84cc16]"
                  checked={selecionados.has(c.id)}
                  disabled={!habilitado}
                  onChange={() => onAlternar(c.id)}
                />
                <span className="min-w-0">
                  <span className="block text-sm font-medium text-slate-800">{c.nome}</span>
                  <span className="line-clamp-2 block text-xs text-slate-500" title={c.contexto}>
                    {c.contexto}
                  </span>
                </span>
              </label>
              <button
                type="button"
                aria-label={`Remover contexto ${c.nome}`}
                title="Remover contexto"
                className="rounded-full px-1.5 text-slate-400 hover:bg-red-50 hover:text-red-600"
                onClick={() => onRemover(c.id)}
              >
                ×
              </button>
            </li>
          ))}
        </ul>
      )}

      <div className="space-y-2 rounded-2xl border border-dashed border-slate-200 p-3">
        <textarea
          value={texto}
          onChange={(e) => setTexto(e.target.value)}
          placeholder={EXEMPLO_CONTEXTO}
          rows={3}
          maxLength={1500}
          disabled={!habilitado}
          aria-label="Descrição do lead simulado"
          className="w-full resize-y rounded-xl border border-slate-200 bg-white px-3 py-2 text-sm outline-none focus:border-navy"
        />
        <div className="flex gap-2">
          <input
            value={nome}
            onChange={(e) => setNome(e.target.value)}
            placeholder="Nome (opcional)"
            maxLength={60}
            disabled={!habilitado}
            aria-label="Nome do contexto"
            className="min-w-0 flex-1 rounded-xl border border-slate-200 bg-white px-3 py-2 text-sm outline-none focus:border-navy"
          />
          <Button
            variant="secondary"
            className="rounded-full"
            isDisabled={!habilitado || !valido || salvando}
            onPress={() => void salvar()}
          >
            {salvando ? <Spinner size="sm" color="current" /> : "Adicionar"}
          </Button>
        </div>
      </div>
    </div>
  );
}

export default function TreinadorPage() {
  const [config, setConfig] = useState<TreinadorConfig | null>(null);
  const [rodadas, setRodadas] = useState<Rodada[]>([]);
  const [casos, setCasos] = useState<CasoRegressao[]>([]);
  const [selecionada, setSelecionada] = useState<string | null>(null);
  const [detalhe, setDetalhe] = useState<Rodada | null>(null);
  const [aba, setAba] = useState<"rodada" | "casos">("rodada");
  const [erro, setErro] = useState<string | null>(null);
  const [iniciando, setIniciando] = useState(false);

  const [personas, setPersonas] = useState<Set<string>>(new Set());
  const [contextos, setContextos] = useState<ContextoTreino[]>([]);
  const [contextosSel, setContextosSel] = useState<Set<string>>(new Set());
  const [qtdRodadas, setQtdRodadas] = useState(1);
  const [maxTurnos, setMaxTurnos] = useState(12);
  const [usarLlm, setUsarLlm] = useState(true);
  const [gerarRegressao, setGerarRegressao] = useState(true);

  const falhou = (err: unknown, padrao: string) => setErro(err instanceof Error ? err.message : padrao);

  const atualizarListas = useCallback(async () => {
    const [r, c] = await Promise.all([api.treinador.rodadas(), api.treinador.casos()]);
    setRodadas(r);
    setCasos(c);
    return r;
  }, []);

  useEffect(() => {
    (async () => {
      try {
        const cfg = await api.treinador.config();
        setConfig(cfg);
        setPersonas(new Set(cfg.personas.map((p) => p.id)));
        setContextos(cfg.contextos ?? []);
        setUsarLlm(cfg.llm_disponivel);
        const r = await atualizarListas();
        if (r[0]) setSelecionada(r[0].id);
      } catch (err) {
        falhou(err, "Falha ao carregar o treinador");
      }
    })();
  }, [atualizarListas]);

  useEffect(() => {
    if (!selecionada) return;
    setDetalhe((atual) => (atual?.id === selecionada ? atual : null));
    let ativo = true;
    let timer: ReturnType<typeof setTimeout> | undefined;
    const buscar = async () => {
      try {
        const r = await api.treinador.rodada(selecionada);
        if (!ativo) return;
        setDetalhe(r);
        if (emAndamento(r)) {
          timer = setTimeout(buscar, 2000);
        } else {
          await atualizarListas();
        }
      } catch (err) {
        if (ativo) falhou(err, "Falha ao carregar a rodada");
      }
    };
    void buscar();
    return () => {
      ativo = false;
      if (timer) clearTimeout(timer);
    };
  }, [selecionada, atualizarListas]);

  const rodando = rodadas.some(emAndamento) || emAndamento(detalhe);

  async function iniciar() {
    setErro(null);
    setIniciando(true);
    try {
      const { id } = await api.treinador.iniciar({
        personas: [...personas, ...contextosNaRodada],
        rodadas: qtdRodadas,
        max_turnos: maxTurnos,
        usar_llm: usarLlm,
        gerar_regressao: gerarRegressao,
      });
      setAba("rodada");
      setDetalhe(null);
      setSelecionada(id);
      setRodadas((atual) => [{ id, estado: "iniciando" }, ...atual]);
    } catch (err) {
      falhou(err, "Falha ao iniciar a rodada");
    } finally {
      setIniciando(false);
    }
  }

  function alternarPersona(id: string) {
    setPersonas((atual) => {
      const nova = new Set(atual);
      if (nova.has(id)) nova.delete(id);
      else nova.add(id);
      return nova;
    });
  }

  function alternarContexto(id: string) {
    setContextosSel((atual) => {
      const nova = new Set(atual);
      if (nova.has(id)) nova.delete(id);
      else nova.add(id);
      return nova;
    });
  }

  async function criarContexto(texto: string, nome: string) {
    setErro(null);
    try {
      const novo = await api.treinador.criarContexto(texto, nome);
      setContextos((atual) => [...atual, novo]);
      setContextosSel((atual) => new Set(atual).add(novo.id));
    } catch (err) {
      falhou(err, "Falha ao salvar o contexto");
    }
  }

  async function removerContexto(id: string) {
    setErro(null);
    try {
      await api.treinador.removerContexto(id);
      setContextos((atual) => atual.filter((c) => c.id !== id));
      setContextosSel((atual) => {
        const nova = new Set(atual);
        nova.delete(id);
        return nova;
      });
    } catch (err) {
      falhou(err, "Falha ao remover o contexto");
    }
  }

  const contextosHabilitados = usarLlm && !!config?.llm_disponivel;
  const contextosNaRodada = contextosHabilitados ? [...contextosSel] : [];
  const totalConversas = (personas.size + contextosNaRodada.length) * qtdRodadas;

  return (
    <div className="flex h-full min-h-0 flex-col gap-3 overflow-auto">
      <div className="flex shrink-0 flex-col gap-1 rounded-[1.75rem] border border-white/60 bg-white/85 p-4 shadow-sm backdrop-blur sm:p-5">
        <h1 className="text-xl font-semibold tracking-tight sm:text-2xl">Treinador do agente</h1>
        <p className="text-sm text-slate-500">
          Leads simulados conversam com o agente, um avaliador aponta as falhas e as conversas reprovadas viram testes de
          regressão. Roda isolado: não grava no banco nem envia e-mails ou convites.
        </p>
      </div>

      {erro && (
        <Alert status="danger">
          <Alert.Content>
            <Alert.Title>Erro</Alert.Title>
            <Alert.Description>{erro}</Alert.Description>
          </Alert.Content>
        </Alert>
      )}

      <div className="grid shrink-0 gap-3 lg:min-h-0 lg:flex-1 lg:shrink lg:grid-cols-[380px_1fr]">
        <div className="flex min-w-0 flex-col gap-3 lg:min-h-0 lg:overflow-auto">
          <Card className="shrink-0 rounded-[1.75rem] border border-white/60 bg-white/90 shadow-sm">
            <Card.Header>
              <Card.Title className="text-lg">Nova rodada</Card.Title>
              <Card.Description>
                {!config
                  ? "Carregando…"
                  : config.llm_disponivel
                    ? `Lead simulado e juiz usam ${config.modelo}.`
                    : "Sem chave da OpenAI: usa roteiros fixos e só as verificações automáticas."}
              </Card.Description>
            </Card.Header>
            <Card.Content className="gap-4">
              <div>
                <div className="mb-2 flex items-center justify-between">
                  <span className="text-xs font-semibold uppercase tracking-wide text-slate-500">
                    Personas ({personas.size}/{config?.personas.length ?? 0})
                  </span>
                  <button
                    type="button"
                    className="text-xs font-semibold text-navy hover:underline"
                    onClick={() =>
                      setPersonas(
                        personas.size === config?.personas.length ? new Set() : new Set(config?.personas.map((p) => p.id)),
                      )
                    }
                  >
                    {personas.size === config?.personas.length ? "Limpar" : "Todas"}
                  </button>
                </div>
                <ul className="max-h-64 space-y-1 overflow-auto pr-1">
                  {config?.personas.map((p) => (
                    <li key={p.id}>
                      <label className="flex cursor-pointer items-start gap-2 rounded-xl px-2 py-1.5 hover:bg-slate-50">
                        <input
                          type="checkbox"
                          className="mt-1 accent-[#84cc16]"
                          checked={personas.has(p.id)}
                          onChange={() => alternarPersona(p.id)}
                        />
                        <span className="min-w-0">
                          <span className="block text-sm font-medium text-slate-800">{p.id.replace(/_/g, " ")}</span>
                          <span className="block text-xs text-slate-500">{p.descricao}</span>
                        </span>
                      </label>
                    </li>
                  ))}
                </ul>
              </div>

              <Contextos
                contextos={contextos}
                selecionados={contextosSel}
                habilitado={contextosHabilitados}
                carregando={!config}
                onAlternar={alternarContexto}
                onCriar={criarContexto}
                onRemover={(id) => void removerContexto(id)}
              />

              <div className="grid grid-cols-2 gap-3">
                <Numero label="Conversas por persona" value={qtdRodadas} min={1} max={5} onChange={setQtdRodadas} />
                <Numero label="Máx. de turnos" value={maxTurnos} min={2} max={20} onChange={setMaxTurnos} />
              </div>

              <div className="space-y-3">
                <Toggle
                  checked={usarLlm}
                  onChange={setUsarLlm}
                  disabled={config !== null && !config.llm_disponivel}
                  label="Lead e juiz com IA"
                  hint={
                    usarLlm
                      ? "O lead improvisa e um juiz dá nota a cada conversa."
                      : "Roteiros fixos, sem juiz: rápido e sem custo."
                  }
                />
                <Toggle
                  checked={gerarRegressao}
                  onChange={setGerarRegressao}
                  label="Gerar casos de regressão"
                  hint="Conversas com falha automática viram testes do pytest."
                />
              </div>

              <Button
                variant="primary"
                className="w-full rounded-full bg-lime"
                isDisabled={iniciando || rodando || totalConversas === 0}
                onPress={() => void iniciar()}
              >
                {iniciando ? (
                  <span className="inline-flex items-center gap-2">
                    <Spinner size="sm" color="current" /> Iniciando
                  </span>
                ) : rodando ? (
                  "Rodada em andamento…"
                ) : (
                  `Iniciar rodada · ${totalConversas} conversa${totalConversas === 1 ? "" : "s"}`
                )}
              </Button>
            </Card.Content>
          </Card>

          <Card className="shrink-0 rounded-[1.75rem] border border-white/60 bg-white/90 shadow-sm">
            <Card.Header>
              <Card.Title className="text-lg">Histórico</Card.Title>
            </Card.Header>
            <Card.Content className="gap-1">
              {rodadas.length === 0 ? (
                <p className="py-4 text-center text-sm text-slate-500">Nenhuma rodada ainda.</p>
              ) : (
                <ul className="space-y-1">
                  {rodadas.map((r) => (
                    <li key={r.id}>
                      <button
                        type="button"
                        onClick={() => {
                          setAba("rodada");
                          setSelecionada(r.id);
                        }}
                        className={`flex w-full items-center gap-3 rounded-2xl px-3 py-2 text-left transition hover:bg-slate-50 ${
                          selecionada === r.id ? "bg-slate-100" : ""
                        }`}
                      >
                        <div className="min-w-0 flex-1">
                          <p className="text-sm font-semibold">{quando(r.inicio) !== "—" ? quando(r.inicio) : r.id}</p>
                          <p className="truncate text-xs text-slate-500">
                            {r.parametros
                              ? `${r.parametros.lead === "LLM" ? "IA" : "roteiro"} · ${r.total ?? 0} conversa${r.total === 1 ? "" : "s"}`
                              : "preparando…"}
                          </p>
                        </div>
                        {r.resumo && r.estado !== "rodando" && (
                          <span className="text-xs font-semibold text-slate-600">
                            {r.resumo.aprovadas}/{r.concluidas ?? 0}
                          </span>
                        )}
                        <EstadoChip estado={r.estado} />
                      </button>
                    </li>
                  ))}
                </ul>
              )}
            </Card.Content>
          </Card>
        </div>

        <Card className="min-w-0 rounded-[1.75rem] border border-white/60 bg-white/90 shadow-sm lg:min-h-0 lg:overflow-auto">
          <Card.Header className="flex flex-row flex-wrap items-center justify-between gap-2">
            <nav className="flex items-center gap-1 rounded-full bg-slate-100 p-1" aria-label="Seções">
              {(
                [
                  ["rodada", "Rodada"],
                  ["casos", `Casos de regressão (${casos.length})`],
                ] as const
              ).map(([id, label]) => (
                <button
                  key={id}
                  type="button"
                  onClick={() => setAba(id)}
                  className={`rounded-full px-3 py-1 text-xs font-semibold transition ${
                    aba === id ? "bg-navy text-white" : "text-slate-600 hover:text-slate-900"
                  }`}
                >
                  {label}
                </button>
              ))}
            </nav>
            {aba === "rodada" && detalhe?.estado === "concluida" && (
              <a
                href={api.treinador.relatorioUrl(detalhe.id)}
                target="_blank"
                rel="noreferrer"
                className="text-xs font-semibold text-navy hover:underline"
              >
                Abrir relatório em Markdown
              </a>
            )}
          </Card.Header>
          <Card.Content>
            {aba === "casos" ? (
              <ListaCasos casos={casos} />
            ) : detalhe ? (
              <DetalheRodada key={detalhe.id} rodada={detalhe} />
            ) : selecionada ? (
              <div className="flex items-center justify-center gap-2 py-12 text-slate-500">
                <Spinner size="sm" /> <span className="text-sm">Carregando…</span>
              </div>
            ) : (
              <EmptyState className="py-12 text-center">
                <p className="font-medium">Nenhuma rodada selecionada</p>
                <p className="mt-1 text-sm text-slate-500">Escolha as personas e inicie uma rodada.</p>
              </EmptyState>
            )}
          </Card.Content>
        </Card>
      </div>
    </div>
  );
}
