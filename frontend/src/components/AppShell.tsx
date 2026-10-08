import { ReactNode } from "react";
import { NavLink, useLocation } from "react-router-dom";

type Props = { children: ReactNode };

function IconChat({ active }: { active?: boolean }) {
  return (
    <svg width="20" height="20" viewBox="0 0 24 24" fill="none" aria-hidden>
      <path
        d="M4 6.5A2.5 2.5 0 0 1 6.5 4h11A2.5 2.5 0 0 1 20 6.5v7A2.5 2.5 0 0 1 17.5 16H9l-4 3.5V6.5Z"
        stroke={active ? "#fff" : "currentColor"}
        strokeWidth="1.8"
        strokeLinejoin="round"
      />
    </svg>
  );
}

function IconDash({ active }: { active?: boolean }) {
  return (
    <svg width="20" height="20" viewBox="0 0 24 24" fill="none" aria-hidden>
      <rect x="4" y="4" width="7" height="7" rx="1.5" stroke={active ? "#fff" : "currentColor"} strokeWidth="1.8" />
      <rect x="13" y="4" width="7" height="7" rx="1.5" stroke={active ? "#fff" : "currentColor"} strokeWidth="1.8" />
      <rect x="4" y="13" width="7" height="7" rx="1.5" stroke={active ? "#fff" : "currentColor"} strokeWidth="1.8" />
      <rect x="13" y="13" width="7" height="7" rx="1.5" stroke={active ? "#fff" : "currentColor"} strokeWidth="1.8" />
    </svg>
  );
}

function IconTreinador({ active }: { active?: boolean }) {
  const cor = active ? "#fff" : "currentColor";
  return (
    <svg width="20" height="20" viewBox="0 0 24 24" fill="none" aria-hidden>
      <path d="M9.5 3.5h5M10.5 3.5v5.2L5.4 17.6A2 2 0 0 0 7.1 20.5h9.8a2 2 0 0 0 1.7-2.9l-5.1-8.9V3.5" stroke={cor} strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" />
      <path d="M7.6 14.5h8.8" stroke={cor} strokeWidth="1.8" strokeLinecap="round" />
    </svg>
  );
}

function TrocaVisao({ isLead }: { isLead: boolean }) {
  const base = "rounded-full px-3 py-1 text-xs font-semibold transition";
  return (
    <nav className="flex items-center gap-1 rounded-full bg-white/10 p-1" aria-label="Trocar visão">
      <NavLink to="/atendimento" className={`${base} ${isLead ? "bg-lime text-white" : "text-white/75 hover:text-white"}`}>
        Lead
      </NavLink>
      <NavLink to="/" className={`${base} ${!isLead ? "bg-lime text-white" : "text-white/75 hover:text-white"}`}>
        Corretor
      </NavLink>
    </nav>
  );
}

export function AppShell({ children }: Props) {
  const { pathname } = useLocation();
  const isLead = pathname.startsWith("/atendimento");
  const isChat = pathname === "/";
  const isDash = pathname.startsWith("/dashboard");
  const isTreinador = pathname.startsWith("/treinador");

  return (
    <div className="flex h-full min-h-0 flex-col">
      <header className="flex shrink-0 items-center justify-between gap-3 bg-navy px-4 py-3 text-white sm:px-6">
        <div className="flex items-center gap-3">
          <div className="flex h-9 w-9 items-center justify-center rounded-xl bg-lime text-sm font-bold text-white shadow-sm">
            AI
          </div>
          <div>
            <p className="text-sm font-semibold tracking-tight sm:text-base">
              Plataforma de Leads com IA
            </p>
            <p className="hidden text-xs text-white/55 sm:block">
              {isLead ? "Visão do lead · site da imobiliária" : "SDR Imobiliário · POC Fase 5"}
            </p>
          </div>
        </div>
        <div className="flex items-center gap-2">
          <TrocaVisao isLead={isLead} />
          {!isLead && (
            <div className="flex h-9 w-9 items-center justify-center rounded-full bg-white/15 text-xs font-semibold">
              TM
            </div>
          )}
        </div>
      </header>

      <div className="mx-auto flex min-h-0 w-full max-w-[1400px] flex-1 gap-3 p-3 sm:p-4">
        <aside
          className={`${isLead ? "hidden" : "hidden md:flex"} w-16 shrink-0 flex-col items-center gap-2 rounded-[1.5rem] border border-white/50 bg-white/70 py-4 shadow-sm backdrop-blur`}
        >
          <NavLink
            to="/"
            className={`flex h-11 w-11 items-center justify-center rounded-2xl transition ${
              isChat ? "bg-navy text-white shadow" : "text-slate-600 hover:bg-slate-100"
            }`}
            title="Mensagens"
          >
            <IconChat active={isChat} />
          </NavLink>
          <NavLink
            to="/dashboard"
            className={`flex h-11 w-11 items-center justify-center rounded-2xl transition ${
              isDash ? "bg-navy text-white shadow" : "text-slate-600 hover:bg-slate-100"
            }`}
            title="Painel"
          >
            <IconDash active={isDash} />
          </NavLink>
          <NavLink
            to="/treinador"
            className={`mt-auto flex h-11 w-11 items-center justify-center rounded-2xl transition ${
              isTreinador ? "bg-navy text-white shadow" : "text-slate-600 hover:bg-slate-100"
            }`}
            title="Treinador do agente"
          >
            <IconTreinador active={isTreinador} />
          </NavLink>
        </aside>

        <div className="min-h-0 min-w-0 flex-1">{children}</div>
      </div>
    </div>
  );
}
