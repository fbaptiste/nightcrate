import { type GridColDef } from "@mui/x-data-grid";
import { fetchFilters, deleteFilter, type Filter } from "@/api/equipment";
import { formatFilterType } from "@/lib/formUtils";
import EquipmentList from "./EquipmentList";
import FilterFormDialog from "./FilterFormDialog";

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
    field: "model_name",
    headerName: "Model",
    flex: 1.5,
    minWidth: 160,
  },
  {
    field: "manufacturer",
    headerName: "Manufacturer",
    flex: 1,
    minWidth: 130,
    valueGetter: (_value, row) => row.manufacturer.name,
  },
  {
    field: "filter_type",
    headerName: "Type",
    flex: 1,
    minWidth: 150,
    valueGetter: (_value, row) => formatFilterType(row.filter_type.name),
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
    field: "filter_size",
    headerName: "Size",
    width: 110,
    valueGetter: (_value, row) => row.filter_size?.name ?? "—",
  },
];

export default function FilterList() {
  return (
    <EquipmentList<Filter>
      title="Filters"
      queryKey="filters"
      fetchFn={fetchFilters}
      deleteFn={deleteFilter}
      columns={columns}
      getItemName={(f) => f.model_name}
      FormDialog={FilterForm}
    />
  );
}
