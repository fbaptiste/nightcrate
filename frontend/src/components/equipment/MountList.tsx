import { type GridColDef } from "@mui/x-data-grid";
import EquipmentList from "./EquipmentList";
import MountFormDialog from "./MountFormDialog";
import { fetchMounts, deleteMount, type Mount } from "@/api/equipment";

const columns: GridColDef<Mount>[] = [
  { field: "model_name", headerName: "Model", flex: 1.5, minWidth: 160 },
  {
    field: "manufacturer",
    headerName: "Manufacturer",
    flex: 1,
    minWidth: 130,
    valueGetter: (_v, row) => row.manufacturer.name,
  },
  {
    field: "mount_type",
    headerName: "Type",
    flex: 1,
    minWidth: 120,
    valueGetter: (_v, row) => row.mount_type?.name ?? "—",
  },
  {
    field: "payload_capacity_kg",
    headerName: "Payload (kg)",
    width: 110,
    valueGetter: (_v, row) => row.payload_capacity_kg ?? "—",
  },
  {
    field: "goto_capable",
    headerName: "GoTo",
    width: 80,
    valueGetter: (_v, row) => (row.goto_capable ? "Yes" : "No"),
  },
];

export default function MountList() {
  return (
    <EquipmentList<Mount>
      title="Mounts"
      queryKey="mounts"
      fetchFn={fetchMounts}
      deleteFn={deleteMount}
      columns={columns}
      getItemName={(m) => m.model_name}
      FormDialog={MountFormDialog}
    />
  );
}
