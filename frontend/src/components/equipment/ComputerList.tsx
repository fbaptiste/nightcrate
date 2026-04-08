import { type GridColDef } from "@mui/x-data-grid";
import EquipmentList from "./EquipmentList";
import ComputerFormDialog from "./ComputerFormDialog";
import { fetchComputers, deleteComputer, type Computer } from "@/api/equipment";

const columns: GridColDef<Computer>[] = [
  { field: "model_name", headerName: "Model", flex: 1.5, minWidth: 160 },
  {
    field: "manufacturer",
    headerName: "Manufacturer",
    flex: 1,
    minWidth: 130,
    valueGetter: (_v, row) => row.manufacturer.name,
  },
  {
    field: "computer_type",
    headerName: "Type",
    flex: 1,
    minWidth: 120,
    valueGetter: (_v, row) => row.computer_type?.name ?? "—",
  },
];

export default function ComputerList() {
  return (
    <EquipmentList<Computer>
      title="Computers"
      queryKey="computers"
      fetchFn={fetchComputers}
      deleteFn={deleteComputer}
      columns={columns}
      getItemName={(c) => c.model_name}
      FormDialog={ComputerFormDialog}
    />
  );
}
