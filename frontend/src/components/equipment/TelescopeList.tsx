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
import { fetchTelescopes, deleteTelescope, type Telescope } from "@/api/equipment";
import ConfirmDeleteDialog from "@/components/equipment/shared/ConfirmDeleteDialog";
import TelescopeFormDialog from "./TelescopeFormDialog";

export default function TelescopeList() {
  const queryClient = useQueryClient();
  const [formOpen, setFormOpen] = useState(false);
  const [editTelescope, setEditTelescope] = useState<Telescope | null>(null);
  const [deleteTarget, setDeleteTarget] = useState<Telescope | null>(null);

  const { data: telescopes = [], isLoading } = useQuery({
    queryKey: ["telescopes"],
    queryFn: () => fetchTelescopes(),
  });

  const handleAdd = () => {
    setEditTelescope(null);
    setFormOpen(true);
  };

  const handleEdit = (telescope: Telescope) => {
    setEditTelescope(telescope);
    setFormOpen(true);
  };

  const handleFormClose = () => {
    setFormOpen(false);
    setEditTelescope(null);
  };

  const handleSaved = () => {
    void queryClient.invalidateQueries({ queryKey: ["telescopes"] });
  };

  const handleDeleteConfirm = async () => {
    if (!deleteTarget) return;
    await deleteTelescope(deleteTarget.id);
    void queryClient.invalidateQueries({ queryKey: ["telescopes"] });
    setDeleteTarget(null);
  };

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
    {
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
            aria-label={`Edit ${params.row.model_name}`}
          >
            <EditIcon fontSize="small" />
          </IconButton>
          <IconButton
            size="small"
            onClick={() => setDeleteTarget(params.row)}
            aria-label={`Retire ${params.row.model_name}`}
          >
            <DeleteIcon fontSize="small" />
          </IconButton>
        </Box>
      ),
    },
  ];

  return (
    <Box sx={{ display: "flex", flexDirection: "column", height: "100%" }}>
      <Box sx={{ display: "flex", alignItems: "center", mb: 2 }}>
        <Typography variant="h6" sx={{ flex: 1 }}>
          Telescopes
        </Typography>
        <Button variant="contained" startIcon={<AddIcon />} onClick={handleAdd}>
          Add Telescope
        </Button>
      </Box>

      <DataGrid
        rows={telescopes}
        columns={columns}
        loading={isLoading}
        autoHeight
        disableRowSelectionOnClick
        pageSizeOptions={[25, 50, 100]}
        initialState={{ pagination: { paginationModel: { pageSize: 25 } } }}
      />

      <TelescopeFormDialog
        open={formOpen}
        telescope={editTelescope}
        onClose={handleFormClose}
        onSaved={handleSaved}
      />

      <ConfirmDeleteDialog
        open={deleteTarget !== null}
        itemName={deleteTarget?.model_name ?? ""}
        onConfirm={handleDeleteConfirm}
        onCancel={() => setDeleteTarget(null)}
      />
    </Box>
  );
}
