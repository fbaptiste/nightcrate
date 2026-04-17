import Box from "@mui/material/Box";
import { type GridColDef } from "@mui/x-data-grid";
import { fetchFilters, deleteFilter, type Filter } from "@/api/equipment";
import EquipmentList from "./EquipmentList";
import FilterFormDialog from "./FilterFormDialog";
import DetailField from "@/components/equipment/shared/DetailField";
import ExternalLink from "@/components/equipment/shared/ExternalLink";

function summarizePassbands(filter: Filter): string {
  if (filter.passbands.length === 0) return "—";
  const names = filter.passbands.map(
    (pb) => pb.line_name ?? `${pb.central_wavelength_nm}nm`,
  );
  return names.join(" + ");
}

function FilterForm({
  open,
  item,
  onClose,
  onSaved,
}: {
  open: boolean;
  item: Filter | null;
  onClose: () => void;
  onSaved: () => void;
}) {
  return (
    <FilterFormDialog
      open={open}
      filter={item}
      onClose={onClose}
      onSaved={onSaved}
    />
  );
}

const columns: GridColDef<Filter>[] = [
  {
    field: "manufacturer",
    headerName: "Manufacturer",
    flex: 1,
    minWidth: 130,
    valueGetter: (_value, row) => row.manufacturer.name,
  },
  {
    field: "model_name",
    headerName: "Model",
    flex: 1.5,
    minWidth: 160,
  },
  {
    field: "filter_type",
    headerName: "Type",
    flex: 1,
    minWidth: 150,
    valueGetter: (_value, row) => row.filter_type.display_name,
  },
  {
    field: "passbands",
    headerName: "Passbands",
    flex: 1.5,
    minWidth: 150,
    sortable: false,
    valueGetter: (_value, row) => summarizePassbands(row),
  },
  {
    field: "size_options",
    headerName: "Sizes",
    width: 150,
    sortable: false,
    valueGetter: (_value, row) =>
      row.size_options.length > 0
        ? row.size_options.map((so) => so.filter_size.name).join(", ")
        : "—",
  },
];

export default function FilterList({ mineOnly = false }: { mineOnly?: boolean } = {}) {
  return (
    <EquipmentList<Filter>
      title={mineOnly ? "My Filters" : "Filters"}
      queryKey={mineOnly ? "my-filters" : "filters"}
      mineOnly={mineOnly}
      tableName="filter"
      fetchFn={fetchFilters}
      deleteFn={deleteFilter}
      columns={columns}
      getItemName={(f) => f.model_name}
      FormDialog={FilterForm}
      renderDetail={(item) => (
        <Box sx={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 0, columnGap: 4 }}>
          <DetailField label="Manufacturer" value={item.manufacturer.name} />
          <DetailField label="Filter Type" value={item.filter_type.display_name} />
          <DetailField label="Peak Transmission %" value={item.peak_transmission_pct != null ? `${item.peak_transmission_pct}%` : null} />
          <DetailField
            label="Sizes"
            value={
              item.size_options.length > 0
                ? item.size_options.map((so) => so.filter_size.name).join(", ")
                : null
            }
          />
          <DetailField
            label="Passbands"
            value={
              item.passbands.length > 0
                ? item.passbands
                    .map((pb) => {
                      const name = pb.line_name ?? `${pb.central_wavelength_nm}nm`;
                      const bw = pb.bandwidth_nm != null ? ` ±${pb.bandwidth_nm}nm` : "";
                      return `${name}${bw}`;
                    })
                    .join(", ")
                : null
            }
          />
          <DetailField label="Notes" value={item.notes ?? null} />
          <DetailField
            label="Source"
            value={item.source_url ? <ExternalLink href={item.source_url} /> : null}
          />
        </Box>
      )}
    />
  );
}
