import Box from "@mui/material/Box";
import { type GridColDef } from "@mui/x-data-grid";
import EquipmentList from "./EquipmentList";
import GuideScopeFormDialog from "./GuideScopeFormDialog";
import { fetchGuideScopes, deleteGuideScope, type GuideScope } from "@/api/equipment";
import DetailField from "@/components/equipment/shared/DetailField";
import ExternalLink from "@/components/equipment/shared/ExternalLink";

const columns: GridColDef<GuideScope>[] = [
  {
    field: "manufacturer",
    headerName: "Manufacturer",
    flex: 1,
    minWidth: 130,
    valueGetter: (_v, row) => row.manufacturer.name,
  },
  { field: "model_name", headerName: "Model", flex: 1.5, minWidth: 160 },
  {
    field: "aperture_mm",
    headerName: "Aperture (mm)",
    width: 120,
    valueGetter: (_v, row) => row.aperture_mm ?? "—",
  },
  {
    field: "focal_length_mm",
    headerName: "Focal Length (mm)",
    width: 140,
    valueGetter: (_v, row) => row.focal_length_mm ?? "—",
  },
  {
    field: "guide_camera_connector",
    headerName: "Connector",
    flex: 1,
    minWidth: 120,
    valueGetter: (_v, row) => row.guide_camera_connector?.name ?? "—",
  },
];

export default function GuideScopeList() {
  return (
    <EquipmentList<GuideScope>
      title="Guide Scopes"
      queryKey="guide-scopes"
      tableName="guide_scope"
      fetchFn={fetchGuideScopes}
      deleteFn={deleteGuideScope}
      columns={columns}
      getItemName={(g) => g.model_name}
      FormDialog={GuideScopeFormDialog}
      renderDetail={(item) => (
        <Box sx={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 0, columnGap: 4 }}>
          <DetailField label="Manufacturer" value={item.manufacturer.name} />
          <DetailField label="Guide Camera Connector" value={item.guide_camera_connector?.name ?? null} />
          <DetailField label="Aperture" value={item.aperture_mm != null ? `${item.aperture_mm}mm` : null} />
          <DetailField label="Focal Length" value={item.focal_length_mm != null ? `${item.focal_length_mm}mm` : null} />
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
