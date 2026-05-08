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
import Checkbox from "@mui/material/Checkbox";
import CircularProgress from "@mui/material/CircularProgress";
import Collapse from "@mui/material/Collapse";
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
import ExpandLessIcon from "@mui/icons-material/ExpandLess";
import ExpandMoreIcon from "@mui/icons-material/ExpandMore";
import PlaceOutlinedIcon from "@mui/icons-material/PlaceOutlined";
import SearchIcon from "@mui/icons-material/Search";
import TuneIcon from "@mui/icons-material/Tune";
import { Link as RouterLink } from "react-router-dom";
import { fetchLocations } from "@/api/locations";
import { fetchRigs } from "@/api/rigs";
import { fetchDsoFacets } from "@/api/dsos";
import { fetchHorizons, type Horizon } from "@/api/horizons";
import PlannerSortPanel from "@/components/planner/PlannerSortPanel";
import { renderHorizonMenuItems } from "@/components/planner/horizonMenuItems";
import { serializeSort } from "@/lib/plannerSortFields";
import { fetchPlannerTargets } from "@/api/planner";
import { FilterIntentSelect } from "@/components/planner/FilterIntentSelect";
import { useSettingsStore } from "@/stores/settingsStore";
import { usePlannerStore } from "@/stores/plannerStore";
import { usePlannerSettingsSync } from "@/lib/usePlannerSettingsSync";
import { useDebounce } from "@/lib/useDebounce";
import PaginationActions from "@/components/common/PaginationActions";
import MoonPhaseIcon from "@/components/weather/MoonPhaseIcon";
import CatalogFilter from "@/components/dso/CatalogFilter";
import ConstellationFilter from "@/components/dso/ConstellationFilter";
import TypeFilter from "@/components/dso/TypeFilter";
import PlannerTargetCard from "@/components/planner/PlannerTargetCard";
import PlannerDetailPanel from "@/components/planner/PlannerDetailPanel";
import WishlistTab from "@/components/planner/WishlistTab";
import { useFavoriteIds, useAddFavorite, useRemoveFavorite } from "@/api/wishlist";

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
  // Bridges the in-memory zustand store with the database-backed
  // settings — hydrates on mount and pushes changes back.
  usePlannerSettingsSync();
  const settings = useSettingsStore((s) => s.settings);
  const locationId = usePlannerStore((s) => s.selectedLocationId);
  const setLocationId = usePlannerStore((s) => s.setSelectedLocationId);
  const horizonId = usePlannerStore((s) => s.selectedHorizonId);
  const setHorizonId = usePlannerStore((s) => s.setSelectedHorizonId);
  const rigId = usePlannerStore((s) => s.selectedRigId);
  const setRigId = usePlannerStore((s) => s.setSelectedRigId);
  const sortBy = usePlannerStore((s) => s.sortBy);
  const setSortBy = usePlannerStore((s) => s.setSortBy);
  const filterIntent = usePlannerStore((s) => s.filterIntent);
  const setFilterIntent = usePlannerStore((s) => s.setFilterIntent);
  const searchQuery = usePlannerStore((s) => s.searchQuery);
  const setSearchQuery = usePlannerStore((s) => s.setSearchQuery);
  const activeTab = usePlannerStore((s) => s.activeTab);
  const setActiveTab = usePlannerStore((s) => s.setActiveTab);
  const restrictTonight = activeTab === "tonight";
  const typeFilter = usePlannerStore((s) => s.typeFilter);
  const setTypeFilter = usePlannerStore((s) => s.setTypeFilter);
  const catalogFilter = usePlannerStore((s) => s.catalogFilter);
  const setCatalogFilter = usePlannerStore((s) => s.setCatalogFilter);
  const constellationFilter = usePlannerStore((s) => s.constellationFilter);
  const setConstellationFilter = usePlannerStore((s) => s.setConstellationFilter);
  const detailId = usePlannerStore((s) => s.detailId);
  const setDetailId = usePlannerStore((s) => s.setDetailId);
  const [filtersOpen, setFiltersOpen] = useState<boolean>(true);
  const { data: favoriteIds } = useFavoriteIds();
  const addFavorite = useAddFavorite();
  const removeFav = useRemoveFavorite();
  const handleToggleFavorite = (dsoId: number) => {
    if (favoriteIds?.has(dsoId)) {
      removeFav.mutate(dsoId);
    } else {
      addFavorite.mutate(dsoId);
    }
  };

  const storeMinHours = usePlannerStore((s) => s.minHours);
  const storeSetMinHours = usePlannerStore((s) => s.setMinHours);
  const storeMaxMag = usePlannerStore((s) => s.maxMag);
  const storeSetMaxMag = usePlannerStore((s) => s.setMaxMag);
  const storeMinSize = usePlannerStore((s) => s.minSize);
  const storeSetMinSize = usePlannerStore((s) => s.setMinSize);
  const storeCoverageRange = usePlannerStore((s) => s.coverageRange);
  const storeSetCoverageRange = usePlannerStore((s) => s.setCoverageRange);

  const minHours = storeMinHours ?? settings?.planner_min_visibility_hours ?? 2.0;
  const setMinHours = (v: number) => storeSetMinHours(v);
  const [minHoursDraft, setMinHoursDraft] = useState<number>(minHours);
  const maxMag = storeMaxMag ?? settings?.planner_max_magnitude ?? 12.0;
  const setMaxMag = (v: number) => storeSetMaxMag(v);
  const [maxMagDraft, setMaxMagDraft] = useState<number>(maxMag);
  const minSize = storeMinSize ?? settings?.planner_min_size_arcmin ?? 5.0;
  const setMinSize = (v: number) => storeSetMinSize(v);
  const [minSizeDraft, setMinSizeDraft] = useState<number>(minSize);

  const framesWellDefault: [number, number] = [
    settings?.planner_frames_well_min_pct ?? 15,
    settings?.planner_frames_well_max_pct ?? 90,
  ];
  const coverageRange = storeCoverageRange ?? framesWellDefault;
  const setCoverageRange = (v: [number, number]) => storeSetCoverageRange(v);
  const [coverageRangeDraft, setCoverageRangeDraft] =
    useState<[number, number]>(coverageRange);
  const [filtersSubOpen, setFiltersSubOpen] = useState(true);
  const [hoursEnabled, setHoursEnabled] = useState(true);
  const [magEnabled, setMagEnabled] = useState(false);
  const [sizeEnabled, setSizeEnabled] = useState(false);
  const [coverageEnabled, setCoverageEnabled] = useState(false);
  const [pagination, setPagination] = useState<{ page: number; pageSize: number }>({
    page: 0,
    pageSize: DEFAULT_PAGE_SIZE,
  });
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
        hoursEnabled,
        minHours,
        magEnabled,
        maxMag,
        sizeEnabled,
        minSize,
        coverageEnabled,
        coverageRange,
        q: debouncedSearch || null,
        restrictTonight,
        limit: pagination.pageSize,
        offset: pagination.page * pagination.pageSize,
        sortParam,
        filterIntent,
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
        min_hours: restrictTonight && hoursEnabled ? minHours : null,
        max_magnitude: magEnabled ? maxMag : null,
        min_size_arcmin: sizeEnabled ? minSize : null,
        coverage_min_pct:
          coverageEnabled && coverageRange[0] > 0 ? coverageRange[0] : null,
        coverage_max_pct:
          coverageEnabled && coverageRange[1] < 200 ? coverageRange[1] : null,
        q: debouncedSearch || null,
        restrict_tonight: restrictTonight,
        limit: pagination.pageSize,
        offset: pagination.page * pagination.pageSize,
        sort: sortParam,
        // Tonight-only input — backend ignores in Anytime mode per
        // its contract, but we still gate here so the query key
        // doesn't diverge uselessly between modes.
        filter_intent: restrictTonight ? filterIntent : undefined,
      }),
    // Tonight mode is location-dependent; Anytime runs without one.
    enabled: !restrictTonight || (locationId != null && horizonId != null),
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
          value={activeTab}
          onChange={(_, v) => {
            if (v === null) return;
            setActiveTab(v);
            setPagination((p) => ({ ...p, page: 0 }));
          }}
          aria-label="Planner scope"
        >
          <Tooltip title="Objects visible tonight during astronomical darkness from your selected location, filtered by hours, magnitude, size, and scored for imaging quality" arrow>
            <ToggleButton value="tonight" sx={{ textTransform: "none", px: 2 }}>
              {locationName ? `Tonight from ${locationName}` : "Tonight"}
            </ToggleButton>
          </Tooltip>
          <Tooltip title="Browse all objects in the DSO catalog regardless of location, date, or visibility — no scoring, no tonight-specific filters" arrow>
            <ToggleButton value="anytime" sx={{ textTransform: "none", px: 2 }}>
              Full Catalog
            </ToggleButton>
          </Tooltip>
          <Tooltip title="Your starred targets — assign locations, rigs, and imaging windows" arrow>
            <ToggleButton value="wishlist" sx={{ textTransform: "none", px: 2 }}>
              Wishlist
            </ToggleButton>
          </Tooltip>
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

      {activeTab === "wishlist" ? (
        <Paper
          variant="outlined"
          sx={{ flex: 1, minHeight: 0, overflow: "auto", borderRadius: 2 }}
        >
          <WishlistTab />
        </Paper>
      ) : plannerEmptyState !== null ? (
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
      {/* Filter bar — collapsible. The header row below always renders
          (with the toggle chevron); the pill / slider / sort content is
          wrapped in a ``Collapse`` so the card list can breathe once
          the user has dialled in their filters. Session-only state; a
          reload opens the bar back up. */}
      <Paper variant="outlined" sx={{ px: 2, py: filtersOpen ? 2 : 0.75 }}>
        <Stack
          direction="row"
          alignItems="center"
          justifyContent="space-between"
          gap={1}
          sx={{ mb: filtersOpen ? 2 : 0 }}
        >
          <Stack direction="row" alignItems="center" gap={1}>
            <TuneIcon fontSize="small" sx={{ color: "text.secondary" }} />
            <Typography variant="subtitle2" fontWeight={600}>
              Settings
            </Typography>
          </Stack>
          <Tooltip
            title={filtersOpen ? "Collapse controls" : "Expand controls"}
            placement="top"
            arrow
          >
            <IconButton
              size="small"
              onClick={() => setFiltersOpen((v) => !v)}
              aria-expanded={filtersOpen}
              aria-label={filtersOpen ? "Collapse filters" : "Expand filters"}
            >
              {filtersOpen ? <ExpandLessIcon /> : <ExpandMoreIcon />}
            </IconButton>
          </Tooltip>
        </Stack>
        <Collapse in={filtersOpen} unmountOnExit>
        {/* Row 1: Location + Horizon + Rig (with FOV) + Filter intent */}
        <Stack direction="row" gap={2} flexWrap="wrap" alignItems="flex-start">
          {restrictTonight && (
            <FormControl size="small" sx={{ minWidth: { xs: 140, sm: 180 } }}>
              <InputLabel>Location</InputLabel>
              <Select
                label="Location"
                value={locationId ?? ""}
                onChange={(e) => {
                  const v = String(e.target.value);
                  setLocationId(v === "" ? null : Number(v));
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
            <FormControl size="small" sx={{ minWidth: { xs: 130, sm: 160 } }}>
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

          <Box>
            <FormControl size="small" sx={{ minWidth: { xs: 140, sm: 180 } }}>
              <InputLabel>Rig</InputLabel>
              <Select
                label="Rig"
                value={rigId ?? ""}
                onChange={(e) => {
                  const v = String(e.target.value);
                  setRigId(v === "" ? null : Number(v));
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
            {rigFov && (
              <Typography variant="caption" color="text.secondary" display="block" sx={{ mt: 0.25 }}>
                FOV: {rigFov}
              </Typography>
            )}
          </Box>

          {restrictTonight && (
            <FilterIntentSelect
              value={filterIntent}
              onChange={(next) => {
                setFilterIntent(next);
                setPagination((p) => ({ ...p, page: 0 }));
              }}
            />
          )}

        </Stack>

        {/* Filters subsection — collapsible */}
        <Box sx={{ mt: 2, bgcolor: "action.hover", borderRadius: 1, px: 1.5, py: filtersSubOpen ? 1.5 : 0.5 }}>
        <Stack
          direction="row"
          alignItems="center"
          justifyContent="space-between"
          sx={{ cursor: "pointer", mb: filtersSubOpen ? 1.5 : 0 }}
          onClick={() => setFiltersSubOpen((v) => !v)}
        >
          <Typography variant="body2" fontWeight={500}>
            Filters
          </Typography>
          <IconButton size="small" aria-label={filtersSubOpen ? "Collapse filters" : "Expand filters"}>
            {filtersSubOpen ? <ExpandLessIcon /> : <ExpandMoreIcon />}
          </IconButton>
        </Stack>
        <Collapse in={filtersSubOpen} unmountOnExit>
        <Stack direction="row" gap={2} sx={{ flexWrap: "wrap", alignItems: "flex-start" }}>
          <TextField
            size="small"
            placeholder="Search (M42, NGC 1976, Orion Nebula…)"
            value={searchQuery}
            onChange={(e) => {
              setSearchQuery(e.target.value);
              setPagination((p) => ({ ...p, page: 0 }));
            }}
            sx={{ width: { xs: "100%", sm: 280 } }}
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
          <Box sx={{ width: { xs: "100%", sm: 220 } }}>
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
          <Box sx={{ width: { xs: "100%", sm: 220 } }}>
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
          <Box sx={{ width: { xs: "100%", sm: 220 } }}>
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

        <Stack
          direction="row"
          gap={3}
          flexWrap="wrap"
          sx={{ mt: 2 }}
        >
          {restrictTonight && (
            <Box sx={{ width: { xs: "100%", sm: 180 } }}>
              <Stack direction="row" alignItems="center">
                <Checkbox
                  size="small"
                  checked={hoursEnabled}
                  onChange={(_, checked) => {
                    setHoursEnabled(checked);
                    setPagination((p) => ({ ...p, page: 0 }));
                  }}
                  sx={{ p: 0.25, ml: -0.5 }}
                />
                <Typography
                  variant="caption"
                  sx={{ color: hoursEnabled ? "text.primary" : "text.disabled" }}
                >
                  Min hours visible: {minHoursDraft.toFixed(1)}h
                </Typography>
              </Stack>
              <Slider
                size="small"
                disabled={!hoursEnabled}
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
          )}
          <Box sx={{ width: { xs: "100%", sm: 180 } }}>
            <Stack direction="row" alignItems="center">
              <Checkbox
                size="small"
                checked={magEnabled}
                onChange={(_, checked) => {
                  setMagEnabled(checked);
                  setPagination((p) => ({ ...p, page: 0 }));
                }}
                sx={{ p: 0.25 }}
              />
              <Typography
                variant="caption"
                sx={{ color: magEnabled ? "text.primary" : "text.disabled" }}
              >
                Brighter than mag {maxMagDraft.toFixed(1)}
              </Typography>
            </Stack>
            <Slider
              size="small"
              disabled={!magEnabled}
              value={-maxMagDraft}
              min={-18}
              max={0}
              step={0.5}
              scale={(v) => -v}
              onChange={(_, v) => setMaxMagDraft(-(v as number))}
              onChangeCommitted={(_, v) => {
                setMaxMag(-(v as number));
                setPagination((p) => ({ ...p, page: 0 }));
              }}
            />
          </Box>
          <Box sx={{ width: { xs: "100%", sm: 180 } }}>
            <Stack direction="row" alignItems="center">
              <Checkbox
                size="small"
                checked={sizeEnabled}
                onChange={(_, checked) => {
                  setSizeEnabled(checked);
                  setPagination((p) => ({ ...p, page: 0 }));
                }}
                sx={{ p: 0.25 }}
              />
              <Typography
                variant="caption"
                sx={{ color: sizeEnabled ? "text.primary" : "text.disabled" }}
              >
                Min size: {minSizeDraft.toFixed(0)}'
              </Typography>
            </Stack>
            <Slider
              size="small"
              disabled={!sizeEnabled}
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
          {rigId != null && (
            <Box sx={{ width: { xs: "100%", sm: 200 } }}>
              <Tooltip
                title={
                  "Percentage of the rig's FOV filled by the DSO's angular size. " +
                  "Uncheck to disable this filter entirely."
                }
                placement="top"
                arrow
              >
                <Stack direction="row" alignItems="center">
                  <Checkbox
                    size="small"
                    checked={coverageEnabled}
                    onChange={(_, checked) => {
                      setCoverageEnabled(checked);
                      setPagination((p) => ({ ...p, page: 0 }));
                    }}
                    sx={{ p: 0.25, ml: -0.5 }}
                  />
                  <Typography
                    variant="caption"
                    sx={{
                      cursor: "help",
                      color: coverageEnabled ? "text.primary" : "text.disabled",
                    }}
                  >
                    Size in frame: {coverageRangeDraft[0]}% – {coverageRangeDraft[1]}%
                  </Typography>
                </Stack>
              </Tooltip>
              <Slider
                size="small"
                disabled={!coverageEnabled}
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
          {catalogFiltersActive && (
            <Box sx={{ width: "100%", display: "flex", justifyContent: "flex-end" }}>
              <Button size="small" variant="text" onClick={clearCatalogFilters}>
                Clear filters
              </Button>
            </Box>
          )}
        </Stack>
        </Collapse>
        </Box>

        <PlannerSortPanel
          sortBy={sortBy}
          onSortChange={(next) => {
            setSortBy(next);
            setPagination((p) => ({ ...p, page: 0 }));
          }}
          restrictTonight={restrictTonight}
          rigSelected={rigId != null}
        />
        </Collapse>
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
        sx={{ position: "relative" }}
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
                  isFavorite={favoriteIds?.has(item.dso_id)}
                  onToggleFavorite={handleToggleFavorite}
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
