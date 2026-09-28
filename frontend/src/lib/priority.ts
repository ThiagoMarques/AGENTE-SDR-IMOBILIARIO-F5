export type Prioridade = "quente" | "morno" | "frio" | string;

export function chipColor(prioridade: Prioridade): "danger" | "warning" | "default" | "accent" {
  switch ((prioridade || "").toLowerCase()) {
    case "quente":
      return "danger";
    case "morno":
      return "warning";
    case "frio":
      return "default";
    default:
      return "accent";
  }
}
