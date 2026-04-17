import Box from "@mui/material/Box";
import { type GridColDef } from "@mui/x-data-grid";
import EquipmentList from "./EquipmentList";
import MountFormDialog from "./MountFormDialog";
import { fetchMounts, deleteMount, type Mount } from "@/api/equipment";
import DetailField from "@/components/equipment/shared/DetailField";
import ExternalLink from "@/components/equipment/shared/ExternalLink";

const columns: GridColDef<Mount>[] = [
  {
    field: "manufacturer",
    headerName: "Manufacturer",
    flex: 1,
    minWidth: 130,
    valueGetter: (_v, row) => row.manufacturer.name,
  },
  { field: "model_name", headerName: "Model", flex: 1.5, minWidth: 160 },
  {
    field: "mount_type",
    headerName: "Type",
    flex: 1,
    minWidth: 120,
    valueGetter: (_v, row) => row.mount_type?.name ?? "—",
  },
  {
    field: "payload_capacity_kg",
    headerName: "Payload (kg)",
    width: 110,
    valueGetter: (_v, row) => row.payload_capacity_kg ?? "—",
  },
  {
    field: "goto_capable",
    headerName: "GoTo",
    width: 80,
    valueGetter: (_v, row) => (row.goto_capable ? "Yes" : "No"),
  },
];

export default function MountList({ mineOnly = false }: { mineOnly?: boolean } = {}) {
  return (
    <EquipmentList<Mount>
      title={mineOnly ? "My Mounts" : "Mounts"}
      queryKey={mineOnly ? "my-mounts" : "mounts"}
      mineOnly={mineOnly}
      tableName="mount"
      fetchFn={fetchMounts}
      deleteFn={deleteMount}
      columns={columns}
      getItemName={(m) => m.model_name}
      FormDialog={MountFormDialog}
      renderDetail={(item) => (
        <Box sx={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 0, columnGap: 4 }}>
          <DetailField label="Manufacturer" value={item.manufacturer.name} />
          <DetailField label="Mount Type" value={item.mount_type?.name ?? null} />
          <DetailField label="Payload Capacity" value={item.payload_capacity_kg != null ? `${item.payload_capacity_kg}kg` : null} />
          <DetailField label="Mount Weight" value={item.mount_weight_kg != null ? `${item.mount_weight_kg}kg` : null} />
          <DetailField label="Counterweight Required" value={item.counterweight_required ? "Yes" : "No"} />
          <DetailField label="GoTo Capable" value={item.goto_capable ? "Yes" : "No"} />
          <DetailField label="Periodic Error" value={item.periodic_error_arcsec != null ? `${item.periodic_error_arcsec}"` : null} />
          <DetailField label="Drive Type" value={item.drive_type ?? null} />
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
