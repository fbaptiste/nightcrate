import { type GridColDef } from "@mui/x-data-grid";
import { fetchTelescopes, deleteTelescope, type Telescope } from "@/api/equipment";
import EquipmentList from "./EquipmentList";
import TelescopeFormDialog from "./TelescopeFormDialog";

function TelescopeForm({
  open,
  item,
  onClose,
  onSaved,
}: {
  open: boolean;
  item: Telescope | null;
  onClose: () => void;
  onSaved: () => void;
}) {
  return (
    <TelescopeFormDialog
      open={open}
      telescope={item}
      onClose={onClose}
      onSaved={onSaved}
    />
  );
}

const columns: GridColDef<Telescope>[] = [
  {
    field: "model_name",
    headerName: "Model",
    flex: 1.5,
    minWidth: 160,
  },
  {
    field: "manufacturer",
    headerName: "Manufacturer",
    flex: 1,
    minWidth: 130,
    valueGetter: (_value, row) => row.manufacturer.name,
  },
  {
    field: "optical_design",
    headerName: "Design",
    width: 130,
    valueGetter: (_value, row) => row.optical_design?.name ?? "—",
  },
  {
    field: "aperture_mm",
    headerName: "Aperture",
    width: 110,
    valueGetter: (_value, row) => `${row.aperture_mm}mm`,
  },
  {
    field: "configurations",
    headerName: "Configs",
    width: 90,
    valueGetter: (_value, row) => row.configurations.length,
  },
];

export default function TelescopeList() {
  return (
    <EquipmentList<Telescope>
      title="Telescopes"
      queryKey="telescopes"
      fetchFn={fetchTelescopes}
      deleteFn={deleteTelescope}
      columns={columns}
      getItemName={(t) => t.model_name}
      FormDialog={TelescopeForm}
    />
  );
}
