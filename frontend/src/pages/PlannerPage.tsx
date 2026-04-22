/**
 * Target Planner.
 *
 * Two modes: "Tonight from {location}" (location-aware, visibility +
 * moon context) and "Browse the full catalog" (no location / no
 * visibility, acts as a DSO catalog browser). Optional rig selection
 * adds a rig-framed thumbnail on each card plus a coverage-range
 * filter ("Size in frame"). Row click opens ``PlannerDetailPanel``.
 */
import { useEffect, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import Alert from "@mui/material/Alert";
import Box from "@mui/material/Box";
import CircularProgress from "@mui/material/CircularProgress";
import TablePagination from "@mui/material/TablePagination";
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
import CloseIcon from "@mui/icons-material/Close";
import CloudDownloadOutlinedIcon from "@mui/icons-material/CloudDownloadOutlined";
import PlaceOutlinedIcon from "@mui/icons-material/PlaceOutlined";
import SearchIcon from "@mui/icons-material/Search";
import { Link as RouterLink } from "react-router-dom";
import { fetchLocations } from "@/api/locations";
import { fetchRigs } from "@/api/rigs";
import { fetchDsoFacets } from "@/api/dsos";
import { fetchHorizons, type Horizon } from "@/api/horizons";
import PlannerSortPanel from "@/components/planner/PlannerSortPanel";
import { renderHorizonMenuItems } from "@/components/planner/horizonMenuItems";
import { serializeSort } from "@/lib/plannerSortFields";
import { fetchPlannerTargets } from "@/api/planner";
import { useSettingsStore } from "@/stores/settingsStore";
import { usePlannerStore } from "@/stores/plannerStore";
import { useDebounce } from "@/lib/useDebounce";
import PaginationActions from "@/components/common/PaginationActions";
import MoonPhaseIcon from "@/components/weather/MoonPhaseIcon";
import CatalogFilter from "@/components/dso/CatalogFilter";
import ConstellationFilter from "@/components/dso/ConstellationFilter";
import TypeFilter from "@/components/dso/TypeFilter";
import PlannerTargetCard from "@/components/planner/PlannerTargetCard";
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
  const [pagination, setPagination] = useState<{ page: number; pageSize: number }>({
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

  const rigFovMajorDeg = data?.rig?.fov_major_deg ?? null;
  const rigFovMinorDeg = data?.rig?.fov_minor_deg ?? null;


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
                {renderHorizonMenuItems(horizons)}
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

      {/* Card list — one card per DSO, server-side paginated. The
          MUI X DataGrid that lived here was replaced with a simple
          stack of cards: the grid no longer owned sort (panel does)
          or row-click semantics (``CardActionArea`` on each card
          does), and the column layout wasted horizontal space for
          the data density we actually want. */}
      <Paper
        variant="outlined"
        sx={{ flex: 1, minHeight: 0, position: "relative", overflow: "auto" }}
      >
        {/* Opaque loading overlay on the Paper — covers the card
            stack during sort / filter refetches so prior rows don't
            bleed through. */}
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

        {data?.items && data.items.length > 0 ? (
          <Box sx={{ p: 1.5 }}>
            <Stack gap={1.25}>
              {data.items.map((item) => (
                <PlannerTargetCard
                  key={item.dso_id}
                  item={item}
                  rigFovMajorDeg={rigFovMajorDeg}
                  rigFovMinorDeg={rigFovMinorDeg}
                  tz={tz}
                  restrictTonight={restrictTonight}
                  onClick={setDetailId}
                />
              ))}
            </Stack>
            <TablePagination
              component="div"
              count={data.total}
              page={pagination.page}
              onPageChange={(_, newPage) =>
                setPagination((p) => ({ ...p, page: newPage }))
              }
              rowsPerPage={pagination.pageSize}
              onRowsPerPageChange={(e) =>
                setPagination({ page: 0, pageSize: parseInt(e.target.value, 10) })
              }
              rowsPerPageOptions={[25, 50, 100]}
              labelRowsPerPage="Cards per page:"
              ActionsComponent={PaginationActions}
              sx={{ mt: 1, borderTop: 1, borderColor: "divider" }}
            />
          </Box>
        ) : (
          !targetsQuery.isLoading &&
          !targetsQuery.isFetching && (
            <Stack
              alignItems="center"
              justifyContent="center"
              sx={{ height: "100%", px: 3, py: 6, textAlign: "center" }}
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
          )
        )}
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
