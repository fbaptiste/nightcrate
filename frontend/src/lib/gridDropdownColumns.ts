import type { GridColDef, GridValidRowModel } from "@mui/x-data-grid";

export type DropdownValue = string | number | boolean;

export function dropdownOptions<R>(
  rows: readonly R[],
  field: string,
  getValue: (row: R) => unknown,
): DropdownValue[] {
  void field;
  const values = new Set<DropdownValue>();
  for (const row of rows) {
    const value = getValue(row);
    if (
      value == null
      || value === ""
      || value === "—"
      || (typeof value !== "string" && typeof value !== "number" && typeof value !== "boolean")
    ) {
      continue;
    }
    values.add(value);
  }
  return [...values].sort((a, b) =>
    String(a).localeCompare(String(b), undefined, { numeric: true, sensitivity: "base" }),
  );
}

export function withDropdownFilters<R extends GridValidRowModel>(
  columns: readonly GridColDef<R>[],
  rows: readonly R[],
  fields: readonly string[],
): GridColDef<R>[] {
  const dropdownFields = new Set(fields);
  return columns.map((column) => {
    if (!dropdownFields.has(column.field)) return column;
    const valueOptions = dropdownOptions(rows, column.field, (row) =>
      column.valueGetter
        ? (column.valueGetter as (value: unknown, row: R) => unknown)(undefined, row)
        : (row as Record<string, unknown>)[column.field],
    );
    return { ...column, type: "singleSelect", valueOptions };
  });
}
