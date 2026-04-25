import Box from "@mui/material/Box";
import Typography from "@mui/material/Typography";
import { SimpleTreeView } from "@mui/x-tree-view/SimpleTreeView";
import { TreeItem } from "@mui/x-tree-view/TreeItem";

// Keep a single source of truth for calculator IDs + labels + grouping.
// Each calcId corresponds to a URL segment (/calculators/:calcId) and to a
// component in pages/Calculators/calculators/.

export interface CalcGroup {
  id: string;
  label: string;
  items: Array<{ id: string; label: string; aware?: boolean }>;
}

export const CALCULATOR_GROUPS: CalcGroup[] = [
  {
    id: "group-coords",
    label: "Coordinates & Time",
    items: [
      { id: "tonight", label: "Tonight at a Glance", aware: true },
      { id: "lat-long", label: "Lat/Long Converter" },
      { id: "radec-altaz", label: "RA/Dec \u2194 Alt/Az", aware: true },
      { id: "clocks", label: "Clocks", aware: true },
    ],
  },
  {
    id: "group-angles",
    label: "Angles & Distances",
    items: [
      { id: "angular-units", label: "Angular Units" },
      { id: "linear-units", label: "Linear Units" },
    ],
  },
  {
    id: "group-imaging",
    label: "Imaging Math",
    items: [
      { id: "pixel-scale", label: "Pixel Scale" },
      { id: "fov", label: "Field of View" },
      { id: "file-size", label: "File Size" },
      { id: "airmass", label: "Airmass" },
    ],
  },
  {
    id: "group-sky",
    label: "Sky Conditions",
    items: [
      { id: "sqm-bortle", label: "SQM / Bortle / NELM" },
      { id: "temperature", label: "Temperature" },
    ],
  },
];

export const ALL_CALC_IDS = CALCULATOR_GROUPS.flatMap((g) =>
  g.items.map((i) => i.id),
);

export function isLocationAware(calcId: string): boolean {
  for (const g of CALCULATOR_GROUPS) {
    for (const i of g.items) {
      if (i.id === calcId) return Boolean(i.aware);
    }
  }
  return false;
}

export default function CalculatorSidebar({
  selected,
  onSelect,
}: {
  selected: string;
  onSelect: (id: string) => void;
}) {
  return (
    <Box
      sx={{
        width: 260,
        flexShrink: 0,
        borderRight: 1,
        borderColor: "divider",
        p: 1,
        overflowY: "auto",
      }}
    >
      <SimpleTreeView
        defaultExpandedItems={CALCULATOR_GROUPS.map((g) => g.id)}
        selectedItems={selected}
        onSelectedItemsChange={(_event, itemId) => {
          if (
            typeof itemId === "string" &&
            !itemId.startsWith("group-") &&
            itemId !== ""
          ) {
            onSelect(itemId);
          }
        }}
      >
        {CALCULATOR_GROUPS.map((g) => (
          <TreeItem
            key={g.id}
            itemId={g.id}
            label={
              <Typography
                variant="caption"
                fontWeight={700}
                sx={{
                  textTransform: "uppercase",
                  letterSpacing: 0.8,
                  color: "text.secondary",
                }}
              >
                {g.label}
              </Typography>
            }
          >
            {g.items.map((i) => (
              <TreeItem key={i.id} itemId={i.id} label={i.label} />
            ))}
          </TreeItem>
        ))}
      </SimpleTreeView>
    </Box>
  );
}
