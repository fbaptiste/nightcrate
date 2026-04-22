/**
 * Grouped <MenuItem> factory for the horizon selector.
 *
 * The Target Planner renders a horizon Select in two places — the
 * header filter bar (``PlannerPage``) and the detail panel's preview
 * header (``PlannerDetailPanel``). Both show Custom and Artificial
 * groups under labelled ``ListSubheader`` rows. The grouping logic is
 * the only real duplication; the outer ``<Select>`` keeps its own
 * props (label, variant, size, fontSize) because the two locations
 * present the control differently.
 *
 * Usage:
 *
 *     <Select ...>
 *       {renderHorizonMenuItems(horizons)}
 *     </Select>
 */
import ListSubheader from "@mui/material/ListSubheader";
import MenuItem from "@mui/material/MenuItem";
import type { ReactNode } from "react";
import type { Horizon } from "@/api/horizons";

export function renderHorizonMenuItems(horizons: Horizon[]): ReactNode[] {
  const nodes: ReactNode[] = [];
  const byType = (type: Horizon["type"], header: string, key: string) => {
    const matches = horizons.filter((h) => h.type === type);
    if (matches.length === 0) return;
    nodes.push(<ListSubheader key={key}>{header}</ListSubheader>);
    for (const h of matches) {
      nodes.push(
        <MenuItem key={h.id} value={h.id}>
          {h.name}
        </MenuItem>,
      );
    }
  };
  byType("custom", "Custom", "custom-header");
  byType("artificial", "Artificial", "artificial-header");
  return nodes;
}
