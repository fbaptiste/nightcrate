/**
 * DataTable — a reusable, lean data grid.
 *
 * Replaces MUI X DataGrid for cases where the Community tier's
 * 100-row pageSize cap is blocking. Features:
 *
 * - Declarative columns with ``renderCell`` / ``valueGetter`` /
 *   ``format``. Header-click sort: ascending → descending → none.
 *   Nulls always sort last.
 * - Filter bar rendered ABOVE the grid (not inside column-header
 *   menus). Each filter is a *multi-select* dropdown: zero selected =
 *   no filter on that column; ≥ 1 selected = keep rows whose
 *   ``valueGetter`` result is in the selected set.
 * - Paginated view (any pageSize) + Scroll view (all rows, virtualized
 *   via a small inline variable-height virtualizer).
 * - Expandable rows via ``renderExpanded`` / ``isExpandable`` props.
 *   Columns' ``renderCell`` receives a second ``api`` argument with
 *   ``isExpanded`` + ``toggleExpand()`` so the cell can place an
 *   expansion chip wherever makes sense. Expanded rows grow in place
 *   and push later rows down — the virtualizer handles variable
 *   heights.
 * - Row-level className hook for conditional tinting.
 *
 * Deliberately NOT implemented: column drag-reorder, column show/hide
 * menu, manual resize handles, cell editing, row selection, detail
 * panels beyond the inline expand.
 */

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import Box from "@mui/material/Box";
import Checkbox from "@mui/material/Checkbox";
import FormControl from "@mui/material/FormControl";
import InputLabel from "@mui/material/InputLabel";
import ListItemText from "@mui/material/ListItemText";
import MenuItem from "@mui/material/MenuItem";
import Paper from "@mui/material/Paper";
import Select, { type SelectChangeEvent } from "@mui/material/Select";
import Stack from "@mui/material/Stack";
import ToggleButton from "@mui/material/ToggleButton";
import ToggleButtonGroup from "@mui/material/ToggleButtonGroup";
import Typography from "@mui/material/Typography";
import ArrowDownwardIcon from "@mui/icons-material/ArrowDownward";
import ArrowUpwardIcon from "@mui/icons-material/ArrowUpward";
import PaginationActions from "@/components/common/PaginationActions";
import type {
  DataTableCellApi,
  DataTableColumn,
  DataTableFilter,
  DataTableSortState,
  DataTableViewMode,
} from "./types";

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
  /** Fixed base row height. Matters for Scroll-mode virtualization. */
  rowHeight?: number;
  /** Paginated-mode page sizes. */
  pageSizeOptions?: readonly number[];
  /** Initial page size. Must be one of ``pageSizeOptions``. */
  defaultPageSize?: number;
  /** Default view mode on first mount. */
  defaultViewMode?: DataTableViewMode;
  /** Hide the paginated/scroll toggle entirely (e.g. for tiny tables). */
  showViewModeToggle?: boolean;
  /** Extra content rendered at the right of the filter bar. */
  toolbarEnd?: React.ReactNode;
  // Expandable-row support (all optional). When renderExpanded is
  // provided, each row CAN expand; the cell renderer is responsible
  // for placing the toggle (using its ``api`` argument). ``isExpandable``
  // gates which rows actually have content worth expanding.
  renderExpanded?: (row: Row) => React.ReactNode;
  isExpandable?: (row: Row) => boolean;
  /** Height of the expanded area (px), added below the normal row.
   *  Can be a function of the row for dynamic sizing. Default 120. */
  expandedHeight?: number | ((row: Row) => number);
  /** When set to a non-null value, DataTable scrolls that row into
   *  view (Scroll mode) or jumps to its page (Paginated mode) and
   *  expands it. The parent typically sets this in response to a
   *  user action (e.g. "click an event in a sidebar → reveal its
   *  frame") and can clear it via ``onRowScrolledTo`` once it fires.
   *  Forcing a new value even when the id is the same triggers a
   *  fresh scroll — so use a ``{ id, nonce }`` pattern if you need
   *  repeat-click behaviour. */
  scrollToRowId?: string | number | null;
  /** Optional ack — fired after a scrollToRowId request resolves. */
  onRowScrolledTo?: (id: string | number) => void;
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
  renderExpanded,
  isExpandable,
  expandedHeight = 120,
  scrollToRowId = null,
  onRowScrolledTo,
}: Props<Row>) {
  const [viewMode, setViewMode] = useState<DataTableViewMode>(defaultViewMode);
  const [pageSize, setPageSize] = useState<number>(
    defaultPageSize ?? pageSizeOptions[0] ?? 100,
  );
  const [page, setPage] = useState(0);
  const [sort, setSort] = useState<DataTableSortState | null>(initialSort);
  // filterValues: one array per filter field. Empty array = no filter.
  const [filterValues, setFilterValues] = useState<Record<string, string[]>>({});
  const [expandedIds, setExpandedIds] = useState<Set<string | number>>(new Set());

  // ── Filtering ──────────────────────────────────────────────────────────────

  const filteredRows = useMemo(() => {
    let result = rows as readonly Row[];
    for (const filter of filters) {
      const selected = filterValues[filter.field];
      if (!selected || selected.length === 0) continue;
      const selectedSet = new Set(selected);
      result = result.filter((r) => selectedSet.has(filter.valueGetter(r)));
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
      if (av == null) return 1; // nulls last
      if (bv == null) return -1;
      if (av < bv) return -dir;
      if (av > bv) return dir;
      return 0;
    });
  }, [filteredRows, sort, columns]);

  // Reset page when the filter/sort/view changes so we don't land on
  // an empty page.
  useEffect(() => {
    setPage(0);
  }, [filteredRows.length, pageSize, viewMode]);

  // Collapse all expanded rows whenever the row set changes — a
  // previously-expanded id might belong to a filtered-out row.
  useEffect(() => {
    setExpandedIds(new Set());
  }, [filteredRows]);

  // ── Pagination slice vs scroll (all rows) ─────────────────────────────────

  const visibleRows = useMemo(() => {
    if (viewMode === "scroll") return sortedRows;
    return sortedRows.slice(page * pageSize, (page + 1) * pageSize);
  }, [sortedRows, viewMode, page, pageSize]);

  // ── Row positions (variable heights for expandable rows) ──────────────────

  const rowLayout = useMemo(() => {
    const positions: Array<{ y: number; h: number; expanded: boolean }> = [];
    let y = 0;
    for (const row of visibleRows) {
      const canExpand = !!renderExpanded && (!isExpandable || isExpandable(row));
      const expanded = canExpand && expandedIds.has(row.id);
      const extra = expanded
        ? typeof expandedHeight === "function"
          ? expandedHeight(row)
          : expandedHeight
        : 0;
      const h = rowHeight + extra;
      positions.push({ y, h, expanded });
      y += h;
    }
    return { positions, totalHeight: y };
  }, [visibleRows, expandedIds, rowHeight, renderExpanded, isExpandable, expandedHeight]);

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

  // Reset scroll when the data or mode changes.
  useEffect(() => {
    if (scrollRef.current) scrollRef.current.scrollTop = 0;
    setScrollTop(0);
  }, [viewMode, filteredRows]);

  const virtualSpan = useMemo(() => {
    if (viewMode !== "scroll") return null;
    const overscanPx = rowHeight * 8;
    const { positions, totalHeight } = rowLayout;
    if (positions.length === 0) {
      return { firstIndex: 0, lastIndex: 0, totalHeight: 0, offsetTop: 0 };
    }
    // Binary search for first row whose bottom is past (scrollTop - overscanPx).
    const targetTop = Math.max(0, scrollTop - overscanPx);
    let lo = 0;
    let hi = positions.length - 1;
    while (lo < hi) {
      const mid = (lo + hi) >> 1;
      if (positions[mid].y + positions[mid].h <= targetTop) lo = mid + 1;
      else hi = mid;
    }
    const firstIndex = lo;
    // Linear scan forward for last visible (cheap — viewport is bounded).
    const targetBottom = scrollTop + viewportH + overscanPx;
    let lastIndex = firstIndex;
    while (lastIndex < positions.length && positions[lastIndex].y < targetBottom) {
      lastIndex++;
    }
    return {
      firstIndex,
      lastIndex,
      totalHeight,
      offsetTop: positions[firstIndex].y,
    };
  }, [viewMode, rowLayout, scrollTop, viewportH, rowHeight]);

  // ── Sort toggle ────────────────────────────────────────────────────────────

  const onSortClick = (field: string) => {
    setSort((prev) => {
      if (!prev || prev.field !== field) return { field, direction: "asc" };
      if (prev.direction === "asc") return { field, direction: "desc" };
      return null;
    });
  };

  // ── Expand toggle ─────────────────────────────────────────────────────────

  const toggleExpand = useCallback((id: string | number) => {
    setExpandedIds((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  }, []);

  // ── External scroll-to-row + auto-expand ──────────────────────────────────

  // Two-phase: first effect flips the row into the expanded set (which
  // triggers a rowLayout recompute); the second effect fires once the
  // new layout is in place and finally scrolls. ``pendingScrollRef``
  // survives across renders so we don't re-scroll on every layout
  // change.
  const pendingScrollRef = useRef<string | number | null>(null);

  useEffect(() => {
    if (scrollToRowId == null) return;
    const row = sortedRows.find((r) => r.id === scrollToRowId);
    if (!row) return;
    pendingScrollRef.current = scrollToRowId;
    // Paginated mode: jump to the page containing this row too.
    if (viewMode === "paginated") {
      const idx = sortedRows.findIndex((r) => r.id === scrollToRowId);
      if (idx >= 0) setPage(Math.floor(idx / pageSize));
    }
    const canExpand = !!renderExpanded && (!isExpandable || isExpandable(row));
    if (canExpand) {
      setExpandedIds((prev) => {
        if (prev.has(scrollToRowId)) return prev;
        const next = new Set(prev);
        next.add(scrollToRowId);
        return next;
      });
    }
  }, [scrollToRowId, sortedRows, viewMode, pageSize, renderExpanded, isExpandable]);

  useEffect(() => {
    const target = pendingScrollRef.current;
    if (target == null) return;
    const idx = visibleRows.findIndex((r) => r.id === target);
    if (idx < 0) return;
    const pos = rowLayout.positions[idx];
    if (!pos || !scrollRef.current) return;
    // Leave a bit of header + one row worth of context at the top.
    scrollRef.current.scrollTop = Math.max(0, pos.y - rowHeight * 2);
    pendingScrollRef.current = null;
    onRowScrolledTo?.(target);
  }, [rowLayout, visibleRows, rowHeight, onRowScrolledTo]);

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

  const renderOne = (row: Row, layoutH: number, expanded: boolean) => {
    const api: DataTableCellApi = {
      isExpanded: expanded,
      toggleExpand: () => toggleExpand(row.id),
    };
    const canExpand = !!renderExpanded && (!isExpandable || isExpandable(row));
    return (
      <Box
        key={row.id}
        role="row"
        className={getRowClassName?.(row)}
        sx={{
          height: layoutH,
          borderBottom: 1,
          borderColor: "divider",
          display: "flex",
          flexDirection: "column",
          fontSize: 12,
        }}
      >
        <Box
          sx={{
            display: "flex",
            alignItems: "center",
            height: rowHeight,
            flexShrink: 0,
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
              {renderCellContent(row, col, api)}
            </Box>
          ))}
        </Box>
        {canExpand && expanded && renderExpanded && (
          <Box
            sx={{
              flex: 1,
              overflow: "auto",
              bgcolor: "action.hover",
              borderTop: 1,
              borderColor: "divider",
              px: 2,
              py: 1,
            }}
          >
            {renderExpanded(row)}
          </Box>
        )}
      </Box>
    );
  };

  return (
    // See the "minWidth: 0" comment below — necessary for flex parents.
    <Stack spacing={1.5} sx={{ height: "100%", minHeight: 0, minWidth: 0 }}>
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
            const value = filterValues[f.field] ?? [];
            return (
              <FormControl key={f.field} size="small" sx={{ minWidth: 160 }}>
                <InputLabel id={`datatable-filter-${f.field}-label`}>{f.label}</InputLabel>
                <Select<string[]>
                  labelId={`datatable-filter-${f.field}-label`}
                  label={f.label}
                  multiple
                  value={value}
                  renderValue={(selected) =>
                    selected.length === 0
                      ? ""
                      : selected.length === options.length
                        ? "All"
                        : selected.length === 1
                          ? selected[0]
                          : `${selected.length} selected`
                  }
                  onChange={(e: SelectChangeEvent<string[]>) => {
                    const raw = e.target.value;
                    const arr = typeof raw === "string" ? raw.split(",") : raw;
                    setFilterValues((prev) => ({ ...prev, [f.field]: arr }));
                  }}
                >
                  {options.map((o) => (
                    <MenuItem key={o} value={o}>
                      <Checkbox checked={value.indexOf(o) > -1} size="small" />
                      <ListItemText primary={o} />
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
          minWidth: 0,
          display: "flex",
          flexDirection: "column",
          overflow: "hidden",
        }}
      >
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
              <Box sx={{ p: 3, textAlign: "center", color: "text.secondary", fontSize: 13 }}>
                {emptyMessage}
              </Box>
            ) : viewMode === "scroll" && virtualSpan ? (
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
                    .map((row, i) => {
                      const pos = rowLayout.positions[virtualSpan.firstIndex + i];
                      return renderOne(row, pos.h, pos.expanded);
                    })}
                </Box>
              </Box>
            ) : (
              // Paginated view — no virtualization.
              visibleRows.map((row, i) => {
                const pos = rowLayout.positions[i];
                return renderOne(row, pos.h, pos.expanded);
              })
            )}
          </Box>
        </Box>

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

function renderCellContent<Row>(
  row: Row,
  col: DataTableColumn<Row>,
  api: DataTableCellApi,
): React.ReactNode {
  if (col.renderCell) return col.renderCell(row, api);
  const value = columnGetter(col)(row);
  if (col.format) return col.format(value);
  if (value == null) return "";
  if (typeof value === "number") return value.toString();
  return String(value);
}
