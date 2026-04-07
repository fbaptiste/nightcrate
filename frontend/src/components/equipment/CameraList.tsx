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
import { fetchCameras, deleteCamera, type Camera } from "@/api/equipment";
import ConfirmDeleteDialog from "@/components/equipment/shared/ConfirmDeleteDialog";
import CameraFormDialog from "./CameraFormDialog";

export default function CameraList() {
  const queryClient = useQueryClient();
  const [formOpen, setFormOpen] = useState(false);
  const [editCamera, setEditCamera] = useState<Camera | null>(null);
  const [deleteTarget, setDeleteTarget] = useState<Camera | null>(null);

  const { data: cameras = [], isLoading } = useQuery({
    queryKey: ["cameras"],
    queryFn: () => fetchCameras(),
  });

  const handleAdd = () => {
    setEditCamera(null);
    setFormOpen(true);
  };

  const handleEdit = (camera: Camera) => {
    setEditCamera(camera);
    setFormOpen(true);
  };

  const handleFormClose = () => {
    setFormOpen(false);
    setEditCamera(null);
  };

  const handleSaved = () => {
    void queryClient.invalidateQueries({ queryKey: ["cameras"] });
  };

  const handleDeleteConfirm = async () => {
    if (!deleteTarget) return;
    await deleteCamera(deleteTarget.id);
    void queryClient.invalidateQueries({ queryKey: ["cameras"] });
    setDeleteTarget(null);
  };

  const columns: GridColDef<Camera>[] = [
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
      field: "sensor",
      headerName: "Sensor",
      flex: 2,
      minWidth: 200,
      valueGetter: (_value, row) =>
        `${row.sensor.model_name} (${row.sensor.sensor_type})`,
    },
    {
      field: "cooled",
      headerName: "Cooled",
      width: 90,
      valueGetter: (_value, row) => (row.cooled ? "Yes" : "No"),
    },
    {
      field: "connector_size",
      headerName: "Connector",
      width: 120,
      valueGetter: (_value, row) => row.connector_size?.name ?? "—",
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
          Cameras
        </Typography>
        <Button variant="contained" startIcon={<AddIcon />} onClick={handleAdd}>
          Add Camera
        </Button>
      </Box>

      <DataGrid
        rows={cameras}
        columns={columns}
        loading={isLoading}
        autoHeight
        disableRowSelectionOnClick
        pageSizeOptions={[25, 50, 100]}
        initialState={{ pagination: { paginationModel: { pageSize: 25 } } }}
      />

      <CameraFormDialog
        open={formOpen}
        camera={editCamera}
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
