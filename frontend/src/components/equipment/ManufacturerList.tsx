import { type GridColDef } from "@mui/x-data-grid";
import EquipmentList from "./EquipmentList";
import ManufacturerFormDialog from "./ManufacturerFormDialog";
import { fetchManufacturers, deleteManufacturer, type Manufacturer } from "@/api/equipment";

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
      return (
        <a href={url} target="_blank" rel="noopener noreferrer" style={{ color: "inherit" }}>
          {url}
        </a>
      );
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
      fetchFn={fetchManufacturers}
      deleteFn={deleteManufacturer}
      columns={columns}
      getItemName={(m) => m.name}
      FormDialog={ManufacturerFormDialog}
    />
  );
}
