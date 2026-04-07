import { type GridColDef } from "@mui/x-data-grid";
import EquipmentList from "./EquipmentList";
import OagFormDialog from "./OagFormDialog";
import { fetchOags, deleteOag, type Oag } from "@/api/equipment";

const columns: GridColDef<Oag>[] = [
  { field: "model_name", headerName: "Model", flex: 1.5, minWidth: 160 },
  {
    field: "manufacturer",
    headerName: "Manufacturer",
    flex: 1,
    minWidth: 130,
    valueGetter: (_v, row) => row.manufacturer.name,
  },
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
      fetchFn={fetchOags}
      deleteFn={deleteOag}
      columns={columns}
      getItemName={(o) => o.model_name}
      FormDialog={OagFormDialog}
    />
  );
}
