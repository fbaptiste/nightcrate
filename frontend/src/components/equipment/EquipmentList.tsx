import { useState } from "react";
import { DataGrid, type GridColDef } from "@mui/x-data-grid";
import Box from "@mui/material/Box";
import Button from "@mui/material/Button";
import IconButton from "@mui/material/IconButton";
import Typography from "@mui/material/Typography";
import AddIcon from "@mui/icons-material/Add";
import EditIcon from "@mui/icons-material/Edit";
import DeleteIcon from "@mui/icons-material/Delete";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import ConfirmDeleteDialog from "@/components/equipment/shared/ConfirmDeleteDialog";

interface EquipmentListProps<T extends { id: number }> {
  title: string;
  addLabel?: string;
  queryKey: string;
  fetchFn: (includeRetired?: boolean) => Promise<T[]>;
  deleteFn: (id: number) => Promise<unknown>;
  columns: GridColDef<T>[];
  getItemName: (item: T) => string;
  FormDialog: React.ComponentType<{
    open: boolean;
    item: T | null;
    onClose: () => void;
    onSaved: () => void;
  }>;
}

function deriveAddLabel(title: string): string {
  // Strip trailing 's' for most plurals: "Cameras" → "Camera", "Telescopes" → "Telescope"
  const singular = title.endsWith("s") ? title.slice(0, -1) : title;
  return `Add ${singular}`;
}

export default function EquipmentList<T extends { id: number }>({
  title,
  addLabel,
  queryKey,
  fetchFn,
  deleteFn,
  columns,
  getItemName,
  FormDialog,
}: EquipmentListProps<T>) {
  const queryClient = useQueryClient();
  const [formOpen, setFormOpen] = useState(false);
  const [editItem, setEditItem] = useState<T | null>(null);
  const [deleteTarget, setDeleteTarget] = useState<T | null>(null);

  const { data: items = [], isLoading } = useQuery({
    queryKey: [queryKey],
    queryFn: () => fetchFn(),
  });

  const handleAdd = () => {
    setEditItem(null);
    setFormOpen(true);
  };

  const handleEdit = (item: T) => {
    setEditItem(item);
    setFormOpen(true);
  };

  const handleFormClose = () => {
    setFormOpen(false);
    setEditItem(null);
  };

  const handleSaved = () => {
    void queryClient.invalidateQueries({ queryKey: [queryKey] });
  };

  const handleDeleteConfirm = async () => {
    if (!deleteTarget) return;
    await deleteFn(deleteTarget.id);
    void queryClient.invalidateQueries({ queryKey: [queryKey] });
    setDeleteTarget(null);
  };

  const actionsColumn: GridColDef<T> = {
    field: "actions",
    headerName: "Actions",
    width: 100,
    sortable: false,
    filterable: false,
    renderCell: (params) => (
      <Box>
        <IconButton
          size="small"
          onClick={() => handleEdit(params.row)}
          aria-label={`Edit ${getItemName(params.row)}`}
        >
          <EditIcon fontSize="small" />
        </IconButton>
        <IconButton
          size="small"
          onClick={() => setDeleteTarget(params.row)}
          aria-label={`Retire ${getItemName(params.row)}`}
        >
          <DeleteIcon fontSize="small" />
        </IconButton>
      </Box>
    ),
  };

  const allColumns = [...columns, actionsColumn];
  const buttonLabel = addLabel ?? deriveAddLabel(title);

  return (
    <Box sx={{ display: "flex", flexDirection: "column", height: "100%" }}>
      <Box sx={{ display: "flex", alignItems: "center", mb: 2 }}>
        <Typography variant="h6" sx={{ flex: 1 }}>
          {title}
        </Typography>
        <Button variant="contained" startIcon={<AddIcon />} onClick={handleAdd}>
          {buttonLabel}
        </Button>
      </Box>

      <DataGrid
        rows={items}
        columns={allColumns}
        loading={isLoading}
        autoHeight
        disableRowSelectionOnClick
        pageSizeOptions={[25, 50, 100]}
        initialState={{ pagination: { paginationModel: { pageSize: 25 } } }}
      />

      <FormDialog
        open={formOpen}
        item={editItem}
        onClose={handleFormClose}
        onSaved={handleSaved}
      />

      <ConfirmDeleteDialog
        open={deleteTarget !== null}
        itemName={deleteTarget !== null ? getItemName(deleteTarget) : ""}
        onConfirm={handleDeleteConfirm}
        onCancel={() => setDeleteTarget(null)}
      />
    </Box>
  );
}
