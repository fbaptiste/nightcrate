/**
 * Public interfaces for the reusable DataTable component.
 *
 * Kept intentionally minimal: columns, filters, sort, view mode. The
 * feature set targets "scan + sort + filter + paginate a list of rows" —
 * the 80% case that MUI X DataGrid's Community tier handles fine but
 * whose 100-row pageSize cap blocks our PHD2 Analyzer Data tab with ~7 500
 * rows. Advanced features MUI X offers (column drag-reorder, show/hide
 * menus, manual resize handles, detail panels) are deliberately out of
 * scope.
 */

import type React from "react";

/** Per-cell render API passed as the second argument to ``renderCell``.
 *
 *  The expand/collapse bits are meaningful only when the table is
 *  configured with ``renderExpanded`` — a cell renderer that wants to
 *  place an expansion chip (e.g. alongside a row id) can call
 *  ``toggleExpand()`` or read ``isExpanded`` here. */
export interface DataTableCellApi {
  isExpanded: boolean;
  toggleExpand: () => void;
}

/** One column definition. Generic over the row type so valueGetter + renderCell
 *  stay type-safe at the call site. `field` doesn't have to be a key of Row —
 *  computed columns with a `valueGetter` can use any string id. */
export interface DataTableColumn<Row> {
  /** Stable column id. Used as key for sort + rendering. */
  field: string;
  /** Displayed column header. */
  headerName: string;
  /** Fixed width in px. Mutually exclusive with `flex`. */
  width?: number;
  /** Grow factor for flexible width. */
  flex?: number;
  /** Minimum width when using `flex`. */
  minWidth?: number;
  /** Text alignment within the cell. Defaults to "left". */
  align?: "left" | "right" | "center";
  /** Disable the header's sort affordance (default sortable: true). */
  sortable?: boolean;
  /** Pulls the sortable / filterable value from a row. Default: `row[field]`. */
  valueGetter?: (row: Row) => unknown;
  /** Custom cell rendering. Default: the formatted valueGetter result. */
  renderCell?: (row: Row, api: DataTableCellApi) => React.ReactNode;
  /** Simple string formatter applied to the valueGetter result when
   *  renderCell is not provided. Falls back to the raw value. */
  format?: (value: unknown) => string;
}

/** One filter control rendered above the grid. Multi-select: the user
 *  picks zero or more values; an empty selection means "no filter on this
 *  column", a non-empty selection keeps rows whose ``valueGetter`` result
 *  is in the selected set. */
export interface DataTableFilter<Row> {
  /** Stable filter id. */
  field: string;
  /** Displayed filter label. */
  label: string;
  /** Selectable values. Either a fixed list or a function that derives
   *  the unique values from the rows (sorted alphabetically in the UI
   *  either way). */
  options: readonly string[] | ((rows: readonly Row[]) => readonly string[]);
  /** Pulls the comparison string from a row. The filter matches when
   *  ``valueGetter(row)`` is one of the selected values. */
  valueGetter: (row: Row) => string;
}

export type DataTableViewMode = "paginated" | "scroll";

export interface DataTableSortState {
  field: string;
  direction: "asc" | "desc";
}
