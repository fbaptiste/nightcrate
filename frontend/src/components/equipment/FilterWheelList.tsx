import Box from "@mui/material/Box";
import { type GridColDef } from "@mui/x-data-grid";
import EquipmentList from "./EquipmentList";
import FilterWheelFormDialog from "./FilterWheelFormDialog";
import { fetchFilterWheels, deleteFilterWheel, type FilterWheel } from "@/api/equipment";
import DetailField from "@/components/equipment/shared/DetailField";
import ExternalLink from "@/components/equipment/shared/ExternalLink";

const columns: GridColDef<FilterWheel>[] = [
  {
    field: "manufacturer",
    headerName: "Manufacturer",
    flex: 1,
    minWidth: 130,
    valueGetter: (_v, row) => row.manufacturer.name,
  },
  { field: "model_name", headerName: "Model", flex: 1.5, minWidth: 160 },
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

export default function FilterWheelList({ mineOnly = false }: { mineOnly?: boolean } = {}) {
  return (
    <EquipmentList<FilterWheel>
      title={mineOnly ? "My Filter Wheels" : "Filter Wheels"}
      queryKey={mineOnly ? "my-filter-wheels" : "filter-wheels"}
      mineOnly={mineOnly}
      tableName="filter_wheel"
      fetchFn={fetchFilterWheels}
      deleteFn={deleteFilterWheel}
      columns={columns}
      dropdownFilterFields={["filter_size", "num_positions"]}
      getItemName={(fw) => fw.model_name}
      FormDialog={FilterWheelFormDialog}
      renderDetail={(item) => (
        <Box sx={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 0, columnGap: 4 }}>
          <DetailField label="Manufacturer" value={item.manufacturer.name} />
          <DetailField label="Filter Size" value={item.filter_size?.name ?? null} />
          <DetailField label="Camera Side Connector" value={item.camera_side_connector?.name ?? null} />
          <DetailField label="Telescope Side Connector" value={item.telescope_side_connector?.name ?? null} />
          <DetailField label="Num Positions" value={item.num_positions} />
          <DetailField label="Back Focus Contribution" value={item.back_focus_contribution_mm != null ? `${item.back_focus_contribution_mm}mm` : null} />
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
