import { type GridColDef } from "@mui/x-data-grid";
import EquipmentList from "./EquipmentList";
import SensorFormDialog from "./SensorFormDialog";
import { fetchSensors, deleteSensor, type Sensor } from "@/api/equipment";

const columns: GridColDef<Sensor>[] = [
  { field: "model_name", headerName: "Model", flex: 1.5, minWidth: 160 },
  {
    field: "manufacturer",
    headerName: "Manufacturer",
    flex: 1,
    minWidth: 130,
    valueGetter: (_v, row) => row.manufacturer.name,
  },
  { field: "sensor_type", headerName: "Type", width: 80 },
  { field: "pixel_size_um", headerName: "Pixel (µm)", width: 100 },
  {
    field: "resolution",
    headerName: "Resolution",
    flex: 1,
    minWidth: 120,
    valueGetter: (_v, row) => `${row.resolution_x} × ${row.resolution_y}`,
  },
];

export default function SensorList() {
  return (
    <EquipmentList<Sensor>
      title="Sensors"
      queryKey="sensors"
      fetchFn={fetchSensors}
      deleteFn={deleteSensor}
      columns={columns}
      getItemName={(s) => s.model_name}
      FormDialog={SensorFormDialog}
    />
  );
}
