import Box from "@mui/material/Box";
import { type GridColDef } from "@mui/x-data-grid";
import EquipmentList from "./EquipmentList";
import ComputerFormDialog from "./ComputerFormDialog";
import { fetchComputers, deleteComputer, type Computer } from "@/api/equipment";
import DetailField from "@/components/equipment/shared/DetailField";
import ExternalLink from "@/components/equipment/shared/ExternalLink";

const columns: GridColDef<Computer>[] = [
  {
    field: "manufacturer",
    headerName: "Manufacturer",
    flex: 1,
    minWidth: 130,
    valueGetter: (_v, row) => row.manufacturer.name,
  },
  { field: "model_name", headerName: "Model", flex: 1.5, minWidth: 160 },
  {
    field: "form_factor",
    headerName: "Type",
    flex: 1,
    minWidth: 120,
    valueGetter: (_v, row) => row.form_factor?.name ?? "—",
  },
];

export default function ComputerList() {
  return (
    <EquipmentList<Computer>
      title="Computers"
      queryKey="computers"
      tableName="computer"
      fetchFn={fetchComputers}
      deleteFn={deleteComputer}
      columns={columns}
      getItemName={(c) => c.model_name}
      FormDialog={ComputerFormDialog}
      renderDetail={(item) => (
        <Box sx={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 0, columnGap: 4 }}>
          <DetailField label="Manufacturer" value={item.manufacturer.name} />
          <DetailField label="Form Factor" value={item.form_factor?.name ?? null} />
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
