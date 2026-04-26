import { useCallback } from "react";
import Box from "@mui/material/Box";
import Chip from "@mui/material/Chip";
import Slider from "@mui/material/Slider";
import Stack from "@mui/material/Stack";
import Typography from "@mui/material/Typography";

import type { AnnotatedDso } from "@/api/plateSolve";

const TYPE_GROUPS = [
  "Galaxy",
  "Open Cluster",
  "Globular Cluster",
  "Emission Nebula",
  "Reflection Nebula",
  "Planetary Nebula",
  "Dark Nebula",
  "Supernova Remnant",
  "Other",
] as const;

export interface AnnotationFilters {
  enabledTypes: Set<string>;
  minSizeArcmin: number;
}

export const DEFAULT_FILTERS: AnnotationFilters = {
  enabledTypes: new Set(TYPE_GROUPS),
  minSizeArcmin: 0,
};

export function applyFilters(dsos: AnnotatedDso[], filters: AnnotationFilters): AnnotatedDso[] {
  return dsos.filter((d) => {
    if (!filters.enabledTypes.has(d.type_group)) return false;
    if (filters.minSizeArcmin > 0 && (d.maj_axis_arcmin == null || d.maj_axis_arcmin < filters.minSizeArcmin)) {
      return false;
    }
    return true;
  });
}

interface Props {
  filters: AnnotationFilters;
  onChange: (filters: AnnotationFilters) => void;
  typeCounts: Map<string, number>;
}

export function PlateSolveFilters({ filters, onChange, typeCounts }: Props) {
  const toggleType = useCallback(
    (type: string) => {
      const next = new Set(filters.enabledTypes);
      if (next.has(type)) next.delete(type);
      else next.add(type);
      onChange({ ...filters, enabledTypes: next });
    },
    [filters, onChange],
  );

  return (
    <Box sx={{ display: "flex", alignItems: "center", gap: 2, px: 1.5, py: 0.75, borderTop: 1, borderColor: "divider", flexShrink: 0 }}>
      <Stack direction="row" spacing={0.5} flexWrap="wrap" useFlexGap sx={{ flex: 1 }}>
        {TYPE_GROUPS.map((tg) => {
          const count = typeCounts.get(tg) ?? 0;
          if (count === 0) return null;
          const active = filters.enabledTypes.has(tg);
          return (
            <Chip
              key={tg}
              label={`${tg} (${count})`}
              size="small"
              variant={active ? "filled" : "outlined"}
              color={active ? "primary" : "default"}
              onClick={() => toggleType(tg)}
              sx={{ fontSize: "0.65rem" }}
            />
          );
        })}
      </Stack>

      <Box sx={{ display: "flex", alignItems: "center", gap: 1, minWidth: 180 }}>
        <Typography variant="caption" color="text.secondary" sx={{ whiteSpace: "nowrap" }}>
          Min size
        </Typography>
        <Slider
          size="small"
          value={filters.minSizeArcmin}
          min={0}
          max={30}
          step={1}
          onChange={(_, v) => onChange({ ...filters, minSizeArcmin: v as number })}
          valueLabelDisplay="auto"
          valueLabelFormat={(v) => `${v}′`}
          sx={{ width: 120 }}
        />
      </Box>
    </Box>
  );
}
