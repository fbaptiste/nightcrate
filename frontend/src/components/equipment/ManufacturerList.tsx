import Box from "@mui/material/Box";
import { type GridColDef } from "@mui/x-data-grid";
import EquipmentList from "./EquipmentList";
import ManufacturerFormDialog from "./ManufacturerFormDialog";
import { fetchManufacturers, deleteManufacturer, type Manufacturer } from "@/api/equipment";
import DetailField from "@/components/equipment/shared/DetailField";
import ExternalLink from "@/components/equipment/shared/ExternalLink";

const columns: GridColDef<Manufacturer>[] = [
  { field: "name", headerName: "Name", flex: 1.5, minWidth: 160 },
  {
    field: "website",
    headerName: "Website",
    flex: 1.5,
    minWidth: 160,
    renderCell: (params) => {
      const url = params.row.website;
      if (!url) return "—";
      return <ExternalLink href={url} />;
    },
  },
  {
    field: "notes",
    headerName: "Notes",
    flex: 2,
    minWidth: 200,
    valueGetter: (_v, row) => row.notes ?? "—",
  },
];

export default function ManufacturerList() {
  return (
    <EquipmentList<Manufacturer>
      title="Manufacturers"
      queryKey="manufacturers"
      tableName="manufacturer"
      fetchFn={fetchManufacturers}
      deleteFn={deleteManufacturer}
      columns={columns}
      getItemName={(m) => m.name}
      FormDialog={ManufacturerFormDialog}
      renderDetail={(item) => (
        <Box sx={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 0, columnGap: 4 }}>
          <DetailField
            label="Website"
            value={item.website ? <ExternalLink href={item.website} /> : null}
          />
          <DetailField label="Notes" value={item.notes ?? null} />
        </Box>
      )}
    />
  );
}
