import { Chip } from "@heroui/react";
import { chipColor, Prioridade } from "../lib/priority";

type Props = {
  prioridade: Prioridade;
  className?: string;
};

export function PriorityChip({ prioridade, className }: Props) {
  return (
    <Chip color={chipColor(prioridade)} variant="soft" size="sm" className={className}>
      <Chip.Label className="capitalize">{prioridade || "—"}</Chip.Label>
    </Chip>
  );
}
