import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import {
  DataGrid,
  type GridColDef,
  type GridPaginationModel,
  type GridSortModel,
  type GridRowParams,
} from "@mui/x-data-grid";
import Box from "@mui/material/Box";
import Button from "@mui/material/Button";
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
import Stack from "@mui/material/Stack";
import TextField from "@mui/material/TextField";
import Tooltip from "@mui/material/Tooltip";
import Typography from "@mui/material/Typography";
import CloseIcon from "@mui/icons-material/Close";
import CloudDownloadOutlinedIcon from "@mui/icons-material/CloudDownloadOutlined";
import InfoOutlinedIcon from "@mui/icons-material/InfoOutlined";
import SearchIcon from "@mui/icons-material/Search";
import { Link as RouterLink } from "react-router-dom";
import { fetchDsoFacets, fetchDsos, type DsoListItem } from "@/api/dsos";
import { useDebounce } from "@/lib/useDebounce";
import PaginationActions from "@/components/common/PaginationActions";
import DsoAttributionPanel from "@/components/dso/DsoAttributionPanel";
import DsoDetailPanel from "@/components/dso/DsoDetailPanel";
import { displayConstellation } from "@/lib/constellations";
import { formatDistance } from "@/lib/distanceFormat";
import { displayDsoType, dsoTypeColor } from "@/lib/dsoTypeNames";
import { typeGroupStyle } from "@/lib/dsoTypeGroups";
import {
  formatDec,
  formatMagnitude,
  formatRa,
  formatSize,
} from "@/lib/dsoFormatters";

const DEFAULT_PAGE_SIZE = 100;

export default function DsoCatalogPage() {
  const [query, setQuery] = useState("");
  const debouncedQuery = useDebounce(query, 300);

  const [typeGroupFilter, setTypeGroupFilter] = useState<string[]>([]);
  const [typeFilter, setTypeFilter] = useState<string[]>([]);
  const [constellation, setConstellation] = useState<string>("");
  const [hasDistance, setHasDistance] = useState(false);
  const [advancedOpen, setAdvancedOpen] = useState(false);
  const [pagination, setPagination] = useState<GridPaginationModel>({
    page: 0,
    pageSize: DEFAULT_PAGE_SIZE,
  });
  const [sortModel, setSortModel] = useState<GridSortModel>([
    { field: "primary_designation", sort: "asc" },
  ]);
  const [detailId, setDetailId] = useState<number | null>(null);
  const [attributionOpen, setAttributionOpen] = useState(false);

  const sort = sortModel[0]?.field ?? "primary_designation";
  const sortDir = (sortModel[0]?.sort ?? "asc") as "asc" | "desc";

  const listParams = {
    q: debouncedQuery || null,
    type: typeFilter,
    type_group: typeGroupFilter,
    constellation: constellation || null,
    has_distance: hasDistance ? true : null,
    limit: pagination.pageSize,
    offset: pagination.page * pagination.pageSize,
    sort,
    sort_dir: sortDir,
  };

  const listQuery = useQuery({
    queryKey: ["dsos", listParams],
    queryFn: () => fetchDsos(listParams),
    placeholderData: (previous) => previous,
  });

  const facetsQuery = useQuery({
    queryKey: ["dso-facets"],
    queryFn: fetchDsoFacets,
    staleTime: 5 * 60_000,
  });

  const toggleType = (objType: string) => {
    setTypeFilter((current) =>
      current.includes(objType)
        ? current.filter((t) => t !== objType)
        : [...current, objType],
    );
    setPagination((p) => ({ ...p, page: 0 }));
  };

  const toggleTypeGroup = (groupName: string) => {
    setTypeGroupFilter((current) =>
      current.includes(groupName)
        ? current.filter((g) => g !== groupName)
        : [...current, groupName],
    );
    setPagination((p) => ({ ...p, page: 0 }));
  };

  const clearFilters = () => {
    setQuery("");
    setTypeFilter([]);
    setTypeGroupFilter([]);
    setConstellation("");
    setHasDistance(false);
    setPagination((p) => ({ ...p, page: 0 }));
  };

  const filtersActive =
    debouncedQuery ||
    typeFilter.length > 0 ||
    typeGroupFilter.length > 0 ||
    constellation ||
    hasDistance;

  // The empty-state CTA fires only when the backend has zero DSOs total AND
  // the user isn't filtering — a filter returning zero rows is a different
  // (and legitimate) state that the DataGrid already handles.
  const showEmptyCatalogCta =
    !listQuery.isLoading &&
    !listQuery.isFetching &&
    (listQuery.data?.total ?? 0) === 0 &&
    !filtersActive;

  const columns: GridColDef<DsoListItem>[] = [
    {
      field: "primary_designation",
      headerName: "Designation",
      width: 140,
      renderCell: (params) => (
        <Typography variant="body2" fontWeight={600}>
          {params.value}
        </Typography>
      ),
    },
    {
      field: "obj_type",
      headerName: "Type",
      width: 150,
      renderCell: (params) => (
        <Chip
          label={displayDsoType(params.value as string)}
          size="small"
          sx={{
            bgcolor: dsoTypeColor(params.value as string),
            color: "#ffffff",
            fontWeight: 500,
          }}
        />
      ),
    },
    {
      field: "constellation",
      headerName: "Constellation",
      width: 150,
      valueFormatter: (value) => displayConstellation(value as string | null),
    },
    {
      field: "ra_deg",
      headerName: "RA",
      width: 130,
      valueFormatter: (value) => formatRa(value as number | null),
    },
    {
      field: "dec_deg",
      headerName: "Dec",
      width: 130,
      valueFormatter: (value) => formatDec(value as number | null),
    },
    {
      field: "size",
      headerName: "Size",
      width: 110,
      // Backend sorts by `maj_axis_arcmin` for this field (see SORT_COLUMNS
      // in api/dso.py). The displayed value is still the full `a × b` form.
      sortable: true,
      valueGetter: (_value, row) =>
        formatSize(row.maj_axis_arcmin, row.min_axis_arcmin),
    },
    {
      field: "mag_v",
      headerName: "Mag V",
      width: 80,
      type: "number",
      valueFormatter: (value) => formatMagnitude(value as number | null),
    },
    {
      field: "distance_pc",
      headerName: "Distance",
      width: 110,
      type: "number",
      valueFormatter: (value) => formatDistance(value as number | null)?.primary ?? "",
    },
    {
      field: "common_name",
      headerName: "Common name",
      flex: 1,
      minWidth: 180,
      valueFormatter: (value) => value ?? "—",
    },
    {
      field: "designations",
      headerName: "Alt designations",
      width: 200,
      sortable: false,
      valueGetter: (_v, row) => {
        const secondary = row.designations.filter((d) => !d.is_primary);
        if (secondary.length === 0) return "—";
        const head = secondary.slice(0, 2).map((d) => d.display_form).join(", ");
        const extra = secondary.length - 2;
        return extra > 0 ? `${head}, +${extra} more` : head;
      },
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
        // Prevent the outer container from ever scrolling — the DataGrid
        // handles its own internal scroll. Without this, a sub-pixel height
        // mismatch between this Box and its parent <main> triggers the
        // native macOS scrollbar intermittently on hover, which reflows
        // layout, which hides the scrollbar, which reflows again…
        overflow: "hidden",
      }}
    >
      {/* Header */}
      <Stack direction="row" alignItems="center" gap={2}>
        <Typography variant="h5" fontWeight={600}>
          Deep-sky objects
        </Typography>
        <Typography variant="body2" color="text.secondary">
          {listQuery.data
            ? `${listQuery.data.total.toLocaleString()} objects`
            : "…"}
        </Typography>
        <Box sx={{ flex: 1 }} />
        <Tooltip title="Catalog attribution" placement="bottom-end">
          <IconButton onClick={() => setAttributionOpen(true)} size="small">
            <InfoOutlinedIcon />
          </IconButton>
        </Tooltip>
      </Stack>

      {/* Filter bar */}
      <Paper variant="outlined" sx={{ p: 2 }}>
        <Stack direction={{ xs: "column", md: "row" }} gap={2} alignItems={{ md: "center" }}>
          <TextField
            size="small"
            placeholder="Search (M42, NGC 1976, Orion Nebula…)"
            value={query}
            onChange={(e) => {
              setQuery(e.target.value);
              setPagination((p) => ({ ...p, page: 0 }));
            }}
            sx={{ minWidth: 280, flex: { xs: 1, md: "initial" } }}
            InputProps={{
              startAdornment: (
                <InputAdornment position="start">
                  <SearchIcon fontSize="small" />
                </InputAdornment>
              ),
              endAdornment: query ? (
                <InputAdornment position="end">
                  <IconButton size="small" onClick={() => setQuery("")}>
                    <CloseIcon fontSize="small" />
                  </IconButton>
                </InputAdornment>
              ) : null,
            }}
          />

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

          {filtersActive && (
            <Button size="small" variant="text" onClick={clearFilters}>
              Clear filters
            </Button>
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
      </Paper>

      {showEmptyCatalogCta ? (
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
          <Typography
            variant="body2"
            color="text.secondary"
            sx={{ maxWidth: 520 }}
          >
            NightCrate doesn't ship catalog data — load the OpenNGC catalog
            directly from GitHub to start browsing. You'll be able to refresh
            it on demand to pick up upstream updates.
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
      ) : (
        <Paper variant="outlined" sx={{ flex: 1, minHeight: 0 }}>
          <DataGrid
            rows={listQuery.data?.items ?? []}
            columns={columns}
            loading={listQuery.isLoading || listQuery.isFetching}
            paginationMode="server"
            sortingMode="server"
            rowCount={listQuery.data?.total ?? 0}
            paginationModel={pagination}
            onPaginationModelChange={setPagination}
            sortModel={sortModel}
            onSortModelChange={setSortModel}
            pageSizeOptions={[25, 50, 100]}
            slotProps={{
              basePagination: {
                ActionsComponent: PaginationActions,
                // eslint-disable-next-line @typescript-eslint/no-explicit-any
              } as any,
            }}
            onRowClick={(params: GridRowParams<DsoListItem>) => setDetailId(params.row.id)}
            disableRowSelectionOnClick
            density="compact"
            sx={{
              border: 0,
              "& .MuiDataGrid-row": { cursor: "pointer" },
            }}
          />
        </Paper>
      )}

      <DsoDetailPanel dsoId={detailId} onClose={() => setDetailId(null)} />
      <DsoAttributionPanel open={attributionOpen} onClose={() => setAttributionOpen(false)} />
    </Box>
  );
}
