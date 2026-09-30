import { Chip } from "@heroui/react";
import { apiUrl, type Agendamento } from "../api";

const NOME_PROVEDOR: Record<string, string> = { google: "Google Agenda", outlook: "Outlook" };

function Atalho({ href, children, download }: { href: string; children: React.ReactNode; download?: boolean }) {
  return (
    <a
      href={href}
      target={download ? undefined : "_blank"}
      rel="noreferrer"
      download={download || undefined}
      className="inline-flex items-center justify-center rounded-full border border-slate-200 bg-white px-3 py-1.5 text-xs font-semibold text-slate-800 transition hover:border-slate-300 hover:bg-slate-50"
    >
      {children}
    </a>
  );
}

/** Visita marcada + atalhos "adicionar à agenda" (Google, Outlook, .ics). */
export function AgendamentoCard({ agendamento, compacto = false }: { agendamento: Agendamento; compacto?: boolean }) {
  const ag = agendamento;
  const titulo = ag.tipo === "visita" ? "Visita marcada" : "Conversa marcada";
  const naAgenda = ag.calendarios.filter((c) => c.status === "criado");

  return (
    <div className={`rounded-[1.5rem] border border-lime/40 bg-white ${compacto ? "p-3" : "p-4"} shadow-sm`}>
      <div className="flex flex-wrap items-center gap-2">
        <span className="inline-block h-2 w-2 rounded-full bg-lime" />
        <p className="text-sm font-semibold text-slate-900">{titulo}</p>
        <span className="text-sm text-slate-700">{ag.quando}</span>
      </div>
      {ag.imovel_titulo && <p className="mt-1 text-xs text-slate-600">{ag.imovel_titulo}</p>}
      {ag.local && <p className="text-xs text-slate-500">{ag.local}</p>}

      <div className="mt-3 flex flex-wrap gap-2">
        <Atalho href={ag.links.google}>Google Agenda</Atalho>
        <Atalho href={ag.links.outlook}>Outlook</Atalho>
        <Atalho href={ag.links.outlook_365}>Microsoft 365</Atalho>
        <Atalho href={apiUrl(ag.links.ics)} download>
          Baixar .ics
        </Atalho>
      </div>

      {(naAgenda.length > 0 || ag.convidados.length > 0) && (
        <div className="mt-3 flex flex-wrap items-center gap-1.5 text-[11px] text-slate-500">
          {naAgenda.map((c) => (
            <Chip key={c.provedor} size="sm" variant="soft" color="success">
              <Chip.Label>
                {c.link ? (
                  <a href={c.link} target="_blank" rel="noreferrer" className="underline-offset-2 hover:underline">
                    na agenda do corretor · {NOME_PROVEDOR[c.provedor] || c.provedor}
                  </a>
                ) : (
                  <>na agenda do corretor · {NOME_PROVEDOR[c.provedor] || c.provedor}</>
                )}
              </Chip.Label>
            </Chip>
          ))}
          {ag.convidados.length > 0 && <span>convite para {ag.convidados.join(", ")}</span>}
        </div>
      )}
    </div>
  );
}
