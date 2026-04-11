import Box from "@mui/material/Box";
import { type GridColDef } from "@mui/x-data-grid";
import { fetchCameras, deleteCamera, type Camera } from "@/api/equipment";
import EquipmentList from "./EquipmentList";
import CameraFormDialog from "./CameraFormDialog";
import DetailField from "@/components/equipment/shared/DetailField";
import ExternalLink from "@/components/equipment/shared/ExternalLink";
import SensorLink from "@/components/equipment/shared/SensorLink";

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
    field: "sensor",
    headerName: "Sensor",
    flex: 2,
    minWidth: 200,
    valueGetter: (_value, row) => row.sensor.model_name,
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
      tableName="camera"
      fetchFn={fetchCameras}
      deleteFn={deleteCamera}
      columns={columns}
      getItemName={(c) => c.model_name}
      FormDialog={CameraForm}
      renderDetail={(item) => (
        <Box sx={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 0, columnGap: 4 }}>
          <DetailField label="Manufacturer" value={item.manufacturer.name} />
          <DetailField label="Sensor" value={<SensorLink sensor={item.sensor} />} />
          <DetailField label="Guide Sensor" value={item.guide_sensor ? <SensorLink sensor={item.guide_sensor} /> : null} />
          <DetailField label="Connector Size" value={item.connector_size?.name ?? null} />
          <DetailField label="Cooled" value={item.cooled ? "Yes" : "No"} />
          <DetailField label="Cooling Delta" value={item.cooling_delta_c != null ? `${item.cooling_delta_c}°C` : null} />
          <DetailField label="Back Focus" value={item.back_focus_mm != null ? `${item.back_focus_mm}mm` : null} />
          <DetailField label="Weight" value={item.weight_g != null ? `${item.weight_g}g` : null} />
          <DetailField label="Tilt Adapter" value={item.tilt_adapter ? "Yes" : "No"} />
          <DetailField label="USB Hub" value={item.has_usb_hub ? "Yes" : "No"} />
          <DetailField label="USB Hub Interface" value={item.usb_hub_interface?.name ?? null} />
          <DetailField label="Unity Gain" value={item.unity_gain ?? null} />
          <DetailField
            label="Interfaces"
            value={item.interfaces.length > 0 ? item.interfaces.map((i) => i.name).join(", ") : null}
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
