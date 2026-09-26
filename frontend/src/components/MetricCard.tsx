import { Card } from "@heroui/react";
import type { ReactNode } from "react";

type Props = {
  label: string;
  value: ReactNode;
  hint?: string;
  tone?: "default" | "quente" | "morno" | "frio";
};

const toneClass: Record<NonNullable<Props["tone"]>, string> = {
  default: "text-slate-900",
  quente: "text-red-600",
  morno: "text-amber-600",
  frio: "text-slate-500",
};

export function MetricCard({ label, value, hint, tone = "default" }: Props) {
  return (
    <Card className="rounded-2xl border border-white/70 bg-white/90 shadow-sm">
      <Card.Content className="gap-1 py-4">
        <p className="text-[11px] font-semibold uppercase tracking-wide text-slate-500">{label}</p>
        <p className={`text-3xl font-bold leading-none ${toneClass[tone]}`}>{value}</p>
        {hint ? <p className="text-xs text-slate-400">{hint}</p> : null}
      </Card.Content>
    </Card>
  );
}
