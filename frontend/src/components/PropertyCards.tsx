type Imovel = Record<string, unknown>;

type Props = {
  imoveis: Imovel[];
  matchBusca?: string;
};

function money(v: unknown, moeda = "USD") {
  const n = Number(v);
  if (!Number.isFinite(n)) return "—";
  return `${moeda} ${n.toLocaleString("pt-BR", { maximumFractionDigits: 0 })}`;
}

export function PropertyCards({ imoveis, matchBusca }: Props) {
  if (!imoveis.length) return null;
  const aproximado = matchBusca === "aproximado";
  return (
    <div className="mt-2 space-y-2">
      <p className="px-1 text-xs font-semibold uppercase tracking-wide text-slate-500">
        {aproximado ? "Opções próximas" : "Imóveis sugeridos"}
      </p>
      <div className="grid gap-2 sm:grid-cols-3">
        {imoveis.slice(0, 3).map((im) => (
          <div
            key={String(im.id)}
            className="rounded-2xl border border-slate-200 bg-white p-3 shadow-sm"
          >
            <p className="line-clamp-2 text-sm font-semibold text-slate-900">
              {String(im.endereco || im.titulo || im.id)}
            </p>
            <p className="mt-1 text-xs text-slate-500">
              {String(im.cidade || "—")}/{String(im.estado || "—")} · {String(im.quartos ?? "—")}{" "}
              quartos
            </p>
            {aproximado && im.match_motivo ? (
              <p className="mt-1 line-clamp-2 text-[11px] leading-snug text-slate-400">
                {String(im.match_motivo)}
              </p>
            ) : null}
            <p className="mt-2 text-sm font-bold text-lime-dark">
              {money(im.preco, String(im.moeda || "USD"))}
            </p>
          </div>
        ))}
      </div>
    </div>
  );
}
