/**
 * Target Planner (v0.16.0, Pass A).
 *
 * Location-driven "what's up tonight" list. Optional rig adds a FOV
 * coverage column and the "frames well" filter.
 */
import { useEffect, useRef, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import {
  DataGrid,
  type GridColDef,
  type GridPaginationModel,
  type GridSortModel,
  type GridRowParams,
} from "@mui/x-data-grid";
import Alert from "@mui/material/Alert";
import Box from "@mui/material/Box";
import Checkbox from "@mui/material/Checkbox";
import Chip from "@mui/material/Chip";
import FormControl from "@mui/material/FormControl";
import FormControlLabel from "@mui/material/FormControlLabel";
import IconButton from "@mui/material/IconButton";
import InputAdornment from "@mui/material/InputAdornment";
import InputLabel from "@mui/material/InputLabel";
import MenuItem from "@mui/material/MenuItem";
import Paper from "@mui/material/Paper";
import Select from "@mui/material/Select";
import Slider from "@mui/material/Slider";
import Stack from "@mui/material/Stack";
import TextField from "@mui/material/TextField";
import ToggleButton from "@mui/material/ToggleButton";
import ToggleButtonGroup from "@mui/material/ToggleButtonGroup";
import Tooltip from "@mui/material/Tooltip";
import Typography from "@mui/material/Typography";
import Button from "@mui/material/Button";
import CloseIcon from "@mui/icons-material/Close";
import CloudDownloadOutlinedIcon from "@mui/icons-material/CloudDownloadOutlined";
import PlaceOutlinedIcon from "@mui/icons-material/PlaceOutlined";
import SearchIcon from "@mui/icons-material/Search";
import { Link as RouterLink } from "react-router-dom";
import { fetchLocations } from "@/api/locations";
import { fetchRigs } from "@/api/rigs";
import { fetchDsoFacets } from "@/api/dsos";
import {
  fetchPlannerTargets,
  type PlannerTargetItem,
} from "@/api/planner";
import { useSettingsStore } from "@/stores/settingsStore";
import { usePlannerStore } from "@/stores/plannerStore";
import { useDebounce } from "@/lib/useDebounce";
import { typeGroupStyle } from "@/lib/dsoTypeGroups";
import { displayDsoType, dsoTypeColor } from "@/lib/dsoTypeNames";
import { displayConstellation } from "@/lib/constellations";
import ThumbnailCell from "@/components/planner/ThumbnailCell";
import PlannerDetailPanel from "@/components/planner/PlannerDetailPanel";

const DEFAULT_PAGE_SIZE = 100;


function formatLocalTime(iso: string, tz: string): string {
  try {
    return new Date(iso).toLocaleTimeString([], {
      hour: "2-digit",
      minute: "2-digit",
      timeZone: tz,
    });
  } catch {
    return "—";
  }
}


export default function PlannerPage() {
  const settings = useSettingsStore((s) => s.settings);
  const locationId = usePlannerStore((s) => s.selectedLocationId);
  const setLocationId = usePlannerStore((s) => s.setSelectedLocationId);
  const rigId = usePlannerStore((s) => s.selectedRigId);
  const setRigId = usePlannerStore((s) => s.setSelectedRigId);
  const [searchQuery, setSearchQuery] = useState("");
  const [restrictTonight, setRestrictTonight] = useState<boolean>(true);
  const [typeGroupFilter, setTypeGroupFilter] = useState<string[]>([]);
  const [typeFilter, setTypeFilter] = useState<string[]>([]);
  const [constellation, setConstellation] = useState<string>("");
  const [hasDistance, setHasDistance] = useState(false);
  const [advancedOpen, setAdvancedOpen] = useState(false);
  const [minHours, setMinHours] = useState<number>(
    settings?.planner_min_visibility_hours ?? 2.0,
  );
  const [maxMag, setMaxMag] = useState<number>(settings?.planner_max_magnitude ?? 12.0);
  const [minSize, setMinSize] = useState<number>(settings?.planner_min_size_arcmin ?? 5.0);
  const [framesWell, setFramesWell] = useState(false);
  const [pagination, setPagination] = useState<GridPaginationModel>({
    page: 0,
    pageSize: DEFAULT_PAGE_SIZE,
  });
  const [sortModel, setSortModel] = useState<GridSortModel>([
    { field: "hours_visible", sort: "desc" },
  ]);
  // Track whether the current sort is still "auto" (the mode's
  // default) vs. user-chosen. On mode toggle we swap to the new
  // mode's default only while the sort is still auto, so a user
  // who explicitly sorted by e.g. magnitude keeps their choice.
  const sortIsAutoRef = useRef(true);
  const [detailId, setDetailId] = useState<number | null>(null);

  const locationsQuery = useQuery({
    queryKey: ["locations"],
    queryFn: fetchLocations,
    staleTime: 5 * 60_000,
  });
  const rigsQuery = useQuery({
    queryKey: ["rigs"],
    queryFn: () => fetchRigs(true),
    staleTime: 5 * 60_000,
  });
  const facetsQuery = useQuery({
    queryKey: ["dso-facets"],
    queryFn: fetchDsoFacets,
    staleTime: 5 * 60_000,
  });

  // Location: auto-select the default when nothing is stored, and drop
  // a stored id that no longer resolves (location deleted while we
  // were away).
  useEffect(() => {
    const locs = locationsQuery.data;
    if (!locs || locs.length === 0) return;
    if (locationId != null && !locs.some((l) => l.id === locationId)) {
      const def = locs.find((l) => l.is_default) ?? locs[0];
      setLocationId(def.id);
      return;
    }
    if (locationId == null) {
      const def = locs.find((l) => l.is_default) ?? locs[0];
      setLocationId(def.id);
    }
  }, [locationId, locationsQuery.data, setLocationId]);

  // Reset sort to the mode's default on toggle, but only while the
  // sort is still "auto". Tonight defaults to hours_visible desc —
  // but that column doesn't exist in Anytime, so leaving it would
  // send the server a sort key that maps to an all-NULL column and
  // produces a meaningless order. Anytime defaults to designation
  // asc (matches the DSO catalog page).
  useEffect(() => {
    if (!sortIsAutoRef.current) return;
    setSortModel(
      restrictTonight
        ? [{ field: "hours_visible", sort: "desc" }]
        : [{ field: "primary_designation", sort: "asc" }],
    );
  }, [restrictTonight]);

  // Rig: drop a stored id that no longer resolves (rig retired or
  // deleted). No auto-select — "No rig" is a valid state.
  useEffect(() => {
    const rigs = rigsQuery.data;
    if (!rigs || rigId == null) return;
    if (!rigs.some((r) => r.id === rigId)) {
      setRigId(null);
    }
  }, [rigId, rigsQuery.data, setRigId]);

  const sortField = sortModel[0]?.field ?? "hours_visible";
  const sortDir = (sortModel[0]?.sort ?? "desc") as "asc" | "desc";
  const debouncedSearch = useDebounce(searchQuery.trim(), 250);

  const targetsQuery = useQuery({
    queryKey: [
      "planner-targets",
      {
        locationId,
        rigId,
        typeGroupFilter,
        typeFilter,
        constellation,
        hasDistance,
        minHours,
        maxMag,
        minSize,
        framesWell,
        q: debouncedSearch || null,
        restrictTonight,
        limit: pagination.pageSize,
        offset: pagination.page * pagination.pageSize,
        sortField,
        sortDir,
      },
    ],
    // Imaging-focused filters (min_hours / max_magnitude /
    // min_size_arcmin / frames_well) only make sense in "Tonight"
    // mode — a user browsing the full catalog expects parity with
    // the DSO catalog page, which has none of these. Sending the
    // user's saved imaging defaults in Anytime would silently
    // collapse e.g. Galaxy Groups (small + faint) to a near-empty
    // list.
    queryFn: () =>
      fetchPlannerTargets({
        location_id: locationId!,
        rig_id: rigId,
        type_group: typeGroupFilter,
        type: typeFilter,
        constellation: constellation || null,
        has_distance: hasDistance ? true : null,
        min_hours: restrictTonight ? minHours : null,
        max_magnitude: restrictTonight ? maxMag : null,
        min_size_arcmin: restrictTonight ? minSize : null,
        frames_well: restrictTonight ? framesWell : false,
        q: debouncedSearch || null,
        restrict_tonight: restrictTonight,
        limit: pagination.pageSize,
        offset: pagination.page * pagination.pageSize,
        sort: sortField,
        sort_dir: sortDir,
      }),
    enabled: locationId != null,
    placeholderData: (prev) => prev,
  });

  const toggleTypeGroup = (name: string) => {
    setTypeGroupFilter((cur) =>
      cur.includes(name) ? cur.filter((g) => g !== name) : [...cur, name],
    );
    setPagination((p) => ({ ...p, page: 0 }));
  };

  const toggleType = (code: string) => {
    setTypeFilter((cur) =>
      cur.includes(code) ? cur.filter((t) => t !== code) : [...cur, code],
    );
    setPagination((p) => ({ ...p, page: 0 }));
  };

  const clearCatalogFilters = () => {
    setSearchQuery("");
    setTypeGroupFilter([]);
    setTypeFilter([]);
    setConstellation("");
    setHasDistance(false);
    setPagination((p) => ({ ...p, page: 0 }));
  };

  // Use the raw search input, not the debounced value, so the "Clear
  // filters" button appears/disappears in sync with typing rather
  // than lagging 250 ms behind.
  const catalogFiltersActive =
    searchQuery.length > 0 ||
    typeGroupFilter.length > 0 ||
    typeFilter.length > 0 ||
    constellation.length > 0 ||
    hasDistance;

  const activeLocation = locationsQuery.data?.find((l) => l.id === locationId);
  const tz = activeLocation?.timezone ?? "UTC";
  const locationName = activeLocation?.name ?? null;
  const data = targetsQuery.data;

  // Block the UI behind the filter bar / grid when we can't reasonably
  // show any targets yet. Both empty-states mirror the DSO Catalog page
  // pattern — full-height centered panel + CTA button to the page
  // that fixes the gap.
  const hasLocations =
    !locationsQuery.isLoading && (locationsQuery.data?.length ?? 0) > 0;
  const catalogTotal = (facetsQuery.data?.type_groups ?? []).reduce(
    (sum, g) => sum + g.count,
    0,
  );
  const hasCatalog = !facetsQuery.isLoading && catalogTotal > 0;
  const plannerEmptyState: "no-location" | "no-catalog" | null =
    !locationsQuery.isLoading && !hasLocations
      ? "no-location"
      : !facetsQuery.isLoading && !hasCatalog
        ? "no-catalog"
        : null;
  const rigFov = data?.rig
    ? `${(data.rig.fov_major_deg * 60).toFixed(1)}' × ${(data.rig.fov_minor_deg * 60).toFixed(1)}'`
    : null;
  // Sensor aspect ratio (major / minor) for the rig-framed column. The
  // stored image is square 180×180 at the rig's major-axis FOV; we
  // present it in a major:minor-shaped box and let object-fit crop.
  const rigAspect =
    data?.rig && data.rig.fov_minor_deg > 0
      ? data.rig.fov_major_deg / data.rig.fov_minor_deg
      : null;

  // Every data column uses flex + minWidth so the grid fills the viewport
  // and contracts gracefully as the window narrows. Only the thumbnail
  // cell has a hard width (image-sized, nothing to gain by flexing it).
  const columns: GridColDef<PlannerTargetItem>[] = [
    {
      field: "thumbnail",
      headerName: "",
      width: 76,
      sortable: false,
      renderCell: (params) => <ThumbnailCell dsoId={params.row.dso_id} size={60} />,
    },
    ...(data?.rig && rigAspect
      ? [
          {
            field: "rig_framed",
            headerName: "In my rig",
            width: 96,
            sortable: false,
            renderCell: (params) => (
              <ThumbnailCell
                dsoId={params.row.dso_id}
                size={80}
                variant="rig_framed"
                fovMajorDeg={data.rig!.fov_major_deg}
                fovMinorDeg={data.rig!.fov_minor_deg}
                aspectRatio={rigAspect}
              />
            ),
          } as GridColDef<PlannerTargetItem>,
        ]
      : []),
    {
      field: "primary_designation",
      headerName: "Designation",
      flex: 0.7,
      minWidth: 90,
      renderCell: (p) => (
        <Typography variant="body2" fontWeight={600}>
          {p.value}
        </Typography>
      ),
    },
    {
      field: "common_name",
      headerName: "Name",
      flex: 1.4,
      minWidth: 140,
      valueFormatter: (v) => v ?? "—",
    },
    {
      field: "type_group",
      headerName: "Type",
      flex: 0.9,
      minWidth: 120,
      renderCell: (p) => {
        const style = typeGroupStyle(p.value as string);
        return (
          <Chip
            label={p.value ?? p.row.obj_type}
            size="small"
            sx={{ bgcolor: style.bg, color: "#ffffff", fontWeight: 500 }}
          />
        );
      },
    },
    {
      field: "size",
      headerName: "Size",
      flex: 0.6,
      minWidth: 85,
      sortable: false,
      valueGetter: (_v, row) => {
        if (row.maj_axis_arcmin == null) return "—";
        if (row.min_axis_arcmin != null && row.min_axis_arcmin !== row.maj_axis_arcmin) {
          return `${row.maj_axis_arcmin.toFixed(1)}' × ${row.min_axis_arcmin.toFixed(1)}'`;
        }
        return `${row.maj_axis_arcmin.toFixed(1)}'`;
      },
    },
    {
      field: "mag_v",
      headerName: "Mag V",
      flex: 0.4,
      minWidth: 60,
      type: "number",
      valueFormatter: (v) => (v == null ? "—" : (v as number).toFixed(1)),
    },
    // Visibility columns only make sense in "Tonight" mode — in
    // Anytime the API returns ``null`` for all of these and showing
    // four columns of "—" is just noise.
    ...(restrictTonight
      ? ([
          {
            field: "hours_visible",
            headerName: "Hours",
            flex: 0.4,
            minWidth: 60,
            type: "number" as const,
            valueFormatter: (v) =>
              v == null ? "—" : `${(v as number).toFixed(1)}h`,
          },
          {
            field: "max_altitude_deg",
            headerName: "Max altitude",
            flex: 1.0,
            minWidth: 120,
            type: "number" as const,
            renderCell: (p) => {
              const alt = p.row.max_altitude_deg as number | null;
              if (alt == null || p.row.peak_time_utc == null) {
                return (
                  <Typography variant="body2" color="text.disabled">
                    —
                  </Typography>
                );
              }
              return (
                <Typography variant="body2">
                  {alt.toFixed(0)}° @ {formatLocalTime(p.row.peak_time_utc, tz)}
                </Typography>
              );
            },
          },
          {
            field: "transit",
            headerName: "Meridian",
            flex: 1.0,
            minWidth: 120,
            sortable: false,
            renderCell: (p) => {
              const alt = p.row.altitude_at_transit_deg as number | null;
              if (alt == null || p.row.transit_time_utc == null) {
                return (
                  <Typography variant="body2" color="text.disabled">
                    —
                  </Typography>
                );
              }
              return (
                <Typography variant="body2">
                  {alt.toFixed(0)}° @{" "}
                  {formatLocalTime(p.row.transit_time_utc, tz)}
                </Typography>
              );
            },
          },
          {
            field: "min_moon_separation_deg",
            headerName: "Moon",
            flex: 0.4,
            minWidth: 60,
            type: "number" as const,
            valueFormatter: (v) =>
              v == null ? "—" : `${(v as number).toFixed(0)}°`,
          },
        ] as GridColDef<PlannerTargetItem>[])
      : []),
    ...(rigFov
      ? [
          {
            field: "coverage_pct",
            headerName: "FOV",
            flex: 0.5,
            minWidth: 75,
            type: "number" as const,
            valueFormatter: (v) => (v == null ? "—" : `${(v as number).toFixed(0)}%`),
          } as GridColDef<PlannerTargetItem>,
        ]
      : []),
    {
      field: "constellation",
      headerName: "Const",
      flex: 0.5,
      minWidth: 70,
      valueFormatter: (v) => displayConstellation(v as string | null),
    },
  ];

  return (
    <Box
      sx={{
        p: 3,
        display: "flex",
        flexDirection: "column",
        gap: 2,
        height: "100%",
        overflow: "hidden",
      }}
    >
      {/* Header — title + prominent mode toggle. The mode chooses
          which "lens" the rest of the page is in: Tonight pulls in
          location / visibility / moon context; Anytime strips those
          away for pure catalog browsing. */}
      <Stack direction="row" alignItems="center" gap={2} flexWrap="wrap">
        <Typography variant="h5" fontWeight={600}>
          Target Planner
        </Typography>
        <ToggleButtonGroup
          size="small"
          exclusive
          value={restrictTonight ? "tonight" : "anytime"}
          onChange={(_, v) => {
            if (v === null) return; // can't deselect both
            setRestrictTonight(v === "tonight");
            setPagination((p) => ({ ...p, page: 0 }));
          }}
          aria-label="Planner scope"
        >
          <ToggleButton value="tonight" sx={{ textTransform: "none", px: 2 }}>
            Tonight from {locationName ?? "Home"}
          </ToggleButton>
          <ToggleButton value="anytime" sx={{ textTransform: "none", px: 2 }}>
            Browse the full catalog
          </ToggleButton>
        </ToggleButtonGroup>
        {restrictTonight && data?.dark_window ? (
          <Typography variant="body2" color="text.secondary">
            Astro dark: {formatLocalTime(data.dark_window.start_utc, tz)} –{" "}
            {formatLocalTime(data.dark_window.end_utc, tz)} · {data.dark_window.hours.toFixed(1)}{" "}
            hours · Moon {Math.round(data.moon_phase_pct)}%
          </Typography>
        ) : null}
      </Stack>

      {plannerEmptyState !== null ? (
        plannerEmptyState === "no-location" ? (
          <Paper
            variant="outlined"
            sx={{
              flex: 1,
              minHeight: 0,
              display: "flex",
              flexDirection: "column",
              alignItems: "center",
              justifyContent: "center",
              gap: 2,
              p: 4,
              textAlign: "center",
            }}
          >
            <PlaceOutlinedIcon sx={{ fontSize: 64, color: "text.secondary" }} />
            <Typography variant="h6">No imaging location defined</Typography>
            <Typography variant="body2" color="text.secondary" sx={{ maxWidth: 520 }}>
              The planner needs to know where you're observing from before it
              can compute rise / set times and altitudes. Add your
              backyard, remote site, or any other location and mark one as
              the default.
            </Typography>
            <Button
              component={RouterLink}
              to="/locations"
              variant="contained"
              startIcon={<PlaceOutlinedIcon />}
            >
              Go to Locations
            </Button>
          </Paper>
        ) : (
          <Paper
            variant="outlined"
            sx={{
              flex: 1,
              minHeight: 0,
              display: "flex",
              flexDirection: "column",
              alignItems: "center",
              justifyContent: "center",
              gap: 2,
              p: 4,
              textAlign: "center",
            }}
          >
            <CloudDownloadOutlinedIcon sx={{ fontSize: 64, color: "text.secondary" }} />
            <Typography variant="h6">No deep-sky object catalog loaded</Typography>
            <Typography variant="body2" color="text.secondary" sx={{ maxWidth: 520 }}>
              NightCrate doesn't ship catalog data — the planner can't
              suggest targets until OpenNGC (and optionally Sharpless,
              Barnard, 50 MGC) is fetched from Admin → Catalogs.
            </Typography>
            <Button
              component={RouterLink}
              to="/admin"
              variant="contained"
              startIcon={<CloudDownloadOutlinedIcon />}
            >
              Go to Admin → Catalogs
            </Button>
          </Paper>
        )
      ) : (
        <>
      {/* Filter bar */}
      <Paper variant="outlined" sx={{ p: 2 }}>
        <Stack direction={{ xs: "column", md: "row" }} gap={2} flexWrap="wrap">
          <TextField
            size="small"
            placeholder="Search (M42, NGC 1976, Orion Nebula…)"
            value={searchQuery}
            onChange={(e) => {
              setSearchQuery(e.target.value);
              setPagination((p) => ({ ...p, page: 0 }));
            }}
            sx={{ minWidth: 280, flex: { xs: 1, md: "initial" } }}
            InputProps={{
              startAdornment: (
                <InputAdornment position="start">
                  <SearchIcon fontSize="small" />
                </InputAdornment>
              ),
              endAdornment: searchQuery ? (
                <InputAdornment position="end">
                  <IconButton size="small" onClick={() => setSearchQuery("")}>
                    <CloseIcon fontSize="small" />
                  </IconButton>
                </InputAdornment>
              ) : null,
            }}
          />

          {restrictTonight && (
            <FormControl size="small" sx={{ minWidth: 220 }}>
              <InputLabel>Location</InputLabel>
              <Select
                label="Location"
                value={locationId ?? ""}
                onChange={(e) => {
                  const v = String(e.target.value);
                  setLocationId(v === "" ? null : Number(v));
                  setPagination((p) => ({ ...p, page: 0 }));
                }}
              >
                {locationsQuery.data?.map((l) => (
                  <MenuItem key={l.id} value={l.id}>
                    {l.name}
                    {l.is_default ? " (default)" : ""}
                  </MenuItem>
                ))}
              </Select>
            </FormControl>
          )}

          <FormControl size="small" sx={{ minWidth: 220 }}>
            <InputLabel>Rig</InputLabel>
            <Select
              label="Rig"
              value={rigId ?? ""}
              onChange={(e) => {
                const v = String(e.target.value);
                setRigId(v === "" ? null : Number(v));
                setFramesWell(false);
                setPagination((p) => ({ ...p, page: 0 }));
              }}
            >
              <MenuItem value="">
                <em>No rig</em>
              </MenuItem>
              {rigsQuery.data?.map((r) => (
                <MenuItem key={r.id} value={r.id}>
                  {r.name}
                </MenuItem>
              ))}
            </Select>
          </FormControl>

          <FormControl size="small" sx={{ minWidth: 180 }}>
            <InputLabel>Constellation</InputLabel>
            <Select
              label="Constellation"
              value={constellation}
              onChange={(e) => {
                setConstellation(e.target.value);
                setPagination((p) => ({ ...p, page: 0 }));
              }}
            >
              <MenuItem value="">
                <em>All</em>
              </MenuItem>
              {[...(facetsQuery.data?.constellations ?? [])]
                .sort((a, b) =>
                  displayConstellation(a.code).localeCompare(displayConstellation(b.code)),
                )
                .map((c) => (
                  <MenuItem key={c.code} value={c.code}>
                    {displayConstellation(c.code)} ({c.count.toLocaleString()})
                  </MenuItem>
                ))}
            </Select>
          </FormControl>

          <FormControlLabel
            control={
              <Checkbox
                size="small"
                checked={hasDistance}
                onChange={(e) => {
                  setHasDistance(e.target.checked);
                  setPagination((p) => ({ ...p, page: 0 }));
                }}
              />
            }
            label="Has distance"
            sx={{ m: 0 }}
          />

          {catalogFiltersActive && (
            <Button size="small" variant="text" onClick={clearCatalogFilters}>
              Clear filters
            </Button>
          )}

          {rigFov && (
            <Typography variant="caption" color="text.secondary" alignSelf="center">
              FOV: {rigFov}
            </Typography>
          )}
        </Stack>

        {/* Primary type-group chips */}
        <Box sx={{ mt: 2, display: "flex", flexWrap: "wrap", gap: 0.75 }}>
          {[...(facetsQuery.data?.type_groups ?? [])]
            .filter((g) => g.count > 0)
            .sort((a, b) => a.display_order - b.display_order)
            .map((g) => {
              const active = typeGroupFilter.includes(g.name);
              const style = typeGroupStyle(g.name);
              return (
                <Chip
                  key={g.name}
                  label={`${g.name} (${g.count.toLocaleString()})`}
                  size="small"
                  onClick={() => toggleTypeGroup(g.name)}
                  variant={active ? "filled" : "outlined"}
                  sx={{
                    bgcolor: active ? style.bg : undefined,
                    color: active ? "#ffffff" : undefined,
                    borderColor: style.bg,
                    fontWeight: 500,
                  }}
                />
              );
            })}
        </Box>

        {/* Advanced filters — raw OpenNGC type codes for power users */}
        <Box sx={{ mt: 1.5 }}>
          <Button
            size="small"
            variant="text"
            onClick={() => setAdvancedOpen((open) => !open)}
            sx={{ textTransform: "none", fontSize: "0.75rem" }}
          >
            {advancedOpen ? "▾" : "▸"} Advanced filters
          </Button>
          {advancedOpen && (
            <Box sx={{ mt: 1, display: "flex", flexWrap: "wrap", gap: 0.75 }}>
              {facetsQuery.data?.raw_types.map((t) => {
                const active = typeFilter.includes(t.code);
                return (
                  <Chip
                    key={t.code}
                    label={`${displayDsoType(t.code)} (${t.count.toLocaleString()})`}
                    size="small"
                    onClick={() => toggleType(t.code)}
                    variant={active ? "filled" : "outlined"}
                    sx={{
                      bgcolor: active ? dsoTypeColor(t.code) : undefined,
                      color: active ? "#ffffff" : undefined,
                      borderColor: dsoTypeColor(t.code),
                      fontWeight: 500,
                    }}
                  />
                );
              })}
            </Box>
          )}
        </Box>

        {/* Imaging-focused sliders — only meaningful in Tonight mode.
            In Anytime the page behaves like a catalog browser, so
            visibility hours / exposure-time-equivalent magnitude cuts
            / frame size don't belong. */}
        {restrictTonight && (
          <Stack direction={{ xs: "column", md: "row" }} gap={3} sx={{ mt: 2, px: 1 }}>
            <Box sx={{ flex: 1, minWidth: 200 }}>
              <Typography variant="caption">Min hours visible: {minHours.toFixed(1)}h</Typography>
              <Slider
                size="small"
                value={minHours}
                min={0}
                max={12}
                step={0.5}
                onChange={(_, v) => setMinHours(v as number)}
                onChangeCommitted={() => setPagination((p) => ({ ...p, page: 0 }))}
              />
            </Box>
            <Box sx={{ flex: 1, minWidth: 200 }}>
              <Typography variant="caption">Brighter than mag {maxMag.toFixed(1)}</Typography>
              <Slider
                size="small"
                value={maxMag}
                min={5}
                max={18}
                step={0.5}
                onChange={(_, v) => setMaxMag(v as number)}
                onChangeCommitted={() => setPagination((p) => ({ ...p, page: 0 }))}
              />
            </Box>
            <Box sx={{ flex: 1, minWidth: 200 }}>
              <Typography variant="caption">Min size: {minSize.toFixed(0)}'</Typography>
              <Slider
                size="small"
                value={minSize}
                min={0}
                max={60}
                step={1}
                onChange={(_, v) => setMinSize(v as number)}
                onChangeCommitted={() => setPagination((p) => ({ ...p, page: 0 }))}
              />
            </Box>
            {rigFov && (
              <Tooltip title="Covers 15–90% of the frame">
                <FormControlLabel
                  control={
                    <Checkbox
                      size="small"
                      checked={framesWell}
                      onChange={(e) => {
                        setFramesWell(e.target.checked);
                        setPagination((p) => ({ ...p, page: 0 }));
                      }}
                    />
                  }
                  label="Frames well"
                  sx={{ m: 0, alignSelf: "center" }}
                />
              </Tooltip>
            )}
          </Stack>
        )}
      </Paper>

      {/* Empty / error states — only relevant in Tonight mode; in
          Anytime there's no location/date, so the concept doesn't
          apply. */}
      {restrictTonight && targetsQuery.data?.dark_window === null && (
        <Alert severity="info">
          It doesn't get astronomically dark tonight at{" "}
          {targetsQuery.data.location.name} — summer twilight at high
          latitude. Try another night or location.
        </Alert>
      )}

      {/* Grid */}
      <Paper variant="outlined" sx={{ flex: 1, minHeight: 0 }}>
        <DataGrid
          rows={data?.items ?? []}
          getRowId={(row) => row.dso_id}
          columns={columns}
          loading={targetsQuery.isLoading || targetsQuery.isFetching}
          paginationMode="server"
          sortingMode="server"
          rowCount={data?.total ?? 0}
          paginationModel={pagination}
          onPaginationModelChange={setPagination}
          sortModel={sortModel}
          onSortModelChange={(m) => {
            sortIsAutoRef.current = false;
            setSortModel(m);
          }}
          pageSizeOptions={[25, 50, 100]}
          getRowHeight={() => "auto"}
          onRowClick={(params: GridRowParams<PlannerTargetItem>) =>
            setDetailId(params.row.dso_id)
          }
          disableRowSelectionOnClick
          slots={{
            noRowsOverlay: () => (
              <Stack
                alignItems="center"
                justifyContent="center"
                sx={{ height: "100%", px: 3, textAlign: "center" }}
                gap={0.5}
              >
                <Typography variant="body2" color="text.secondary">
                  {restrictTonight
                    ? "No targets match these filters tonight."
                    : "No DSOs match these filters."}
                </Typography>
                {restrictTonight && (
                  <Typography variant="caption" color="text.secondary">
                    Try relaxing Min hours / Magnitude, or switch to
                    &ldquo;Browse the full catalog&rdquo; mode.
                  </Typography>
                )}
              </Stack>
            ),
          }}
          sx={{
            border: 0,
            "& .MuiDataGrid-row": { cursor: "pointer" },
            // Cells wrap text over multiple lines rather than truncating
            // with ellipses when the column gets narrow. Paired with
            // getRowHeight="auto" so the row grows to fit.
            "& .MuiDataGrid-cell": {
              whiteSpace: "normal",
              lineHeight: 1.35,
              alignItems: "center",
              py: 1,
            },
            "& .MuiDataGrid-cell:focus, & .MuiDataGrid-cell:focus-within": {
              outline: "none",
            },
            // MUI X DataGrid v8 renders a small three-dot "overflow" button
            // on cells whose content it believes is truncated. It fires
            // on every thumbnail cell because the <img> has a fixed width
            // the grid can't measure past. We wrap text with whiteSpace:
            // normal, so the indicator has nothing to reveal and just adds
            // noise — hide it.
            "& .MuiDataGrid-cellOverflowIndicator, & .MuiDataGrid-cellOverflowIndicatorButton":
              {
                display: "none",
              },
          }}
        />
      </Paper>
        </>
      )}

      <PlannerDetailPanel
        dsoId={detailId}
        target={data?.items.find((i) => i.dso_id === detailId) ?? null}
        selectedLocationId={locationId}
        locations={locationsQuery.data ?? []}
        selectedRigId={rigId}
        rigs={rigsQuery.data ?? []}
        onSelectDso={(id) => setDetailId(id)}
        onClose={() => setDetailId(null)}
      />
    </Box>
  );
}
