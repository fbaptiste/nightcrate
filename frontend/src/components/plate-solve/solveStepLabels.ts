import type { SolveStep } from "@/api/plateSolve";

const labels: Record<SolveStep, string> = {
  load: "Load image and detect stars",
  near_index: "Search near the supplied position",
  near_catalog: "Match catalog stars near the supplied position",
  blind_known_scale: "Search the whole sky at the supplied scale",
  blind_unknown_scale: "Search the whole sky at every scale",
  astap_near: "ASTAP search near the supplied position",
  astap_blind: "ASTAP search of the whole sky",
};

export function stepLabel(step: SolveStep): string {
  return labels[step];
}
