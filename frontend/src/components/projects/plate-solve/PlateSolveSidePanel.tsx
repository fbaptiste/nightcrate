import { useEffect, useRef } from "react";
import Box from "@mui/material/Box";
import Button from "@mui/material/Button";
import Checkbox from "@mui/material/Checkbox";
import FormControlLabel from "@mui/material/FormControlLabel";
import Slider from "@mui/material/Slider";
import Typography from "@mui/material/Typography";

import { displayCatalogName } from "@/lib/catalogNames";
import { DSO_TYPE_DISPLAY } from "@/lib/dsoTypeNames";
import {
  sizeToSlider,
  sliderToSize,
  type FacetCounts,
  type PlateSolveFilters,
} from "@/lib/plateSolveObjects";

interface Props {
  collapsed: boolean;
  onCollapsedChange: (collapsed: boolean) => void;
  activeCount: number;
  filters: PlateSolveFilters;
  facets: FacetCounts;
  catalogs: string[];
  types: string[];
  maxSizeArcmin: number;
  onToggleCatalog: (catalog: string) => void;
  onToggleType: (type: string) => void;
  onMinimumSizeChange: (size: number) => void;
  onClear: () => void;
}

function formatSize(value: number): string {
  if (value < 0.1) return `${value.toFixed(2)}′`;
  if (value < 10) return `${value.toFixed(1)}′`;
  return `${Math.round(value)}′`;
}

function sliderMarks(maxSizeArcmin: number): { value: number; label: string }[] {
  if (maxSizeArcmin <= 0) return [{ value: 0, label: "Any" }];
  const sizes = [1, 10, maxSizeArcmin]
    .filter((value) => value <= maxSizeArcmin)
    .filter((value, index, values) => index === values.findIndex((other) => Math.abs(other - value) < 0.001));
  return [
    { value: 0, label: "Any" },
    ...sizes.map((size) => ({ value: sizeToSlider(size, maxSizeArcmin), label: formatSize(size) })),
  ];
}

export default function PlateSolveSidePanel({
  collapsed,
  onCollapsedChange,
  activeCount,
  filters,
  facets,
  catalogs,
  types,
  maxSizeArcmin,
  onToggleCatalog,
  onToggleType,
  onMinimumSizeChange,
  onClear,
}: Props) {
  const previousCollapsed = useRef(collapsed);
  const collapseButtonRef = useRef<HTMLButtonElement | null>(null);
  const stripButtonRef = useRef<HTMLButtonElement | null>(null);
  useEffect(() => {
    if (previousCollapsed.current === collapsed) return;
    previousCollapsed.current = collapsed;
    if (collapsed) stripButtonRef.current?.focus();
    else collapseButtonRef.current?.focus();
  }, [collapsed]);

  if (collapsed) {
    return (
      <Button
        ref={stripButtonRef}
        aria-expanded={false}
        aria-label={`Open filters${activeCount ? `, ${activeCount} active` : ""}`}
        onClick={() => onCollapsedChange(false)}
        sx={{
          width: 44,
          minWidth: 44,
          height: "100%",
          minHeight: 200,
          p: 0,
          border: 1,
          borderColor: "divider",
          color: "text.secondary",
          display: "flex",
          flexDirection: "column",
          justifyContent: "flex-start",
          gap: 1,
        }}
      >
        <Box component="span" sx={{ mt: 1 }}>›</Box>
        <Box component="span" sx={{ writingMode: "vertical-rl", transform: "rotate(180deg)", textTransform: "none", fontSize: 12 }}>
          Filters{activeCount ? ` (${activeCount})` : ""}
        </Box>
      </Button>
    );
  }

  const sliderValue = sizeToSlider(filters.minSizeArcmin, maxSizeArcmin);
  return (
    <Box sx={{ width: 220, minWidth: 220, height: "100%", minHeight: 0, overflowY: "auto", pr: 0.5 }}>
      <Box sx={{ display: "flex", alignItems: "center", mb: 1 }}>
        <Typography color="text.secondary" sx={{ fontSize: 13 }}>Filters</Typography>
        <Button onClick={onClear} disabled={activeCount === 0} sx={{ ml: "auto", minWidth: 0, px: 0.5, fontSize: 12 }}>
          Clear
        </Button>
        <Button
          ref={collapseButtonRef}
          aria-expanded={true}
          aria-label="Collapse filters"
          onClick={() => onCollapsedChange(true)}
          sx={{ ml: 0.5, minWidth: 32, width: 32, height: 32, color: "text.secondary" }}
        >
          «
        </Button>
      </Box>
      <Box sx={{ display: "grid", gap: 1.5 }}>
        <Box sx={{ border: 1, borderColor: "divider", borderRadius: "8px", overflow: "hidden" }}>
          <Box sx={{ p: 1.5, display: "grid", gap: 1.5 }}>
            <Box>
              <Typography color="text.secondary" sx={{ mb: 0.5, fontSize: 11.5, fontWeight: 600 }}>Catalogs</Typography>
              {catalogs.map((catalog) => (
                <Box key={catalog} sx={{ minHeight: 24, display: "grid", gridTemplateColumns: "1fr auto", alignItems: "center" }}>
                  <FormControlLabel
                    control={<Checkbox size="small" checked={filters.catalogs.has(catalog)} onChange={() => onToggleCatalog(catalog)} sx={{ p: "2px", mr: "4px", "& .MuiSvgIcon-root": { fontSize: 18 } }} />}
                    label={displayCatalogName(catalog)}
                    sx={{ m: 0, minWidth: 0, height: 24, "& .MuiFormControlLabel-label": { fontSize: 12 } }}
                  />
                  <Typography color="text.secondary" sx={{ fontSize: 11.5, fontVariantNumeric: "tabular-nums" }}>{facets.catalogs.get(catalog) ?? 0}</Typography>
                </Box>
              ))}
            </Box>
            <Box>
              <Typography color="text.secondary" sx={{ mb: 0.5, fontSize: 11.5, fontWeight: 600 }}>Types</Typography>
              {types.map((type) => (
                <Box key={type} sx={{ minHeight: 24, display: "grid", gridTemplateColumns: "1fr auto", alignItems: "center" }}>
                  <FormControlLabel
                    control={<Checkbox size="small" checked={filters.types.has(type)} onChange={() => onToggleType(type)} sx={{ p: "2px", mr: "4px", "& .MuiSvgIcon-root": { fontSize: 18 } }} />}
                    label={DSO_TYPE_DISPLAY[type] ?? type}
                    sx={{ m: 0, minWidth: 0, height: 24, "& .MuiFormControlLabel-label": { fontSize: 12 } }}
                  />
                  <Typography color="text.secondary" sx={{ fontSize: 11.5, fontVariantNumeric: "tabular-nums" }}>{facets.types.get(type) ?? 0}</Typography>
                </Box>
              ))}
            </Box>
            <Box>
              <Typography sx={{ fontSize: 11.5, fontWeight: 600 }}>
                Minimum size&nbsp;&nbsp;
                <Box component="span" sx={{ fontWeight: 400 }}>
                  {filters.minSizeArcmin > 0 ? `${formatSize(filters.minSizeArcmin)} or larger` : "Any size"}
                </Box>
              </Typography>
              <Slider
                size="small"
                min={0}
                max={100}
                value={sliderValue}
                disabled={maxSizeArcmin <= 0}
                onChange={(_, value) => onMinimumSizeChange(sliderToSize(value as number, maxSizeArcmin))}
                valueLabelDisplay="off"
                marks={sliderMarks(maxSizeArcmin)}
                getAriaValueText={() => filters.minSizeArcmin > 0 ? `${formatSize(filters.minSizeArcmin)} or larger` : "Any size"}
                aria-label="Minimum object size"
              />
              <Typography color="text.secondary" sx={{ mt: -0.75, fontSize: 10.5 }}>Main targets always show.</Typography>
            </Box>
          </Box>
        </Box>
      </Box>
    </Box>
  );
}
