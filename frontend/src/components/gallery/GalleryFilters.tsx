import Box from "@mui/material/Box";
import Button from "@mui/material/Button";
import Checkbox from "@mui/material/Checkbox";
import FormControlLabel from "@mui/material/FormControlLabel";
import InputAdornment from "@mui/material/InputAdornment";
import Switch from "@mui/material/Switch";
import TextField from "@mui/material/TextField";
import SearchIcon from "@mui/icons-material/Search";
import type { GalleryFacets } from "@/api/gallery";
import PillFilter from "@/components/common/PillFilter";
import CatalogFilter from "@/components/dso/CatalogFilter";
import ConstellationFilter from "@/components/dso/ConstellationFilter";
import type { GalleryFilters as FilterValues } from "@/stores/galleryStore";
import TypeGroupFilter from "./TypeGroupFilter";

interface Props {
  values: FilterValues;
  facets?: GalleryFacets;
  invalidRange: boolean;
  onChange: (patch: Partial<FilterValues>) => void;
  onClear: () => void;
  hasFilters: boolean;
}

const statusNames: Record<string, string> = {
  active: "Active",
  paused: "Paused",
  complete: "Complete",
  abandoned: "Abandoned",
};

export default function GalleryFilters({
  values,
  facets,
  invalidRange,
  onChange,
  onClear,
  hasFilters,
}: Props) {
  const wrapperSx = { flex: "0 1 180px", minWidth: 160 };
  const statusOptions = (facets?.statuses ?? []).map((option) => ({
    code: option.code,
    displayName: statusNames[option.code] ?? option.code,
    count: option.count,
  }));
  const rigOptions = (facets?.rigs ?? []).map((option) => ({
    code: String(option.id),
    displayName: option.name,
    count: option.count,
  }));

  const setDate = (field: "dateFrom" | "dateTo", value: string) => {
    const otherDate = field === "dateFrom" ? values.dateTo : values.dateFrom;
    onChange({
      [field]: value,
      ...(!value && !otherDate ? { includeUndated: false } : {}),
    });
  };

  return (
    <>
      <Box
        sx={{
          display: "flex",
          flexWrap: "wrap",
          alignItems: "center",
          gap: "12px 20px",
          mb: "18px",
        }}
      >
        <TextField
          size="small"
          label="Search"
          value={values.search}
          onChange={(event) => onChange({ search: event.target.value })}
          placeholder="Project, target or object name"
          autoComplete="off"
          slotProps={{
            input: {
              startAdornment: (
                <InputAdornment position="start">
                  <SearchIcon sx={{ fontSize: 18 }} />
                </InputAdornment>
              ),
            },
          }}
          sx={{ flex: "0 1 420px", minWidth: 280 }}
        />
        <FormControlLabel
          control={
            <Checkbox
              checked={values.searchImages}
              onChange={(event) => onChange({ searchImages: event.target.checked })}
            />
          }
          label="Also search plate-solved projects"
        />
      </Box>
      <Box sx={{ display: "flex", flexWrap: "wrap", gap: "12px", mb: "12px" }}>
        <Box sx={wrapperSx}>
          <CatalogFilter
            value={values.catalogs}
            onChange={(catalogs) => onChange({ catalogs })}
            options={facets?.catalogs ?? []}
            placeholder="Any catalog"
          />
        </Box>
        <Box sx={wrapperSx}>
          <TypeGroupFilter
            value={values.typeGroups}
            onChange={(typeGroups) => onChange({ typeGroups })}
            options={facets?.type_groups ?? []}
          />
        </Box>
        <Box sx={wrapperSx}>
          <ConstellationFilter
            value={values.constellations}
            onChange={(constellations) => onChange({ constellations })}
            options={facets?.constellations ?? []}
            placeholder="Any constellation"
          />
        </Box>
        <Box sx={wrapperSx}>
          <PillFilter
            label="Status"
            placeholder="Any status"
            value={values.statuses}
            onChange={(statuses) => onChange({ statuses })}
            options={statusOptions}
          />
        </Box>
        <Box sx={wrapperSx}>
          <PillFilter
            label="Rig"
            placeholder="Any rig"
            value={values.rigs}
            onChange={(rigs) => onChange({ rigs })}
            options={rigOptions}
          />
        </Box>
      </Box>
      <Box
        sx={{
          display: "flex",
          flexWrap: "wrap",
          alignItems: "center",
          gap: "12px",
          mb: "20px",
        }}
      >
        <Box sx={{ color: "text.secondary" }}>Imaged between</Box>
        <TextField
          size="small"
          type="date"
          label="From"
          value={values.dateFrom}
          onChange={(event) => setDate("dateFrom", event.target.value)}
          slotProps={{ inputLabel: { shrink: true } }}
          sx={{ flex: "0 0 170px" }}
        />
        <TextField
          size="small"
          type="date"
          label="To"
          value={values.dateTo}
          onChange={(event) => setDate("dateTo", event.target.value)}
          error={invalidRange}
          helperText={invalidRange ? "To is before From" : " "}
          slotProps={{ inputLabel: { shrink: true } }}
          sx={{ flex: "0 0 170px", mb: "-23px" }}
        />
        {(values.dateFrom || values.dateTo) && (
          <FormControlLabel
            control={
              <Checkbox
                checked={values.includeUndated}
                onChange={(event) =>
                  onChange({ includeUndated: event.target.checked })
                }
              />
            }
            label="Include projects without imaging dates"
          />
        )}
        <FormControlLabel
          control={
            <Switch
              checked={values.includeRetired}
              onChange={(event) => onChange({ includeRetired: event.target.checked })}
            />
          }
          label="Show retired"
        />
        <Button onClick={onClear} disabled={!hasFilters}>
          Clear filters
        </Button>
      </Box>
    </>
  );
}
