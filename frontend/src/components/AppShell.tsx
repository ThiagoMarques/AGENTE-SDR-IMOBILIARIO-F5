import { Button } from "@heroui/react";
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

export function AppShell({ children }: Props) {
  const { pathname } = useLocation();
  const isChat = pathname === "/";
  const isDash = pathname.startsWith("/dashboard");

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
            <p className="hidden text-xs text-white/55 sm:block">SDR Imobiliário · POC Fase 5</p>
          </div>
        </div>
        <div className="flex items-center gap-2">
          <span className="hidden rounded-full bg-white/10 px-3 py-1 text-xs text-white/80 sm:inline">
            Modo claro
          </span>
          <Button size="sm" className="rounded-full bg-lime text-white" variant="primary">
            Corretor
          </Button>
          <div className="flex h-9 w-9 items-center justify-center rounded-full bg-white/15 text-xs font-semibold">
            TM
          </div>
        </div>
      </header>

      <div className="mx-auto flex min-h-0 w-full max-w-[1400px] flex-1 gap-3 p-3 sm:p-4">
        <aside className="hidden w-16 shrink-0 flex-col items-center gap-2 rounded-[1.5rem] border border-white/50 bg-white/70 py-4 shadow-sm backdrop-blur md:flex">
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
        </aside>

        <div className="min-h-0 min-w-0 flex-1">{children}</div>
      </div>
    </div>
  );
}
