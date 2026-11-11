import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import Autocomplete from "@mui/material/Autocomplete";
import Box from "@mui/material/Box";
import Button from "@mui/material/Button";
import Checkbox from "@mui/material/Checkbox";
import FormControlLabel from "@mui/material/FormControlLabel";
import InputAdornment from "@mui/material/InputAdornment";
import Switch from "@mui/material/Switch";
import TextField from "@mui/material/TextField";
import SearchIcon from "@mui/icons-material/Search";
import {
  fetchGallerySuggestions,
  type GalleryFacets,
  type GallerySuggestion,
} from "@/api/gallery";
import PillFilter from "@/components/common/PillFilter";
import CatalogFilter from "@/components/dso/CatalogFilter";
import ConstellationFilter from "@/components/dso/ConstellationFilter";
import type { GalleryFilters as FilterValues } from "@/stores/galleryStore";
import TypeGroupFilter from "./TypeGroupFilter";
import { useDebounce } from "@/lib/useDebounce";

interface Props {
  values: FilterValues;
  facets?: GalleryFacets;
  invalidRange: boolean;
  onChange: (patch: Partial<FilterValues>) => void;
  onClear: () => void;
  hasFilters: boolean;
  onSuggestionsOpenChange: (open: boolean) => void;
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
  onSuggestionsOpenChange,
}: Props) {
  const [suggestionsOpen, setSuggestionsOpen] = useState(false);
  const debouncedSuggestionText = useDebounce(values.search.trim(), 300);
  const suggestionQuery = useQuery({
    queryKey: [
      "gallery",
      "suggestions",
      debouncedSuggestionText,
      values.searchImages,
      values.includeRetired,
    ],
    queryFn: () =>
      fetchGallerySuggestions(
        debouncedSuggestionText,
        values.searchImages,
        values.includeRetired,
      ),
    enabled: debouncedSuggestionText.length >= 2,
  });
  const setOpen = (open: boolean) => {
    const next = open && values.search.trim().length >= 2;
    setSuggestionsOpen(next);
    onSuggestionsOpenChange(next);
  };
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
        <Autocomplete<GallerySuggestion, false, false, true>
          freeSolo
          open={suggestionsOpen && values.search.trim().length >= 2}
          onOpen={() => setOpen(true)}
          onClose={() => setOpen(false)}
          value={null}
          inputValue={values.search}
          options={suggestionQuery.data ?? []}
          loading={suggestionQuery.isFetching}
          filterOptions={(options) => options}
          getOptionLabel={(option) =>
            typeof option === "string" ? option : option.designation
          }
          groupBy={(option) =>
            option.project_count > 0 ? "In your pictures" : "Not in your pictures"
          }
          onInputChange={(_event, value, reason) => {
            // The clear button reports "clear"; "reset" follows a pick and
            // is ignored so it can't overwrite the chosen designation.
            if (reason === "clear") {
              onChange({ search: "" });
              setOpen(false);
              return;
            }
            if (reason !== "input") {
              setOpen(false);
              return;
            }
            onChange({ search: value });
            setOpen(value.trim().length >= 2);
          }}
          onChange={(_event, value) => {
            if (typeof value === "string") onChange({ search: value });
            else if (value) onChange({ search: value.designation });
            setOpen(false);
          }}
          renderOption={(props, option) => {
            const typed = values.search.trim();
            const index = option.designation.toLocaleLowerCase().indexOf(
              typed.toLocaleLowerCase(),
            );
            return (
              <Box
                component="li"
                {...props}
                key={option.dso_id}
                sx={{
                  display: "grid !important",
                  gridTemplateColumns: "minmax(0, 1fr) auto",
                  gap: "4px 16px",
                  opacity: option.project_count > 0 ? 1 : 0.58,
                }}
              >
                <Box sx={{ minWidth: 0 }}>
                  <Box sx={{ fontWeight: 600 }}>
                    {index >= 0 ? (
                      <>
                        {option.designation.slice(0, index)}
                        <Box component="strong" sx={{ color: "primary.main", fontWeight: 800 }}>
                          {option.designation.slice(index, index + typed.length)}
                        </Box>
                        {option.designation.slice(index + typed.length)}
                      </>
                    ) : option.designation}
                  </Box>
                  {option.detail && (
                    <Box sx={{ color: "text.secondary", fontSize: 12 }}>
                      {option.detail}
                    </Box>
                  )}
                </Box>
                <Box sx={{ color: "text.secondary", fontSize: 12, whiteSpace: "nowrap" }}>
                  {option.project_count === 0
                    ? "none"
                    : `${option.project_count} ${option.project_count === 1 ? "project" : "projects"}`}
                </Box>
              </Box>
            );
          }}
          renderInput={(params) => (
            <TextField
              {...params}
              size="small"
              label="Search"
              placeholder="Project, target or object name"
              autoComplete="off"
              slotProps={{
                input: {
                  ...params.InputProps,
                  startAdornment: (
                    <>
                      <InputAdornment position="start">
                        <SearchIcon sx={{ fontSize: 18 }} />
                      </InputAdornment>
                      {params.InputProps.startAdornment}
                    </>
                  ),
                },
              }}
            />
          )}
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
        <Button
          onClick={() => {
            setOpen(false);
            onClear();
          }}
          disabled={!hasFilters}
        >
          Clear filters
        </Button>
      </Box>
    </>
  );
}
