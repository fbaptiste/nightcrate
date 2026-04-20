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
  type GridSortModel,
  type GridRowParams,
} from "@mui/x-data-grid";
import Alert from "@mui/material/Alert";
import Box from "@mui/material/Box";
import Checkbox from "@mui/material/Checkbox";
import Chip from "@mui/material/Chip";
import FormControl from "@mui/material/FormControl";
import FormControlLabel from "@mui/material/FormControlLabel";
import InputLabel from "@mui/material/InputLabel";
import MenuItem from "@mui/material/MenuItem";
import Paper from "@mui/material/Paper";
import Select from "@mui/material/Select";
import Slider from "@mui/material/Slider";
import Stack from "@mui/material/Stack";
import Tooltip from "@mui/material/Tooltip";
import Typography from "@mui/material/Typography";
import { fetchLocations } from "@/api/locations";
import { fetchRigs } from "@/api/rigs";
import { fetchDsoFacets } from "@/api/dsos";
import {
  fetchPlannerTargets,
  type PlannerTargetItem,
} from "@/api/planner";
import { useSettingsStore } from "@/stores/settingsStore";
import { usePlannerStore } from "@/stores/plannerStore";
import { typeGroupStyle } from "@/lib/dsoTypeGroups";
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
  const [typeGroupFilter, setTypeGroupFilter] = useState<string[]>([]);
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

  const targetsQuery = useQuery({
    queryKey: [
      "planner-targets",
      {
        locationId,
        rigId,
        typeGroupFilter,
        minHours,
        maxMag,
        minSize,
        framesWell,
        limit: pagination.pageSize,
        offset: pagination.page * pagination.pageSize,
        sortField,
        sortDir,
      },
    ],
    queryFn: () =>
      fetchPlannerTargets({
        location_id: locationId!,
        rig_id: rigId,
        type_group: typeGroupFilter,
        min_hours: minHours,
        max_magnitude: maxMag,
        min_size_arcmin: minSize,
        frames_well: framesWell,
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

  const activeLocation = locationsQuery.data?.find((l) => l.id === locationId);
  const tz = activeLocation?.timezone ?? "UTC";
  const locationName = activeLocation?.name ?? null;
  const data = targetsQuery.data;
  const rigFov = data?.rig
    ? `${(data.rig.fov_major_deg * 60).toFixed(1)}' × ${(data.rig.fov_minor_deg * 60).toFixed(1)}'`
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
    {
      field: "hours_visible",
      headerName: "Hours",
      flex: 0.4,
      minWidth: 60,
      type: "number",
      valueFormatter: (v) => `${(v as number).toFixed(1)}h`,
    },
    {
      field: "max_altitude_deg",
      headerName: "Max altitude",
      flex: 1.0,
      minWidth: 120,
      type: "number",
      renderCell: (p) => (
        <Typography variant="body2">
          {(p.row.max_altitude_deg as number).toFixed(0)}° @{" "}
          {formatLocalTime(p.row.peak_time_utc, tz)}
        </Typography>
      ),
    },
    {
      field: "transit",
      headerName: "Meridian",
      flex: 1.0,
      minWidth: 120,
      sortable: false,
      renderCell: (p) => {
        const alt = p.row.altitude_at_transit_deg;
        const t = p.row.transit_time_utc;
        if (alt == null || t == null) {
          return <Typography variant="body2" color="text.disabled">—</Typography>;
        }
        return (
          <Typography variant="body2">
            {(alt as number).toFixed(0)}° @ {formatLocalTime(t, tz)}
          </Typography>
        );
      },
    },
    {
      field: "min_moon_separation_deg",
      headerName: "Moon",
      flex: 0.4,
      minWidth: 60,
      type: "number",
      valueFormatter: (v) => (v == null ? "—" : `${(v as number).toFixed(0)}°`),
    },
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
      {/* Header */}
      <Stack direction="row" alignItems="center" gap={2} flexWrap="wrap">
        <Typography variant="h5" fontWeight={600}>
          Target Planner
        </Typography>
        {data?.dark_window ? (
          <Typography variant="body2" color="text.secondary">
            Astro dark: {formatLocalTime(data.dark_window.start_utc, tz)} –{" "}
            {formatLocalTime(data.dark_window.end_utc, tz)} · {data.dark_window.hours.toFixed(1)}{" "}
            hours · Moon {Math.round(data.moon_phase_pct)}%
          </Typography>
        ) : null}
      </Stack>

      {/* Filter bar */}
      <Paper variant="outlined" sx={{ p: 2 }}>
        <Stack direction={{ xs: "column", md: "row" }} gap={2} flexWrap="wrap">
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

          {rigFov && (
            <Typography variant="caption" color="text.secondary" alignSelf="center">
              FOV: {rigFov}
            </Typography>
          )}
        </Stack>

        {/* Type group chips */}
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
                  label={g.name}
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

        {/* Sliders */}
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
      </Paper>

      {/* Empty / error states */}
      {targetsQuery.data?.dark_window === null && (
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
          onSortModelChange={setSortModel}
          pageSizeOptions={[25, 50, 100]}
          getRowHeight={() => "auto"}
          onRowClick={(params: GridRowParams<PlannerTargetItem>) =>
            setDetailId(params.row.dso_id)
          }
          disableRowSelectionOnClick
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
          }}
        />
      </Paper>

      <PlannerDetailPanel
        dsoId={detailId}
        target={data?.items.find((i) => i.dso_id === detailId) ?? null}
        locationId={locationId}
        locationName={locationName}
        rigFov={data?.rig ? [data.rig.fov_major_deg, data.rig.fov_minor_deg] : null}
        rigName={data?.rig?.name ?? null}
        tz={tz}
        onClose={() => setDetailId(null)}
      />
    </Box>
  );
}
