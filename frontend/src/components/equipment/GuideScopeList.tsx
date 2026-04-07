import { type GridColDef } from "@mui/x-data-grid";
import EquipmentList from "./EquipmentList";
import GuideScopeFormDialog from "./GuideScopeFormDialog";
import { fetchGuideScopes, deleteGuideScope, type GuideScope } from "@/api/equipment";

const columns: GridColDef<GuideScope>[] = [
  { field: "model_name", headerName: "Model", flex: 1.5, minWidth: 160 },
  {
    field: "manufacturer",
    headerName: "Manufacturer",
    flex: 1,
    minWidth: 130,
    valueGetter: (_v, row) => row.manufacturer.name,
  },
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
      fetchFn={fetchGuideScopes}
      deleteFn={deleteGuideScope}
      columns={columns}
      getItemName={(g) => g.model_name}
      FormDialog={GuideScopeFormDialog}
    />
  );
}
