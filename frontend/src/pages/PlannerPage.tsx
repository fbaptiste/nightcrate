/**
 * Target Planner (v0.16.0, Pass A).
 *
 * Location-driven "what's up tonight" list. Optional rig adds a FOV
 * coverage column and the "frames well" filter.
 */
import { useEffect, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import {
  DataGrid,
  type GridColDef,
  type GridPaginationModel,
  type GridRowParams,
} from "@mui/x-data-grid";
import Alert from "@mui/material/Alert";
import Box from "@mui/material/Box";
import Chip from "@mui/material/Chip";
import CircularProgress from "@mui/material/CircularProgress";
import FormControl from "@mui/material/FormControl";
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
import ArrowDownwardIcon from "@mui/icons-material/ArrowDownward";
import ArrowUpwardIcon from "@mui/icons-material/ArrowUpward";
import CircleIcon from "@mui/icons-material/Circle";
import CloseIcon from "@mui/icons-material/Close";
import CloudDownloadOutlinedIcon from "@mui/icons-material/CloudDownloadOutlined";
import PlaceOutlinedIcon from "@mui/icons-material/PlaceOutlined";
import SearchIcon from "@mui/icons-material/Search";
import { Link as RouterLink } from "react-router-dom";
import { fetchLocations } from "@/api/locations";
import { fetchRigs } from "@/api/rigs";
import { fetchDsoFacets } from "@/api/dsos";
import { fetchHorizons, type Horizon } from "@/api/horizons";
import ListSubheader from "@mui/material/ListSubheader";
import PlannerSortPanel from "@/components/planner/PlannerSortPanel";
import { serializeSort } from "@/lib/plannerSortFields";
import {
  fetchPlannerTargets,
  type PlannerTargetItem,
} from "@/api/planner";
import { useSettingsStore } from "@/stores/settingsStore";
import { usePlannerStore } from "@/stores/plannerStore";
import { useDebounce } from "@/lib/useDebounce";
import PaginationActions from "@/components/common/PaginationActions";
import GridLoadingOverlay from "@/components/common/GridLoadingOverlay";
import { displayDsoType, dsoTypeColor } from "@/lib/dsoTypeNames";
import { displayConstellation } from "@/lib/constellations";
import { RIG_BLUE, RIG_ORANGE } from "@/lib/rigColors";
import MoonPhaseIcon from "@/components/weather/MoonPhaseIcon";
import CatalogFilter from "@/components/dso/CatalogFilter";
import ConstellationFilter from "@/components/dso/ConstellationFilter";
import TypeFilter from "@/components/dso/TypeFilter";
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
  const horizonId = usePlannerStore((s) => s.selectedHorizonId);
  const setHorizonId = usePlannerStore((s) => s.setSelectedHorizonId);
  const rigId = usePlannerStore((s) => s.selectedRigId);
  const setRigId = usePlannerStore((s) => s.setSelectedRigId);
  const sortBy = usePlannerStore((s) => s.sortBy);
  const setSortBy = usePlannerStore((s) => s.setSortBy);
  const [searchQuery, setSearchQuery] = useState("");
  const [restrictTonight, setRestrictTonight] = useState<boolean>(true);
  const [typeFilter, setTypeFilter] = useState<string[]>([]);
  const [catalogFilter, setCatalogFilter] = useState<string[]>([]);
  const [constellationFilter, setConstellationFilter] = useState<string[]>([]);
  // Two-state pattern per slider — UI tracks the ``*Draft`` value
  // during drag, and only the committed (``minHours`` / ``maxMag``
  // / ``minSize``) value feeds the query key. Without this split,
  // every intermediate drag tick re-fires ``/api/planner/targets``
  // and the grid visibly flashes the relaxed-filter result set.
  const [minHours, setMinHours] = useState<number>(
    settings?.planner_min_visibility_hours ?? 2.0,
  );
  const [minHoursDraft, setMinHoursDraft] = useState<number>(minHours);
  const [maxMag, setMaxMag] = useState<number>(settings?.planner_max_magnitude ?? 12.0);
  const [maxMagDraft, setMaxMagDraft] = useState<number>(maxMag);
  const [minSize, setMinSize] = useState<number>(settings?.planner_min_size_arcmin ?? 5.0);
  const [minSizeDraft, setMinSizeDraft] = useState<number>(minSize);
  // Frames-Well is a dual-thumb coverage range slider. Defaults come
  // from user settings (``planner_frames_well_min_pct`` /
  // ``planner_frames_well_max_pct``); setting the range to 0–200
  // turns filtering off. Two-state commit mirrors the other sliders
  // so dragging doesn't re-fire the query on every tick.
  const framesWellDefault: [number, number] = [
    settings?.planner_frames_well_min_pct ?? 15,
    settings?.planner_frames_well_max_pct ?? 90,
  ];
  const [coverageRange, setCoverageRange] = useState<[number, number]>(framesWellDefault);
  const [coverageRangeDraft, setCoverageRangeDraft] =
    useState<[number, number]>(framesWellDefault);
  const [pagination, setPagination] = useState<GridPaginationModel>({
    page: 0,
    pageSize: DEFAULT_PAGE_SIZE,
  });
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
  // Horizons for the selected location. The grid's visibility
  // computation runs against this horizon; the horizon selector
  // resets to the location's default whenever location changes.
  const horizonsQuery = useQuery({
    queryKey: ["horizons", locationId],
    queryFn: () => fetchHorizons(locationId as number),
    enabled: locationId != null,
    staleTime: 5 * 60_000,
  });
  const horizons: Horizon[] = horizonsQuery.data ?? [];
  // Used to populate the pill filter option lists (full-catalog sets of
  // raw types / catalogs / constellations) and to detect "no catalog
  // loaded" state. Per-option COUNTS in the pickers come from
  // ``/api/planner/targets`` (filter-aware) — the facets here are
  // option-source only.
  const facetsQuery = useQuery({
    queryKey: ["dso-facets"],
    queryFn: () => fetchDsoFacets(),
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
      setHorizonId(null);
      return;
    }
    if (locationId == null) {
      const def = locs.find((l) => l.is_default) ?? locs[0];
      setLocationId(def.id);
    }
  }, [locationId, locationsQuery.data, setLocationId, setHorizonId]);

  // Horizon: snap to the location's default whenever the stored id
  // doesn't resolve against the current horizon list (stale store,
  // location changed, horizon deleted).
  useEffect(() => {
    if (horizons.length === 0) return;
    if (horizonId != null && horizons.some((h) => h.id === horizonId)) return;
    const def = horizons.find((h) => h.is_default) ?? horizons[0];
    setHorizonId(def.id);
  }, [horizonId, horizons, setHorizonId]);

  // Rig: drop a stored id that no longer resolves (rig retired or
  // deleted). No auto-select — "No rig" is a valid state.
  useEffect(() => {
    const rigs = rigsQuery.data;
    if (!rigs || rigId == null) return;
    if (!rigs.some((r) => r.id === rigId)) {
      setRigId(null);
    }
  }, [rigId, rigsQuery.data, setRigId]);


  // Serialize the active multi-sort for the backend. Entries that
  // aren't applicable in the current mode / rig state are filtered
  // out by ``serializeSort`` — the backend's own default kicks in
  // when the resulting string is empty.
  const sortParam = serializeSort(sortBy, restrictTonight, rigId != null);
  const debouncedSearch = useDebounce(searchQuery.trim(), 250);


  const targetsQuery = useQuery({
    queryKey: [
      "planner-targets",
      {
        locationId,
        horizonId,
        rigId,
        typeFilter,
        catalogFilter,
        constellationFilter,
        minHours,
        maxMag,
        minSize,
        coverageRange,
        q: debouncedSearch || null,
        restrictTonight,
        limit: pagination.pageSize,
        offset: pagination.page * pagination.pageSize,
        sortParam,
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
        // Tonight mode gates the query on ``locationId != null``
        // (see ``enabled`` below), so the non-null assertion is
        // safe. Anytime mode sends ``null`` so the backend skips
        // the location load entirely.
        location_id: restrictTonight ? locationId! : null,
        horizon_id: restrictTonight ? horizonId : null,
        rig_id: rigId,
        type: typeFilter,
        catalog: catalogFilter,
        constellation: constellationFilter,
        min_hours: restrictTonight ? minHours : null,
        max_magnitude: restrictTonight ? maxMag : null,
        min_size_arcmin: restrictTonight ? minSize : null,
        // Only forward the coverage bounds when the range has been
        // narrowed. 0-200 = full range = no filter.
        coverage_min_pct:
          restrictTonight && coverageRange[0] > 0 ? coverageRange[0] : null,
        coverage_max_pct:
          restrictTonight && coverageRange[1] < 200 ? coverageRange[1] : null,
        q: debouncedSearch || null,
        restrict_tonight: restrictTonight,
        limit: pagination.pageSize,
        offset: pagination.page * pagination.pageSize,
        sort: sortParam,
      }),
    // Tonight mode is location-dependent; Anytime runs without one.
    enabled: !restrictTonight || locationId != null,
    placeholderData: (prev) => prev,
  });

  const clearCatalogFilters = () => {
    setSearchQuery("");
    setTypeFilter([]);
    setCatalogFilter([]);
    setConstellationFilter([]);
    setPagination((p) => ({ ...p, page: 0 }));
  };

  // Use the raw search input, not the debounced value, so the "Clear
  // filters" button appears/disappears in sync with typing rather
  // than lagging 250 ms behind.
  const catalogFiltersActive =
    searchQuery.length > 0 ||
    typeFilter.length > 0 ||
    catalogFilter.length > 0 ||
    constellationFilter.length > 0;

  const activeLocation = locationsQuery.data?.find((l) => l.id === locationId);
  const tz = activeLocation?.timezone ?? "UTC";
  const locationName = activeLocation?.name ?? null;
  const data = targetsQuery.data;

  // Block the UI behind the filter bar / grid when we can't reasonably
  // show any targets yet. The "no-location" CTA only fires in Tonight
  // mode — Anytime is location-independent, so a first-run user with
  // no locations can still browse the catalog.
  const hasLocations =
    !locationsQuery.isLoading && (locationsQuery.data?.length ?? 0) > 0;
  const catalogTotal = (facetsQuery.data?.raw_types ?? []).reduce(
    (sum, t) => sum + t.count,
    0,
  );
  const hasCatalog = !facetsQuery.isLoading && catalogTotal > 0;
  const plannerEmptyState: "no-location" | "no-catalog" | null =
    restrictTonight && !locationsQuery.isLoading && !hasLocations
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

  // Column layout rewritten for the compact planner redesign:
  // - Designation + type-chip collapsed into one two-line cell.
  // - Meridian + Max altitude collapsed; when the peak-during-dark
  //   lands on the transit they render as a single "meridian / max
  //   alt: VAL" line; otherwise each gets its own line.
  // - Moon column drops the phase (phase lives in the header) and
  //   shows only the minimum target–moon separation.
  // - FOV coverage % is captioned under the "In my rig" thumb
  //   instead of occupying its own column.
  // - Grid column sorting is fully disabled; a dedicated sort UI
  //   will replace it.
  const columns: GridColDef<PlannerTargetItem>[] = [
    {
      field: "thumbnail",
      headerName: "",
      // Width bumped to 96 — the cell now carries the rise/set
      // status glyph on the left (~18 px + gap) in addition to the
      // 60 px thumbnail.
      width: 96,
      sortable: false,
      renderCell: (p) => {
        const status = p.row.now_status as "up" | "rising" | "set" | null;
        const icon =
          status === "up" ? (
            <Tooltip title="Above horizon right now" arrow>
              <CircleIcon sx={{ color: RIG_BLUE, fontSize: 14 }} />
            </Tooltip>
          ) : status === "rising" ? (
            <Tooltip title="Not up yet — rises during tonight" arrow>
              <ArrowUpwardIcon sx={{ color: RIG_ORANGE, fontSize: 18 }} />
            </Tooltip>
          ) : status === "set" ? (
            <Tooltip title="Already set for tonight" arrow>
              <ArrowDownwardIcon sx={{ color: "text.secondary", fontSize: 18 }} />
            </Tooltip>
          ) : null;
        return (
          <Stack direction="row" alignItems="center" gap={0.75}>
            {/* Reserve the icon slot even when ``null`` so the
                thumbnail sits at a consistent x position across
                rows — matters in Anytime mode where every row has
                a null status. */}
            <Box sx={{ width: 18, display: "flex", justifyContent: "center" }}>
              {icon}
            </Box>
            <ThumbnailCell dsoId={p.row.dso_id} size={60} />
          </Stack>
        );
      },
    },
    ...(data?.rig && rigAspect
      ? [
          {
            field: "rig_framed",
            headerName: "In my rig",
            width: 96,
            sortable: false,
            renderCell: (params) => {
              const coverage = params.row.coverage_pct as number | null;
              return (
                <Stack alignItems="center" spacing={0.25}>
                  <ThumbnailCell
                    dsoId={params.row.dso_id}
                    size={72}
                    variant="rig_framed"
                    fovMajorDeg={data.rig!.fov_major_deg}
                    fovMinorDeg={data.rig!.fov_minor_deg}
                    aspectRatio={rigAspect}
                  />
                  <Typography
                    variant="caption"
                    color={coverage == null ? "text.disabled" : "text.secondary"}
                    sx={{ lineHeight: 1, fontWeight: 500 }}
                  >
                    {coverage == null ? "—" : `${coverage.toFixed(0)}%`}
                  </Typography>
                </Stack>
              );
            },
          } as GridColDef<PlannerTargetItem>,
        ]
      : []),
    {
      field: "primary_designation",
      // Merged Designation + Name + Type. Line 1: bold primary
      // designation. Line 2 (optional): muted common name — hidden
      // when the DSO has none. Line 3: small coloured type chip.
      headerName: "Designation",
      flex: 1.6,
      minWidth: 180,
      sortable: false,
      renderCell: (p) => (
        <Stack spacing={0.25}>
          <Typography variant="body2" fontWeight={600}>
            {p.value as string}
          </Typography>
          {p.row.common_name ? (
            <Typography
              variant="caption"
              color="text.secondary"
              sx={{ lineHeight: 1.25 }}
            >
              {p.row.common_name}
            </Typography>
          ) : null}
          <Chip
            label={displayDsoType(p.row.obj_type)}
            size="small"
            sx={{
              bgcolor: dsoTypeColor(p.row.obj_type),
              color: "#ffffff",
              fontWeight: 500,
              width: "fit-content",
              height: 18,
              "& .MuiChip-label": { px: 0.75, fontSize: "0.7rem" },
            }}
          />
        </Stack>
      ),
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
      sortable: false,
      valueFormatter: (v) => (v == null ? "—" : (v as number).toFixed(1)),
    },
    // Visibility columns only make sense in "Tonight" mode.
    ...(restrictTonight
      ? ([
          {
            field: "hours_visible",
            headerName: "Hours",
            flex: 0.4,
            minWidth: 60,
            type: "number" as const,
            sortable: false,
            valueFormatter: (v) =>
              v == null ? "—" : `${(v as number).toFixed(1)}h`,
          },
          {
            // Combined meridian / max-altitude cell. When the target
            // transits during astro-dark, max altitude equals the
            // transit altitude — so they render as a single compact
            // line. Otherwise we show both, two lines.
            field: "max_altitude_deg",
            headerName: "Meridian / max alt",
            flex: 1.2,
            minWidth: 150,
            sortable: false,
            renderCell: (p) => {
              const maxAlt = p.row.max_altitude_deg as number | null;
              const peakT = p.row.peak_time_utc as string | null;
              const transitAlt = p.row.altitude_at_transit_deg as number | null;
              const transitT = p.row.transit_time_utc as string | null;
              if (maxAlt == null || peakT == null) {
                return (
                  <Typography variant="body2" color="text.disabled">
                    —
                  </Typography>
                );
              }
              // Collapse when the two agree (transit is inside the
              // astro-dark window): 1° / 1-min tolerance absorbs
              // rounding and sub-minute drift without hiding a real
              // mismatch.
              const matches =
                transitAlt != null &&
                transitT != null &&
                Math.abs(transitAlt - maxAlt) < 0.75 &&
                Math.abs(
                  new Date(transitT).getTime() - new Date(peakT).getTime(),
                ) <
                  60 * 1000;
              if (matches) {
                return (
                  <Typography variant="body2">
                    <Box
                      component="span"
                      sx={{ color: "text.secondary", mr: 0.75 }}
                    >
                      meridian / max alt:
                    </Box>
                    {maxAlt.toFixed(0)}° @ {formatLocalTime(peakT, tz)}
                  </Typography>
                );
              }
              return (
                <Stack spacing={0.15}>
                  {transitAlt != null && transitT != null && (
                    <Typography variant="body2">
                      <Box
                        component="span"
                        sx={{ color: "text.secondary", mr: 0.75 }}
                      >
                        meridian:
                      </Box>
                      {transitAlt.toFixed(0)}° @ {formatLocalTime(transitT, tz)}
                    </Typography>
                  )}
                  <Typography variant="body2">
                    <Box
                      component="span"
                      sx={{ color: "text.secondary", mr: 0.75 }}
                    >
                      max alt:
                    </Box>
                    {maxAlt.toFixed(0)}° @ {formatLocalTime(peakT, tz)}
                  </Typography>
                </Stack>
              );
            },
          },
          {
            field: "min_moon_separation_deg",
            headerName: "Moon sep",
            flex: 0.5,
            minWidth: 70,
            type: "number" as const,
            sortable: false,
            valueFormatter: (v) =>
              v == null ? "—" : `${(v as number).toFixed(0)}°`,
          },
        ] as GridColDef<PlannerTargetItem>[])
      : []),
    {
      field: "constellation",
      headerName: "Const",
      flex: 0.5,
      minWidth: 70,
      sortable: false,
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
            {locationName ? `Tonight from ${locationName}` : "Tonight"}
          </ToggleButton>
          <ToggleButton value="anytime" sx={{ textTransform: "none", px: 2 }}>
            Browse the full catalog
          </ToggleButton>
        </ToggleButtonGroup>
        {restrictTonight && data?.dark_window ? (
          <Stack direction="row" alignItems="center" gap={0.5}>
            <Typography variant="body2" color="text.secondary">
              Astro dark: {formatLocalTime(data.dark_window.start_utc, tz)} –{" "}
              {formatLocalTime(data.dark_window.end_utc, tz)} ·{" "}
              {data.dark_window.hours.toFixed(1)} hours ·
            </Typography>
            <MoonPhaseIcon
              phaseName={data.moon_phase_name ?? "Full Moon"}
              illuminationPct={data.moon_phase_pct}
              sx={{ fontSize: 18, color: "text.secondary" }}
            />
            <Typography variant="body2" color="text.secondary">
              {Math.round(data.moon_phase_pct)}%
            </Typography>
          </Stack>
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
                  // Drop the horizon override so the new location's
                  // default takes over via the effect above.
                  setHorizonId(null);
                  setPagination((p) => ({ ...p, page: 0 }));
                }}
              >
                {locationsQuery.data?.map((l) => (
                  <MenuItem key={l.id} value={l.id}>
                    {l.name}
                  </MenuItem>
                ))}
              </Select>
            </FormControl>
          )}

          {restrictTonight && locationId != null && horizons.length > 0 && (
            <FormControl size="small" sx={{ minWidth: 200 }}>
              <InputLabel>Horizon</InputLabel>
              <Select
                label="Horizon"
                value={horizonId ?? ""}
                onChange={(e) => {
                  setHorizonId(Number(e.target.value));
                  setPagination((p) => ({ ...p, page: 0 }));
                }}
              >
                {horizons.some((h) => h.type === "custom") && [
                  <ListSubheader key="custom-header">Custom</ListSubheader>,
                  ...horizons
                    .filter((h) => h.type === "custom")
                    .map((h) => (
                      <MenuItem key={h.id} value={h.id}>
                        {h.name}
                      </MenuItem>
                    )),
                ]}
                {horizons.some((h) => h.type === "artificial") && [
                  <ListSubheader key="artificial-header">Artificial</ListSubheader>,
                  ...horizons
                    .filter((h) => h.type === "artificial")
                    .map((h) => (
                      <MenuItem key={h.id} value={h.id}>
                        {h.name}
                      </MenuItem>
                    )),
                ]}
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
                // Reset the coverage-range filter to the user's
                // configured default when the rig changes — old
                // bounds won't mean much for a new FOV.
                setCoverageRange(framesWellDefault);
                setCoverageRangeDraft(framesWellDefault);
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

        {/* Pill filter row — Catalog / Object type / Constellation, same
            pattern as the DSO Catalog page. Each is a multi-select OR
            filter. Per-option counts come from the planner's filter-
            aware facet dicts when present; the full option list
            (including zero-count entries for the current filter
            state) comes from ``/api/dso/facets``. Option counts reflect
            the current state with the chip's own dimension held out, so
            users can keep adding selections without the picker
            collapsing to the first choice. */}
        <Stack direction={{ xs: "column", md: "row" }} gap={2} sx={{ mt: 2, flexWrap: "wrap" }}>
          <Box sx={{ width: { xs: "100%", md: 320 } }}>
            <CatalogFilter
              value={catalogFilter}
              onChange={(codes) => {
                setCatalogFilter(codes);
                setPagination((p) => ({ ...p, page: 0 }));
              }}
              options={(facetsQuery.data?.catalogs ?? []).map((c) => ({
                code: c.code,
                count: data?.catalog_counts?.[c.code] ?? c.count,
              }))}
            />
          </Box>
          <Box sx={{ width: { xs: "100%", md: 320 } }}>
            <TypeFilter
              value={typeFilter}
              onChange={(codes) => {
                setTypeFilter(codes);
                setPagination((p) => ({ ...p, page: 0 }));
              }}
              options={(facetsQuery.data?.raw_types ?? []).map((t) => ({
                code: t.code,
                count: data?.raw_type_counts?.[t.code] ?? t.count,
              }))}
            />
          </Box>
          <Box sx={{ width: { xs: "100%", md: 320 } }}>
            <ConstellationFilter
              value={constellationFilter}
              onChange={(codes) => {
                setConstellationFilter(codes);
                setPagination((p) => ({ ...p, page: 0 }));
              }}
              options={(facetsQuery.data?.constellations ?? []).map((c) => ({
                code: c.code,
                count: data?.constellation_counts?.[c.code] ?? c.count,
              }))}
            />
          </Box>
        </Stack>

        {/* Imaging-focused sliders — only meaningful in Tonight mode.
            In Anytime the page behaves like a catalog browser, so
            visibility hours / exposure-time-equivalent magnitude cuts
            / frame size don't belong. */}
        {restrictTonight && (
          <Stack
            direction="row"
            gap={3}
            flexWrap="wrap"
            sx={{ mt: 2, px: 1 }}
          >
            <Box sx={{ width: 160 }}>
              <Typography variant="caption">
                Min hours visible: {minHoursDraft.toFixed(1)}h
              </Typography>
              <Slider
                size="small"
                value={minHoursDraft}
                min={0}
                max={12}
                step={0.5}
                onChange={(_, v) => setMinHoursDraft(v as number)}
                onChangeCommitted={(_, v) => {
                  setMinHours(v as number);
                  setPagination((p) => ({ ...p, page: 0 }));
                }}
              />
            </Box>
            <Box sx={{ width: 160 }}>
              <Typography variant="caption">
                Brighter than mag {maxMagDraft.toFixed(1)}
              </Typography>
              <Slider
                size="small"
                value={maxMagDraft}
                min={5}
                max={18}
                step={0.5}
                onChange={(_, v) => setMaxMagDraft(v as number)}
                onChangeCommitted={(_, v) => {
                  setMaxMag(v as number);
                  setPagination((p) => ({ ...p, page: 0 }));
                }}
              />
            </Box>
            <Box sx={{ width: 160 }}>
              <Typography variant="caption">
                Min size: {minSizeDraft.toFixed(0)}'
              </Typography>
              <Slider
                size="small"
                value={minSizeDraft}
                min={0}
                max={60}
                step={1}
                onChange={(_, v) => setMinSizeDraft(v as number)}
                onChangeCommitted={(_, v) => {
                  setMinSize(v as number);
                  setPagination((p) => ({ ...p, page: 0 }));
                }}
              />
            </Box>
            {/* Gate on the local ``rigId`` (synchronous dropdown state),
                not ``rigFov`` which is derived from the last query
                response — using the response would leave the slider
                visible for one round-trip after the user deselects
                the rig. */}
            {rigId != null && (
              <Box sx={{ width: 180 }}>
                <Tooltip
                  title={
                    "Percentage of the rig's FOV filled by the DSO's angular size. " +
                    "Drag either thumb to narrow or widen the band; 0–200% = no filter."
                  }
                  placement="top"
                  arrow
                >
                  <Typography variant="caption" sx={{ cursor: "help" }}>
                    Size in frame: {coverageRangeDraft[0]}% – {coverageRangeDraft[1]}%
                  </Typography>
                </Tooltip>
                <Slider
                  size="small"
                  value={coverageRangeDraft}
                  min={0}
                  max={200}
                  step={5}
                  disableSwap
                  onChange={(_, v) =>
                    setCoverageRangeDraft(v as [number, number])
                  }
                  onChangeCommitted={(_, v) => {
                    setCoverageRange(v as [number, number]);
                    setPagination((p) => ({ ...p, page: 0 }));
                  }}
                />
              </Box>
            )}
          </Stack>
        )}

        <PlannerSortPanel
          sortBy={sortBy}
          onSortChange={(next) => {
            setSortBy(next);
            setPagination((p) => ({ ...p, page: 0 }));
          }}
          restrictTonight={restrictTonight}
          rigSelected={rigId != null}
        />
      </Paper>

      {/* Empty / error states — only relevant in Tonight mode; in
          Anytime there's no location/date, so the concept doesn't
          apply. */}
      {restrictTonight &&
        targetsQuery.data?.dark_window === null &&
        targetsQuery.data.location && (
          <Alert severity="info">
            It doesn't get astronomically dark tonight at{" "}
            {targetsQuery.data.location.name} — summer twilight at high
            latitude. Try another night or location.
          </Alert>
        )}

      {/* Grid */}
      <Paper variant="outlined" sx={{ flex: 1, minHeight: 0, position: "relative" }}>
        {/* Custom fetch overlay. ``loading`` on the DataGrid is NOT
            used because MUI X Community renders a linear-progress
            bar inside the column-header row during re-fetches with
            existing data — that bar peeks through as clipped text
            and ignores ``slots.loadingOverlay``. Rolling our own
            overlay on the Paper wrapper sidesteps it entirely. */}
        {(targetsQuery.isLoading || targetsQuery.isFetching) && (
          <Stack
            alignItems="center"
            justifyContent="center"
            gap={1.5}
            sx={{
              position: "absolute",
              inset: 0,
              bgcolor: "background.paper",
              zIndex: 2,
              pointerEvents: "none",
            }}
          >
            <CircularProgress size={32} thickness={4} />
            <Typography variant="body2" color="text.secondary">
              Loading…
            </Typography>
          </Stack>
        )}
        <DataGrid
          rows={data?.items ?? []}
          getRowId={(row) => row.dso_id}
          columns={columns}
          paginationMode="server"
          // Sort is entirely owned by the Sorting panel (server-side
          // sort via the ``sort`` query param). The DataGrid has no
          // sort responsibility — disable column-header sort entirely
          // so there's no duplicate UI and no risk of MUI's internal
          // sortModel reconciliation clobbering the panel's state.
          disableColumnSorting
          rowCount={data?.total ?? 0}
          paginationModel={pagination}
          onPaginationModelChange={setPagination}
          pageSizeOptions={[25, 50, 100]}
          getRowHeight={() => "auto"}
          slotProps={{
            basePagination: {
              ActionsComponent: PaginationActions,
              // eslint-disable-next-line @typescript-eslint/no-explicit-any
            } as any,
          }}
          onRowClick={(params: GridRowParams<PlannerTargetItem>) =>
            setDetailId(params.row.dso_id)
          }
          disableRowSelectionOnClick
          slots={{
            loadingOverlay: GridLoadingOverlay,
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
        selectedHorizonId={horizonId}
        selectedRigId={rigId}
        rigs={rigsQuery.data ?? []}
        onSelectDso={(id) => setDetailId(id)}
        onClose={() => setDetailId(null)}
      />
    </Box>
  );
}
