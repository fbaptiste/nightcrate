import Box from "@mui/material/Box";
import { type GridColDef } from "@mui/x-data-grid";
import EquipmentList from "./EquipmentList";
import SensorFormDialog from "./SensorFormDialog";
import { fetchSensors, deleteSensor, type Sensor } from "@/api/equipment";
import DetailField from "@/components/equipment/shared/DetailField";
import ExternalLink from "@/components/equipment/shared/ExternalLink";

const columns: GridColDef<Sensor>[] = [
  {
    field: "manufacturer",
    headerName: "Manufacturer",
    flex: 1,
    minWidth: 130,
    valueGetter: (_v, row) => row.manufacturer.name,
  },
  { field: "model_name", headerName: "Model", flex: 1.5, minWidth: 160 },
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
      tableName="sensor"
      fetchFn={fetchSensors}
      deleteFn={deleteSensor}
      columns={columns}
      getItemName={(s) => s.model_name}
      FormDialog={SensorFormDialog}
      hideMineColumn
      renderDetail={(item) => (
        <Box sx={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 0, columnGap: 4 }}>
          <DetailField label="Manufacturer" value={item.manufacturer.name} />
          <DetailField label="Model" value={item.model_name} />
          <DetailField label="Type" value={item.sensor_type} />
          <DetailField label="Pixel Size" value={`${item.pixel_size_um}µm`} />
          <DetailField label="Resolution" value={`${item.resolution_x} × ${item.resolution_y}`} />
          <DetailField
            label="Sensor Size (W×H mm)"
            value={
              item.sensor_width_mm != null && item.sensor_height_mm != null
                ? `${item.sensor_width_mm} × ${item.sensor_height_mm}mm`
                : null
            }
          />
          <DetailField label="ADC Bit Depth" value={item.adc_bit_depth ?? null} />
          <DetailField label="Full Well" value={item.full_well_capacity_ke != null ? `${item.full_well_capacity_ke}ke⁻` : null} />
          <DetailField label="Read Noise" value={item.read_noise_e != null ? `${item.read_noise_e}e⁻` : null} />
          <DetailField label="Peak QE" value={item.peak_qe_pct != null ? `${item.peak_qe_pct}%` : null} />
          <DetailField label="Bayer Pattern" value={item.bayer_pattern ?? null} />
          <DetailField label="Dual Gain" value={item.dual_gain ? "Yes" : "No"} />
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
