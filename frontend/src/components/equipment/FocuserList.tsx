import Box from "@mui/material/Box";
import { type GridColDef } from "@mui/x-data-grid";
import EquipmentList from "./EquipmentList";
import FocuserFormDialog from "./FocuserFormDialog";
import { fetchFocusers, deleteFocuser, type Focuser } from "@/api/equipment";
import DetailField from "@/components/equipment/shared/DetailField";
import ExternalLink from "@/components/equipment/shared/ExternalLink";

const columns: GridColDef<Focuser>[] = [
  {
    field: "manufacturer",
    headerName: "Manufacturer",
    flex: 1,
    minWidth: 130,
    valueGetter: (_v, row) => row.manufacturer.name,
  },
  { field: "model_name", headerName: "Model", flex: 1.5, minWidth: 160 },
  {
    field: "focuser_type",
    headerName: "Type",
    flex: 1,
    minWidth: 120,
    valueGetter: (_v, row) => row.focuser_type?.name ?? "—",
  },
  {
    field: "motorized",
    headerName: "Motorized",
    width: 100,
    valueGetter: (_v, row) => (row.motorized ? "Yes" : "No"),
  },
  {
    field: "travel_range_mm",
    headerName: "Travel (mm)",
    width: 110,
    valueGetter: (_v, row) => row.travel_range_mm ?? "—",
  },
  {
    field: "total_steps",
    headerName: "Steps",
    width: 90,
    valueGetter: (_v, row) => row.total_steps ?? "—",
  },
];

export default function FocuserList({ mineOnly = false }: { mineOnly?: boolean } = {}) {
  return (
    <EquipmentList<Focuser>
      title={mineOnly ? "My Focusers" : "Focusers"}
      queryKey={mineOnly ? "my-focusers" : "focusers"}
      mineOnly={mineOnly}
      tableName="focuser"
      fetchFn={fetchFocusers}
      deleteFn={deleteFocuser}
      columns={columns}
      getItemName={(f) => f.model_name}
      FormDialog={FocuserFormDialog}
      renderDetail={(item) => (
        <Box sx={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 0, columnGap: 4 }}>
          <DetailField label="Manufacturer" value={item.manufacturer.name} />
          <DetailField label="Type" value={item.focuser_type?.name ?? null} />
          <DetailField label="Motorized" value={item.motorized ? "Yes" : "No"} />
          <DetailField label="Travel Range" value={item.travel_range_mm != null ? `${item.travel_range_mm}mm` : null} />
          <DetailField label="Step Size" value={item.step_size_um != null ? `${item.step_size_um}µm` : null} />
          <DetailField label="Total Steps" value={item.total_steps ?? null} />
          <DetailField label="Temperature Compensation" value={item.temperature_compensation ? "Yes" : "No"} />
          <DetailField label="Backlash Steps" value={item.backlash_steps ?? null} />
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
