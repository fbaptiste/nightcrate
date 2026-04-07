import { type GridColDef } from "@mui/x-data-grid";
import EquipmentList from "./EquipmentList";
import FilterWheelFormDialog from "./FilterWheelFormDialog";
import { fetchFilterWheels, deleteFilterWheel, type FilterWheel } from "@/api/equipment";

const columns: GridColDef<FilterWheel>[] = [
  { field: "model_name", headerName: "Model", flex: 1.5, minWidth: 160 },
  {
    field: "manufacturer",
    headerName: "Manufacturer",
    flex: 1,
    minWidth: 130,
    valueGetter: (_v, row) => row.manufacturer.name,
  },
  {
    field: "filter_size",
    headerName: "Filter Size",
    flex: 1,
    minWidth: 110,
    valueGetter: (_v, row) => row.filter_size?.name ?? "—",
  },
  {
    field: "num_positions",
    headerName: "Positions",
    width: 100,
    valueGetter: (_v, row) => row.num_positions,
  },
  {
    field: "camera_side_connector",
    headerName: "Camera Connector",
    flex: 1,
    minWidth: 150,
    valueGetter: (_v, row) => row.camera_side_connector?.name ?? "—",
  },
  {
    field: "telescope_side_connector",
    headerName: "Telescope Connector",
    flex: 1,
    minWidth: 160,
    valueGetter: (_v, row) => row.telescope_side_connector?.name ?? "—",
  },
];

export default function FilterWheelList() {
  return (
    <EquipmentList<FilterWheel>
      title="Filter Wheels"
      queryKey="filter-wheels"
      fetchFn={fetchFilterWheels}
      deleteFn={deleteFilterWheel}
      columns={columns}
      getItemName={(fw) => fw.model_name}
      FormDialog={FilterWheelFormDialog}
    />
  );
}
