import { type GridColDef } from "@mui/x-data-grid";
import EquipmentList from "./EquipmentList";
import FocuserFormDialog from "./FocuserFormDialog";
import { fetchFocusers, deleteFocuser, type Focuser } from "@/api/equipment";

const columns: GridColDef<Focuser>[] = [
  { field: "model_name", headerName: "Model", flex: 1.5, minWidth: 160 },
  {
    field: "manufacturer",
    headerName: "Manufacturer",
    flex: 1,
    minWidth: 130,
    valueGetter: (_v, row) => row.manufacturer.name,
  },
  {
    field: "motorized",
    headerName: "Motorized",
    width: 100,
    valueGetter: (_v, row) => (row.motorized ? "Yes" : "No"),
  },
  {
    field: "travel_range_mm",
    headerName: "Travel (mm)",
    width: 110,
    valueGetter: (_v, row) => row.travel_range_mm ?? "—",
  },
  {
    field: "total_steps",
    headerName: "Steps",
    width: 90,
    valueGetter: (_v, row) => row.total_steps ?? "—",
  },
];

export default function FocuserList() {
  return (
    <EquipmentList<Focuser>
      title="Focusers"
      queryKey="focusers"
      fetchFn={fetchFocusers}
      deleteFn={deleteFocuser}
      columns={columns}
      getItemName={(f) => f.model_name}
      FormDialog={FocuserFormDialog}
    />
  );
}
