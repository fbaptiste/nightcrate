import { type GridColDef } from "@mui/x-data-grid";
import { fetchCameras, deleteCamera, type Camera } from "@/api/equipment";
import EquipmentList from "./EquipmentList";
import CameraFormDialog from "./CameraFormDialog";

function CameraForm({
  open,
  item,
  onClose,
  onSaved,
}: {
  open: boolean;
  item: Camera | null;
  onClose: () => void;
  onSaved: () => void;
}) {
  return (
    <CameraFormDialog
      open={open}
      camera={item}
      onClose={onClose}
      onSaved={onSaved}
    />
  );
}

const columns: GridColDef<Camera>[] = [
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
    field: "sensor",
    headerName: "Sensor",
    flex: 2,
    minWidth: 200,
    valueGetter: (_value, row) =>
      `${row.sensor.model_name} (${row.sensor.sensor_type})`,
  },
  {
    field: "cooled",
    headerName: "Cooled",
    width: 90,
    valueGetter: (_value, row) => (row.cooled ? "Yes" : "No"),
  },
  {
    field: "connector_size",
    headerName: "Connector",
    width: 120,
    valueGetter: (_value, row) => row.connector_size?.name ?? "—",
  },
];

export default function CameraList() {
  return (
    <EquipmentList<Camera>
      title="Cameras"
      queryKey="cameras"
      fetchFn={fetchCameras}
      deleteFn={deleteCamera}
      columns={columns}
      getItemName={(c) => c.model_name}
      FormDialog={CameraForm}
    />
  );
}
