import { Chip } from "@heroui/react";
import type { ResumoCorretor as Resumo } from "../api";
import { AgendamentoCard } from "./AgendamentoCard";
import { PriorityChip } from "./PriorityChip";

/**
 * Resumo inteligente para o corretor (human-in-the-loop).
 * Mostra, em 30 segundos de leitura: prioridade e por quê, sinopse,
 * objeções, pontos de atenção, perfil e próximo passo.
 */

const ROTULOS: Record<string, string> = {
  intencao: "Intenção",
  regiao: "Região",
  quartos: "Quartos",
  faixa_preco: "Orçamento",
  ticket: "Ticket de investimento",
  urgencia: "Urgência",
  retorno_esperado: "Retorno esperado",
  perfil: "Perfil de investidor",
  email: "E-mail",
};

const STATUS_AGENDAMENTO: Record<string, string> = {
  remarcado: "remarcado",
  cancelado: "cancelado",
};

const NOMES_CRITERIOS: Record<string, string> = {
  necessidade: "Necessidade",
  detalhamento: "Detalhamento",
  orcamento: "Orçamento",
  prazo: "Prazo",
  engajamento: "Engajamento",
};

function formatarValor(campo: string, valor: unknown): string {
  if ((campo === "faixa_preco" || campo === "ticket") && typeof valor === "number") {
    return valor.toLocaleString("pt-BR", { style: "currency", currency: "BRL", maximumFractionDigits: 0 });
  }
  return String(valor);
}

function Secao({ titulo, children }: { titulo: string; children: React.ReactNode }) {
  return (
    <section className="space-y-2">
      <h3 className="text-xs font-semibold uppercase tracking-wide text-slate-500">{titulo}</h3>
      {children}
    </section>
  );
}

export function ResumoCorretor({ resumo }: { resumo: Resumo }) {
  const q = resumo.qualificacao || ({} as Resumo["qualificacao"]);
  const perfil = resumo.perfil || {};
  const campos = Object.keys(ROTULOS).filter((c) => perfil[c] !== undefined && perfil[c] !== null && perfil[c] !== "");
  // investidor: orçamento e ticket costumam ser o mesmo valor
  const camposVisiveis =
    campos.includes("ticket") && campos.includes("faixa_preco") && perfil.ticket === perfil.faixa_preco
      ? campos.filter((c) => c !== "faixa_preco")
      : campos;
  const limitada = (q.justificativa || "").includes("Prioridade limitada");
  const objecoes = resumo.objecoes || [];
  const pontos = resumo.pontos_atencao || [];
  const imoveis = resumo.imoveis_sugeridos || [];
  const agendamentos = resumo.agendamentos || [];
  const ativos = agendamentos.filter((a) => a.status === "agendado");
  const historico = agendamentos.filter((a) => a.status !== "agendado");

  return (
    <div className="space-y-5">
      {/* Cabeçalho: prioridade, score, encaminhamento */}
      <div className="flex flex-wrap items-center gap-2">
        <PriorityChip prioridade={q.prioridade} />
        <span className="text-sm font-semibold text-slate-700">score {q.score}/100</span>
        {resumo.encaminhamento && (
          <Chip size="sm" variant="soft">
            <Chip.Label>→ {resumo.encaminhamento}</Chip.Label>
          </Chip>
        )}
        {q.pronto_para_agendar && (
          <Chip size="sm" variant="soft" color="success">
            <Chip.Label>pronto para agendar</Chip.Label>
          </Chip>
        )}
        <span className="ml-auto text-[11px] text-slate-400">
          gerado por {resumo.gerado_por === "llm" ? "IA" : "regras"}
        </span>
      </div>

      {/* Próximo passo */}
      <div className="rounded-2xl bg-navy px-4 py-3 text-white">
        <p className="text-xs uppercase tracking-wide text-white/60">Ação sugerida</p>
        <p className="mt-1 text-sm font-medium">{resumo.acao_sugerida || "—"}</p>
      </div>

      {resumo.sinopse && (
        <Secao titulo="Sinopse">
          <p className="text-sm leading-relaxed text-slate-700">{resumo.sinopse}</p>
        </Secao>
      )}

      {/* Por que essa prioridade */}
      {q.criterios && q.criterios.length > 0 && (
        <Secao titulo="Por que essa prioridade">
          <ul className="space-y-2.5">
            {q.criterios.map((c) => {
              const pct = c.maximo ? Math.round((100 * c.pontos) / c.maximo) : 0;
              return (
                <li key={c.criterio}>
                  <div className="flex items-baseline justify-between text-sm">
                    <span className="font-medium text-slate-700">
                      {NOMES_CRITERIOS[c.criterio] || c.criterio}
                    </span>
                    <span className="tabular-nums text-slate-500">
                      {c.pontos}/{c.maximo}
                    </span>
                  </div>
                  <div
                    className="mt-1 h-1.5 overflow-hidden rounded-full bg-slate-100"
                    role="progressbar"
                    aria-valuenow={c.pontos}
                    aria-valuemax={c.maximo}
                    aria-label={NOMES_CRITERIOS[c.criterio] || c.criterio}
                  >
                    <div
                      className={`h-full rounded-full ${pct === 100 ? "bg-emerald-500" : pct === 0 ? "bg-slate-300" : "bg-sky-400"}`}
                      style={{ width: `${Math.max(pct, 2)}%` }}
                    />
                  </div>
                  <p className="mt-0.5 text-xs text-slate-500">{c.motivo}</p>
                </li>
              );
            })}
          </ul>
          {limitada && (
            <p className="rounded-xl bg-amber-50 px-3 py-2 text-xs text-amber-800">
              Prioridade limitada a morno: lead quente exige orçamento informado.
            </p>
          )}
        </Secao>
      )}

      <Secao titulo="Objeções do cliente">
        {objecoes.length ? (
          <div className="flex flex-wrap gap-1.5">
            {objecoes.map((o) => (
              <Chip key={o} size="sm" variant="soft" color="warning">
                <Chip.Label>{o}</Chip.Label>
              </Chip>
            ))}
          </div>
        ) : (
          <p className="text-sm text-slate-500">Nenhuma identificada</p>
        )}
      </Secao>

      <Secao titulo="Pontos de atenção">
        {pontos.length ? (
          <ul className="list-disc space-y-1 pl-5 text-sm text-slate-700">
            {pontos.map((p) => (
              <li key={p}>{p}</li>
            ))}
          </ul>
        ) : (
          <p className="text-sm text-slate-500">Nenhum</p>
        )}
      </Secao>

      <Secao titulo="Perfil">
        {camposVisiveis.length ? (
          <dl className="grid grid-cols-[auto_1fr] gap-x-4 gap-y-1 text-sm">
            {camposVisiveis.map((c) => (
              <div key={c} className="contents">
                <dt className="text-slate-500">{ROTULOS[c]}</dt>
                <dd className="font-medium text-slate-800">{formatarValor(c, perfil[c])}</dd>
              </div>
            ))}
          </dl>
        ) : (
          <p className="text-sm text-slate-500">Sem dados ainda</p>
        )}
      </Secao>

      {imoveis.length > 0 && (
        <Secao titulo={`Imóveis sugeridos (${imoveis.length})`}>
          <p className="text-sm text-slate-700">{imoveis.join(", ")}</p>
        </Secao>
      )}

      {agendamentos.length > 0 && (
        <Secao titulo="Agendamentos">
          <div className="space-y-2">
            {ativos.map((a) => (
              <AgendamentoCard key={a.indice} agendamento={a} compacto />
            ))}
            {historico.length > 0 && (
              <ul className="space-y-0.5 text-xs text-slate-500">
                {historico.map((a) => (
                  <li key={a.indice} className="line-through decoration-slate-300">
                    {a.quando} · {STATUS_AGENDAMENTO[a.status] || a.status}
                  </li>
                ))}
              </ul>
            )}
          </div>
        </Secao>
      )}
    </div>
  );
}
