import Box from "@mui/material/Box";
import { type GridColDef } from "@mui/x-data-grid";
import EquipmentList from "./EquipmentList";
import SoftwareFormDialog from "./SoftwareFormDialog";
import { fetchSoftwares, deleteSoftware, type Software } from "@/api/equipment";
import { formatSnakeCase } from "@/lib/formUtils";
import DetailField from "@/components/equipment/shared/DetailField";
import ExternalLink from "@/components/equipment/shared/ExternalLink";

const columns: GridColDef<Software>[] = [
  { field: "name", headerName: "Name", flex: 1.5, minWidth: 160 },
  {
    field: "manufacturer",
    headerName: "Manufacturer",
    flex: 1,
    minWidth: 130,
    valueGetter: (_v, row) => row.manufacturer?.name ?? "—",
  },
  {
    field: "category",
    headerName: "Category",
    flex: 1,
    minWidth: 120,
    valueGetter: (_v, row) => formatSnakeCase(row.category),
  },
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
];

export default function SoftwareList({ mineOnly = false }: { mineOnly?: boolean } = {}) {
  return (
    <EquipmentList<Software>
      title={mineOnly ? "My Software" : "Software"}
      addLabel="Add Software"
      queryKey={mineOnly ? "my-software" : "software"}
      mineOnly={mineOnly}
      tableName="software"
      fetchFn={fetchSoftwares}
      deleteFn={deleteSoftware}
      columns={columns}
      dropdownFilterFields={["category"]}
      getItemName={(s) => s.name}
      FormDialog={SoftwareFormDialog}
      renderDetail={(item) => (
        <Box sx={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 0, columnGap: 4 }}>
          <DetailField label="Manufacturer" value={item.manufacturer?.name ?? null} />
          <DetailField label="Category" value={formatSnakeCase(item.category)} />
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
