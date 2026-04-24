/**
 * DataTable — a reusable, lean data grid.
 *
 * Replaces MUI X DataGrid for cases where the Community tier's
 * 100-row pageSize cap is blocking. Features:
 *
 * - Declarative columns with `renderCell` / `valueGetter` / `format`.
 * - Clickable header sort (ascending → descending → none). Nulls last.
 * - Filter bar rendered ABOVE the grid — not inside column-header
 *   menus — so the selected values are always visible at a glance.
 *   Each filter is a single-select with options either fixed or
 *   derived from the row data.
 * - Paginated view (any pageSize) + Scroll view (all rows, virtualized).
 *   Scroll mode uses a small inline row virtualizer — no external
 *   dependency — that renders only the rows inside the viewport plus a
 *   small overscan buffer.
 * - Row-level className hook for conditional tinting (e.g. DROP frames
 *   in the PHD2 Analyzer data tab).
 *
 * Deliberately NOT implemented (would bloat this for marginal value):
 *   column drag-reorder, column show/hide menu, manual resize handles,
 *   cell editing, row selection, detail panels, tree rows.
 */

import { useEffect, useMemo, useRef, useState } from "react";
import Box from "@mui/material/Box";
import FormControl from "@mui/material/FormControl";
import InputLabel from "@mui/material/InputLabel";
import MenuItem from "@mui/material/MenuItem";
import Paper from "@mui/material/Paper";
import Select from "@mui/material/Select";
import Stack from "@mui/material/Stack";
import ToggleButton from "@mui/material/ToggleButton";
import ToggleButtonGroup from "@mui/material/ToggleButtonGroup";
import Typography from "@mui/material/Typography";
import ArrowDownwardIcon from "@mui/icons-material/ArrowDownward";
import ArrowUpwardIcon from "@mui/icons-material/ArrowUpward";
import PaginationActions from "@/components/common/PaginationActions";
import type {
  DataTableColumn,
  DataTableFilter,
  DataTableSortState,
  DataTableViewMode,
} from "./types";

const ALL_VALUE = "__all__";

interface Props<Row extends { id: string | number }> {
  rows: readonly Row[];
  columns: readonly DataTableColumn<Row>[];
  filters?: readonly DataTableFilter<Row>[];
  /** Initial sort state (uncontrolled). */
  initialSort?: DataTableSortState | null;
  /** Optional row-level className callback for conditional tinting. */
  getRowClassName?: (row: Row) => string | undefined;
  /** Empty-state label when there are no rows after filtering. */
  emptyMessage?: string;
  /** Fixed row height. Matters for Scroll-mode virtualization. */
  rowHeight?: number;
  /** Paginated-mode page sizes. */
  pageSizeOptions?: readonly number[];
  /** Initial page size. Must be one of ``pageSizeOptions``. */
  defaultPageSize?: number;
  /** Default view mode on first mount. */
  defaultViewMode?: DataTableViewMode;
  /** Hide the paginated/scroll toggle entirely (e.g. for tiny static tables). */
  showViewModeToggle?: boolean;
  /** Extra content rendered into the filter bar's right side (beside the toggle). */
  toolbarEnd?: React.ReactNode;
}

export default function DataTable<Row extends { id: string | number }>({
  rows,
  columns,
  filters = [],
  initialSort = null,
  getRowClassName,
  emptyMessage = "No rows to display",
  rowHeight = 32,
  pageSizeOptions = [25, 50, 100],
  defaultPageSize,
  defaultViewMode = "scroll",
  showViewModeToggle = true,
  toolbarEnd,
}: Props<Row>) {
  const [viewMode, setViewMode] = useState<DataTableViewMode>(defaultViewMode);
  const [pageSize, setPageSize] = useState<number>(
    defaultPageSize ?? pageSizeOptions[0] ?? 100,
  );
  const [page, setPage] = useState(0);
  const [sort, setSort] = useState<DataTableSortState | null>(initialSort);
  const [filterValues, setFilterValues] = useState<Record<string, string>>({});

  // ── Filtering ──────────────────────────────────────────────────────────────

  const filteredRows = useMemo(() => {
    let result = rows as readonly Row[];
    for (const filter of filters) {
      const selected = filterValues[filter.field];
      if (!selected || selected === ALL_VALUE) continue;
      result = result.filter((r) => filter.valueGetter(r) === selected);
    }
    return result;
  }, [rows, filters, filterValues]);

  // ── Sorting ────────────────────────────────────────────────────────────────

  const sortedRows = useMemo(() => {
    if (!sort) return filteredRows;
    const col = columns.find((c) => c.field === sort.field);
    if (!col) return filteredRows;
    const getter = columnGetter(col);
    const dir = sort.direction === "asc" ? 1 : -1;
    return [...filteredRows].sort((a, b) => {
      const av = getter(a);
      const bv = getter(b);
      if (av == null && bv == null) return 0;
      // Nulls always last regardless of direction.
      if (av == null) return 1;
      if (bv == null) return -1;
      if (av < bv) return -dir;
      if (av > bv) return dir;
      return 0;
    });
  }, [filteredRows, sort, columns]);

  // Reset to page 0 whenever the filtered/sorted set changes size so we
  // don't end up on an empty page after a filter shrinks the result.
  useEffect(() => {
    setPage(0);
  }, [filteredRows.length, pageSize, viewMode]);

  // ── Paginated slice vs scroll (all rows) ──────────────────────────────────

  const visibleRows = useMemo(() => {
    if (viewMode === "scroll") return sortedRows;
    return sortedRows.slice(page * pageSize, (page + 1) * pageSize);
  }, [sortedRows, viewMode, page, pageSize]);

  // ── Virtualization (Scroll mode) ──────────────────────────────────────────

  const scrollRef = useRef<HTMLDivElement | null>(null);
  const [scrollTop, setScrollTop] = useState(0);
  const [viewportH, setViewportH] = useState(0);

  useEffect(() => {
    const el = scrollRef.current;
    if (!el) return;
    const onScroll = () => setScrollTop(el.scrollTop);
    const ro = new ResizeObserver(() => setViewportH(el.clientHeight));
    ro.observe(el);
    el.addEventListener("scroll", onScroll, { passive: true });
    setViewportH(el.clientHeight);
    return () => {
      ro.disconnect();
      el.removeEventListener("scroll", onScroll);
    };
  }, []);

  // Reset scroll to top when the data or mode changes so the user doesn't
  // end up halfway down a different dataset.
  useEffect(() => {
    if (scrollRef.current) scrollRef.current.scrollTop = 0;
    setScrollTop(0);
  }, [viewMode, filteredRows]);

  const virtualSpan = useMemo(() => {
    if (viewMode !== "scroll") return null;
    const overscan = 8;
    const total = visibleRows.length;
    const firstVisible = Math.max(0, Math.floor(scrollTop / rowHeight) - overscan);
    const lastVisible = Math.min(
      total,
      Math.ceil((scrollTop + viewportH) / rowHeight) + overscan,
    );
    return {
      firstIndex: firstVisible,
      lastIndex: lastVisible,
      totalHeight: total * rowHeight,
      offsetTop: firstVisible * rowHeight,
    };
  }, [viewMode, visibleRows.length, scrollTop, viewportH, rowHeight]);

  // ── Sort toggle ────────────────────────────────────────────────────────────

  const onSortClick = (field: string) => {
    setSort((prev) => {
      if (!prev || prev.field !== field) return { field, direction: "asc" };
      if (prev.direction === "asc") return { field, direction: "desc" };
      return null; // third click clears
    });
  };

  // ── Filter options resolution ──────────────────────────────────────────────

  const resolvedFilterOptions = useMemo(() => {
    const out: Record<string, readonly string[]> = {};
    for (const f of filters) {
      const opts = typeof f.options === "function" ? f.options(rows) : f.options;
      out[f.field] = Array.from(new Set(opts)).sort();
    }
    return out;
  }, [filters, rows]);

  // ── Render ─────────────────────────────────────────────────────────────────

  const totalColumnsMinWidth = columns.reduce(
    (acc, c) => acc + (c.width ?? c.minWidth ?? 100),
    0,
  );

  const lastPage = Math.max(0, Math.ceil(sortedRows.length / pageSize) - 1);
  const currentPage = Math.min(page, lastPage);

  return (
    <Stack spacing={1.5} sx={{ height: "100%", minHeight: 0 }}>
      {(filters.length > 0 || showViewModeToggle || toolbarEnd) && (
        <Stack
          direction="row"
          spacing={1.5}
          alignItems="center"
          flexWrap="wrap"
          useFlexGap
          sx={{ flexShrink: 0 }}
        >
          {filters.map((f) => {
            const options = resolvedFilterOptions[f.field] ?? [];
            const value = filterValues[f.field] ?? ALL_VALUE;
            return (
              <FormControl key={f.field} size="small" sx={{ minWidth: 140 }}>
                <InputLabel id={`datatable-filter-${f.field}-label`}>{f.label}</InputLabel>
                <Select
                  labelId={`datatable-filter-${f.field}-label`}
                  label={f.label}
                  value={value}
                  onChange={(e) =>
                    setFilterValues((prev) => ({
                      ...prev,
                      [f.field]: String(e.target.value),
                    }))
                  }
                >
                  <MenuItem value={ALL_VALUE}>
                    <em>All</em>
                  </MenuItem>
                  {options.map((o) => (
                    <MenuItem key={o} value={o}>
                      {o}
                    </MenuItem>
                  ))}
                </Select>
              </FormControl>
            );
          })}
          <Box sx={{ flexGrow: 1 }} />
          {toolbarEnd}
          {showViewModeToggle && (
            <ToggleButtonGroup
              value={viewMode}
              exclusive
              size="small"
              onChange={(_, v) => {
                if (v) setViewMode(v as DataTableViewMode);
              }}
              sx={{ "& .MuiToggleButton-root": { py: 0.25, px: 1, fontSize: 12 } }}
            >
              <ToggleButton value="scroll">Scroll</ToggleButton>
              <ToggleButton value="paginated">Paginated</ToggleButton>
            </ToggleButtonGroup>
          )}
        </Stack>
      )}

      <Paper
        variant="outlined"
        sx={{
          flex: 1,
          minHeight: 0,
          display: "flex",
          flexDirection: "column",
          overflow: "hidden",
        }}
      >
        {/* Scrollable grid container — both horizontal and vertical. */}
        <Box
          ref={scrollRef}
          sx={{
            flex: 1,
            minHeight: 0,
            overflow: "auto",
            position: "relative",
          }}
        >
          <Box sx={{ minWidth: totalColumnsMinWidth, position: "relative" }}>
            {/* Sticky header */}
            <Box
              role="row"
              sx={{
                display: "flex",
                position: "sticky",
                top: 0,
                zIndex: 2,
                bgcolor: "background.paper",
                borderBottom: 1,
                borderColor: "divider",
                height: rowHeight + 2,
                alignItems: "center",
                fontSize: 12,
                fontWeight: 600,
              }}
            >
              {columns.map((col) => {
                const isSortable = col.sortable !== false;
                const sorted = sort?.field === col.field ? sort.direction : null;
                return (
                  <Box
                    key={col.field}
                    role="columnheader"
                    onClick={isSortable ? () => onSortClick(col.field) : undefined}
                    sx={{
                      ...columnSizeSx(col),
                      px: 1.25,
                      display: "flex",
                      alignItems: "center",
                      justifyContent: alignJustify(col.align),
                      gap: 0.25,
                      cursor: isSortable ? "pointer" : "default",
                      userSelect: "none",
                      "&:hover": isSortable ? { color: "primary.main" } : undefined,
                    }}
                  >
                    <span>{col.headerName}</span>
                    {sorted === "asc" && <ArrowUpwardIcon sx={{ fontSize: 14 }} />}
                    {sorted === "desc" && <ArrowDownwardIcon sx={{ fontSize: 14 }} />}
                  </Box>
                );
              })}
            </Box>

            {/* Body */}
            {visibleRows.length === 0 ? (
              <Box
                sx={{
                  p: 3,
                  textAlign: "center",
                  color: "text.secondary",
                  fontSize: 13,
                }}
              >
                {emptyMessage}
              </Box>
            ) : viewMode === "scroll" && virtualSpan ? (
              // Virtualized list — an outer sized box gives the scrollbar
              // its full extent; each rendered row is absolutely
              // positioned at its index * rowHeight offset.
              <Box sx={{ position: "relative", height: virtualSpan.totalHeight }}>
                <Box
                  sx={{
                    position: "absolute",
                    top: virtualSpan.offsetTop,
                    left: 0,
                    right: 0,
                  }}
                >
                  {visibleRows
                    .slice(virtualSpan.firstIndex, virtualSpan.lastIndex)
                    .map((row) => (
                      <DataRow
                        key={row.id}
                        row={row}
                        columns={columns}
                        rowHeight={rowHeight}
                        className={getRowClassName?.(row)}
                      />
                    ))}
                </Box>
              </Box>
            ) : (
              // Paginated view — no virtualization needed at ≤100 rows.
              visibleRows.map((row) => (
                <DataRow
                  key={row.id}
                  row={row}
                  columns={columns}
                  rowHeight={rowHeight}
                  className={getRowClassName?.(row)}
                />
              ))
            )}
          </Box>
        </Box>

        {/* Footer — pagination (paginated mode) or row count (scroll mode). */}
        {viewMode === "paginated" ? (
          <Stack
            direction="row"
            spacing={1}
            alignItems="center"
            sx={{
              flexShrink: 0,
              px: 1.5,
              py: 0.5,
              borderTop: 1,
              borderColor: "divider",
              fontSize: 12,
              minHeight: 40,
            }}
          >
            <Typography variant="caption" color="text.secondary">
              {sortedRows.length.toLocaleString()} rows
            </Typography>
            <Box sx={{ flexGrow: 1 }} />
            <FormControl size="small" sx={{ minWidth: 76 }}>
              <Select
                value={pageSize}
                onChange={(e) => setPageSize(Number(e.target.value))}
                displayEmpty
                sx={{ height: 30, fontSize: 12 }}
              >
                {pageSizeOptions.map((n) => (
                  <MenuItem key={n} value={n}>
                    {n} / page
                  </MenuItem>
                ))}
              </Select>
            </FormControl>
            <PaginationActions
              count={sortedRows.length}
              page={currentPage}
              rowsPerPage={pageSize}
              onPageChange={(_, p) => setPage(p)}
            />
          </Stack>
        ) : (
          <Stack
            direction="row"
            spacing={1}
            alignItems="center"
            sx={{
              flexShrink: 0,
              px: 1.5,
              py: 0.5,
              borderTop: 1,
              borderColor: "divider",
              fontSize: 12,
              minHeight: 32,
            }}
          >
            <Typography variant="caption" color="text.secondary">
              {sortedRows.length.toLocaleString()} rows · virtualized scroll
            </Typography>
          </Stack>
        )}
      </Paper>
    </Stack>
  );
}

// ── Row subcomponent ─────────────────────────────────────────────────────────

interface RowProps<Row> {
  row: Row;
  columns: readonly DataTableColumn<Row>[];
  rowHeight: number;
  className?: string;
}

function DataRow<Row extends { id: string | number }>({
  row,
  columns,
  rowHeight,
  className,
}: RowProps<Row>) {
  return (
    <Box
      role="row"
      className={className}
      sx={{
        display: "flex",
        height: rowHeight,
        alignItems: "center",
        borderBottom: 1,
        borderColor: "divider",
        fontSize: 12,
        "&:hover": { bgcolor: "action.hover" },
      }}
    >
      {columns.map((col) => (
        <Box
          key={col.field}
          role="cell"
          sx={{
            ...columnSizeSx(col),
            px: 1.25,
            overflow: "hidden",
            textOverflow: "ellipsis",
            whiteSpace: "nowrap",
            textAlign: col.align ?? "left",
          }}
        >
          {renderCellContent(row, col)}
        </Box>
      ))}
    </Box>
  );
}

// ── Helpers ──────────────────────────────────────────────────────────────────

function columnGetter<Row>(col: DataTableColumn<Row>): (row: Row) => unknown {
  if (col.valueGetter) return col.valueGetter;
  return (row) => (row as unknown as Record<string, unknown>)[col.field];
}

function columnSizeSx<Row>(col: DataTableColumn<Row>) {
  if (col.width != null) {
    return { width: col.width, minWidth: col.width, flexShrink: 0 };
  }
  return {
    flex: col.flex ?? 1,
    minWidth: col.minWidth ?? 100,
  };
}

function alignJustify(align: DataTableColumn<unknown>["align"]): string {
  if (align === "right") return "flex-end";
  if (align === "center") return "center";
  return "flex-start";
}

function renderCellContent<Row>(row: Row, col: DataTableColumn<Row>): React.ReactNode {
  if (col.renderCell) return col.renderCell(row);
  const value = columnGetter(col)(row);
  if (col.format) return col.format(value);
  if (value == null) return "";
  if (typeof value === "number") return value.toString();
  return String(value);
}
