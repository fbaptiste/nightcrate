import { type GridColDef } from "@mui/x-data-grid";
import EquipmentList from "./EquipmentList";
import SoftwareFormDialog from "./SoftwareFormDialog";
import { fetchSoftwares, deleteSoftware, type Software } from "@/api/equipment";
import { formatFilterType } from "@/lib/formUtils";

const columns: GridColDef<Software>[] = [
  { field: "name", headerName: "Name", flex: 1.5, minWidth: 160 },
  {
    field: "manufacturer",
    headerName: "Manufacturer",
    flex: 1,
    minWidth: 130,
    valueGetter: (_v, row) => row.manufacturer?.name ?? "—",
  },
  {
    field: "category",
    headerName: "Category",
    flex: 1,
    minWidth: 120,
    valueGetter: (_v, row) => formatFilterType(row.category),
  },
  {
    field: "website",
    headerName: "Website",
    flex: 1.5,
    minWidth: 160,
    valueGetter: (_v, row) => row.website ?? "—",
  },
];

export default function SoftwareList() {
  return (
    <EquipmentList<Software>
      title="Software"
      addLabel="Add Software"
      queryKey="software"
      fetchFn={fetchSoftwares}
      deleteFn={deleteSoftware}
      columns={columns}
      getItemName={(s) => s.name}
      FormDialog={SoftwareFormDialog}
    />
  );
}
