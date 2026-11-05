import { useMemo, useRef, useState } from "react";
import { useDsoCatalogStore } from "@/stores/dsoCatalogStore";
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
import FormControlLabel from "@mui/material/FormControlLabel";
import IconButton from "@mui/material/IconButton";
import InputAdornment from "@mui/material/InputAdornment";
import Paper from "@mui/material/Paper";
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
import GridLoadingOverlay from "@/components/common/GridLoadingOverlay";
import PaginationActions from "@/components/common/PaginationActions";
import NameWithAlternates from "@/components/common/NameWithAlternates";
import CatalogFilter from "@/components/dso/CatalogFilter";
import ConstellationFilter from "@/components/dso/ConstellationFilter";
import DsoAttributionPanel from "@/components/dso/DsoAttributionPanel";
import DsoDetailPanel from "@/components/dso/DsoDetailPanel";
import TypeFilter from "@/components/dso/TypeFilter";
import { displayConstellation } from "@/lib/constellations";
import { formatDistance } from "@/lib/distanceFormat";
import { displayDsoType, dsoTypeColor } from "@/lib/dsoTypeNames";
// Note: the old "advanced filters" chip row is retired in favour of the
// TypeFilter pill selector — displayDsoType + dsoTypeColor are still used
// by the grid's Type column.
import {
  formatDec,
  formatMagnitude,
  formatRa,
  formatSize,
} from "@/lib/dsoFormatters";

// Screen-reader-only text. Explicit px: in `sx`, a bare 1 means 100% and a
// bare -1 a theme spacing step.
const visuallyHiddenSx = {
  border: 0,
  clip: "rect(0 0 0 0)",
  height: "1px",
  margin: "-1px",
  overflow: "hidden",
  padding: 0,
  position: "absolute",
  whiteSpace: "nowrap",
  width: "1px",
} as const;

export default function DsoCatalogPage() {
  const store = useDsoCatalogStore();
  const [query, setQuery] = [store.query, store.setQuery];
  const debouncedQuery = useDebounce(query, 300);

  const [typeFilter, setTypeFilter] = [store.typeFilter, store.setTypeFilter];
  const [constellationFilter, setConstellationFilter] = [store.constellationFilter, store.setConstellationFilter];
  const [hasDistance, setHasDistance] = [store.hasDistance, store.setHasDistance];
  const [catalogFilter, setCatalogFilter] = [store.catalogFilter, store.setCatalogFilter];
  const pagination: GridPaginationModel = { page: store.page, pageSize: store.pageSize };
  const setPagination = (m: GridPaginationModel | ((prev: GridPaginationModel) => GridPaginationModel)) => {
    const val = typeof m === "function" ? m(pagination) : m;
    store.setPage(val.page);
    store.setPageSize(val.pageSize);
  };
  // Keep the model's identity stable: the grid re-applies a new sortModel
  // array as a sort change and jumps back to the first page.
  const sortModel: GridSortModel = useMemo(
    () => [{ field: store.sortField, sort: store.sortDir }],
    [store.sortField, store.sortDir],
  );
  const setSortModel = (m: GridSortModel) => {
    if (m.length > 0) {
      store.setSort(m[0].field, (m[0].sort ?? "asc") as "asc" | "desc");
    }
  };
  const [detailId, setDetailId] = [store.detailId, store.setDetailId];
  const detailReturnFocusRef = useRef<HTMLElement | null>(null);
  const [attributionOpen, setAttributionOpen] = useState(false);

  const closeDetail = () => {
    const returnFocus = detailReturnFocusRef.current;
    setDetailId(null);
    if (returnFocus) {
      window.requestAnimationFrame(() => {
        returnFocus.focus();
        detailReturnFocusRef.current = null;
      });
    }
  };

  const sort = store.sortField;
  const sortDir = store.sortDir;

  const listParams = {
    q: debouncedQuery || null,
    type: typeFilter,
    constellation: constellationFilter,
    has_distance: hasDistance ? true : null,
    catalog: catalogFilter,
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

  // Facets are filter-aware: each chip's count reflects the current
  // filter state with that chip's own dimension excluded. Query key
  // includes every filter param so TanStack re-fetches when the user
  // types in search / flips the has-distance box / clears filters.
  const facetsParams = {
    q: debouncedQuery || null,
    constellation: constellationFilter,
    has_distance: hasDistance ? true : null,
    type: typeFilter,
    catalog: catalogFilter,
  };
  const facetsQuery = useQuery({
    queryKey: ["dso-facets", facetsParams],
    queryFn: () => fetchDsoFacets(facetsParams),
    staleTime: 60_000,
    // Keep showing the previous counts while the refetch is in flight
    // so chip labels don't flash to empty on every filter tick.
    placeholderData: (previous) => previous,
  });

  const clearFilters = () => {
    setQuery("");
    setTypeFilter([]);
    setConstellationFilter([]);
    setHasDistance(false);
    setCatalogFilter([]);
    setPagination((p) => ({ ...p, page: 0 }));
  };

  const filtersActive =
    debouncedQuery ||
    typeFilter.length > 0 ||
    constellationFilter.length > 0 ||
    hasDistance ||
    catalogFilter.length > 0;

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
      renderCell: (params) => {
        const nameTooltip = params.row.common_name
          ? [
              params.row.common_name,
              params.row.other_names.length > 0
                ? `also known as ${params.row.other_names.join(", ")}`
                : null,
            ]
              .filter(Boolean)
              .join(" — ")
          : undefined;
        return (
          <Box sx={{ alignItems: "center", display: "flex", height: "100%" }}>
            <NameWithAlternates
              name={params.row.display_designation}
              otherNames={params.row.other_names}
              title={nameTooltip}
              tabIndex={null}
            >
              <Typography component="span" variant="body2" fontWeight={600}>
                {params.row.display_designation}
              </Typography>
            </NameWithAlternates>
          </Box>
        );
      },
    },
    {
      field: "designations",
      headerName: "Alt designations",
      width: 360,
      resizable: false,
      sortable: false,
      renderCell: (params) => {
        const alternatives = params.row.designations
          .map((designation) => designation.display_form)
          .filter(
            (designation, index, all) =>
              designation !== params.row.display_designation &&
              all.indexOf(designation) === index,
          );
        const labels = [
          ...params.row.part_of.map(
            (group) =>
              `Part of ${group.display_form}${group.common_name ? ` · ${group.common_name}` : ""}`,
          ),
          ...alternatives,
        ].filter((label, index, all) => all.indexOf(label) === index);
        const visible = labels.slice(0, 2);
        const hidden = labels.slice(2);
        return (
          <Box
            sx={{
              alignItems: "center",
              display: "flex",
              gap: 0.75,
              height: "100%",
              minWidth: 0,
              overflow: "hidden",
              width: "100%",
            }}
          >
            {visible.length === 0 ? (
              <Typography variant="body2" color="text.secondary">
                —
              </Typography>
            ) : (
              visible.map((label) => (
                <Chip
                  key={label}
                  label={label}
                  size="small"
                  variant="outlined"
                  sx={{
                    bgcolor: "background.paper",
                    borderColor: "divider",
                    color: "text.primary",
                    maxWidth: 140,
                    minWidth: 0,
                    "& .MuiChip-label": {
                      overflow: "hidden",
                      textOverflow: "ellipsis",
                      whiteSpace: "nowrap",
                    },
                  }}
                />
              ))
            )}
            {hidden.length > 0 && (
              <>
                <Chip
                  aria-hidden="true"
                  label={`+${hidden.length}`}
                  size="small"
                  variant="outlined"
                  sx={{
                    bgcolor: "background.paper",
                    borderColor: "divider",
                    color: "text.secondary",
                    flexShrink: 0,
                  }}
                />
                <Box
                  component="span"
                  sx={visuallyHiddenSx}
                >
                  {hidden.length} more: {hidden.join(", ")}.
                </Box>
              </>
            )}
            <Box
              component="span"
              sx={visuallyHiddenSx}
            >
              Press Enter for details.
            </Box>
          </Box>
        );
      },
    },
    {
      field: "obj_type",
      headerName: "Type",
      width: 212,
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
      renderCell: (params) =>
        params.row.common_name ? (
          <NameWithAlternates
            name={params.row.common_name}
            otherNames={params.row.other_names}
          />
        ) : (
          "—"
        ),
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

        {/* Pill filter row — every multi-select filter gets the same shape
            (label + chips inside the input + muted (count) in the dropdown).
            Each wraps in a 320px Box on md+ so two medium chips sit side-
            by-side before wrapping. Order: Catalog → Object type → Constellation. */}
        <Stack direction={{ xs: "column", md: "row" }} gap={2} sx={{ mt: 2, flexWrap: "wrap" }}>
          <Box sx={{ width: { xs: "100%", md: 320 } }}>
            <CatalogFilter
              value={catalogFilter}
              onChange={(codes) => {
                setCatalogFilter(codes);
                setPagination((p) => ({ ...p, page: 0 }));
              }}
              options={facetsQuery.data?.catalogs ?? []}
            />
          </Box>
          <Box sx={{ width: { xs: "100%", md: 320 } }}>
            <TypeFilter
              value={typeFilter}
              onChange={(codes) => {
                setTypeFilter(codes);
                setPagination((p) => ({ ...p, page: 0 }));
              }}
              options={facetsQuery.data?.raw_types ?? []}
            />
          </Box>
          <Box sx={{ width: { xs: "100%", md: 320 } }}>
            <ConstellationFilter
              value={constellationFilter}
              onChange={(codes) => {
                setConstellationFilter(codes);
                setPagination((p) => ({ ...p, page: 0 }));
              }}
              options={facetsQuery.data?.constellations ?? []}
            />
          </Box>
        </Stack>
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
            sortingOrder={["asc", "desc"]}
            pageSizeOptions={[25, 50, 100]}
            slots={{ loadingOverlay: GridLoadingOverlay }}
            slotProps={{
              basePagination: {
                ActionsComponent: PaginationActions,
                // eslint-disable-next-line @typescript-eslint/no-explicit-any
              } as any,
            }}
            onRowClick={(params: GridRowParams<DsoListItem>) => setDetailId(params.row.id)}
            onCellKeyDown={(params, event) => {
              if (
                event.key === "Enter" &&
                event.target === event.currentTarget &&
                event.currentTarget instanceof HTMLElement
              ) {
                detailReturnFocusRef.current = event.currentTarget;
                setDetailId(params.row.id);
              }
            }}
            disableRowSelectionOnClick
            density="compact"
            sx={{
              border: 0,
              "& .MuiDataGrid-row": { cursor: "pointer" },
            }}
          />
        </Paper>
      )}

      <DsoDetailPanel
        dsoId={detailId}
        onSelectDso={setDetailId}
        onClose={closeDetail}
      />
      <DsoAttributionPanel open={attributionOpen} onClose={() => setAttributionOpen(false)} />
    </Box>
  );
}
