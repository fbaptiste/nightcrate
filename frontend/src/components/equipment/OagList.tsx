import Box from "@mui/material/Box";
import { type GridColDef } from "@mui/x-data-grid";
import EquipmentList from "./EquipmentList";
import OagFormDialog from "./OagFormDialog";
import { fetchOags, deleteOag, type Oag } from "@/api/equipment";
import DetailField from "@/components/equipment/shared/DetailField";
import ExternalLink from "@/components/equipment/shared/ExternalLink";

const columns: GridColDef<Oag>[] = [
  {
    field: "manufacturer",
    headerName: "Manufacturer",
    flex: 1,
    minWidth: 130,
    valueGetter: (_v, row) => row.manufacturer.name,
  },
  { field: "model_name", headerName: "Model", flex: 1.5, minWidth: 160 },
  {
    field: "imaging_side_connector",
    headerName: "Imaging Connector",
    flex: 1,
    minWidth: 140,
    valueGetter: (_v, row) => row.imaging_side_connector?.name ?? "—",
  },
  {
    field: "guide_camera_connector",
    headerName: "Guide Connector",
    flex: 1,
    minWidth: 130,
    valueGetter: (_v, row) => row.guide_camera_connector?.name ?? "—",
  },
  {
    field: "prism_size_mm",
    headerName: "Prism (mm)",
    width: 110,
    valueGetter: (_v, row) => row.prism_size_mm ?? "—",
  },
];

export default function OagList() {
  return (
    <EquipmentList<Oag>
      title="Off-Axis Guiders"
      queryKey="oags"
      tableName="oag"
      fetchFn={fetchOags}
      deleteFn={deleteOag}
      columns={columns}
      getItemName={(o) => o.model_name}
      FormDialog={OagFormDialog}
      renderDetail={(item) => (
        <Box sx={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 0, columnGap: 4 }}>
          <DetailField label="Manufacturer" value={item.manufacturer.name} />
          <DetailField label="Imaging Side Connector" value={item.imaging_side_connector?.name ?? null} />
          <DetailField label="Guide Camera Connector" value={item.guide_camera_connector?.name ?? null} />
          <DetailField label="Prism Size" value={item.prism_size_mm != null ? `${item.prism_size_mm}mm` : null} />
          <DetailField label="Back Focus Contribution" value={item.back_focus_contribution_mm != null ? `${item.back_focus_contribution_mm}mm` : null} />
          <DetailField label="Weight" value={item.weight_g != null ? `${item.weight_g}g` : null} />
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
