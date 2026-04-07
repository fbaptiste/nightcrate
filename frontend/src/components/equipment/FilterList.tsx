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
import { fetchFilters, deleteFilter, type Filter } from "@/api/equipment";
import { formatFilterType } from "@/lib/formUtils";
import ConfirmDeleteDialog from "@/components/equipment/shared/ConfirmDeleteDialog";
import FilterFormDialog from "./FilterFormDialog";

function summarizePassbands(filter: Filter): string {
  if (filter.passbands.length === 0) return "—";
  const names = filter.passbands.map((pb) => pb.line_name ?? `${pb.central_wavelength_nm}nm`);
  return names.join(" + ");
}

export default function FilterList() {
  const queryClient = useQueryClient();
  const [formOpen, setFormOpen] = useState(false);
  const [editFilter, setEditFilter] = useState<Filter | null>(null);
  const [deleteTarget, setDeleteTarget] = useState<Filter | null>(null);

  const { data: filters = [], isLoading } = useQuery({
    queryKey: ["filters"],
    queryFn: () => fetchFilters(),
  });

  const handleAdd = () => {
    setEditFilter(null);
    setFormOpen(true);
  };

  const handleEdit = (filter: Filter) => {
    setEditFilter(filter);
    setFormOpen(true);
  };

  const handleFormClose = () => {
    setFormOpen(false);
    setEditFilter(null);
  };

  const handleSaved = () => {
    void queryClient.invalidateQueries({ queryKey: ["filters"] });
  };

  const handleDeleteConfirm = async () => {
    if (!deleteTarget) return;
    await deleteFilter(deleteTarget.id);
    void queryClient.invalidateQueries({ queryKey: ["filters"] });
    setDeleteTarget(null);
  };

  const columns: GridColDef<Filter>[] = [
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
      field: "filter_type",
      headerName: "Type",
      flex: 1,
      minWidth: 150,
      valueGetter: (_value, row) => formatFilterType(row.filter_type.name),
    },
    {
      field: "passbands",
      headerName: "Passbands",
      flex: 1.5,
      minWidth: 150,
      sortable: false,
      valueGetter: (_value, row) => summarizePassbands(row),
    },
    {
      field: "filter_size",
      headerName: "Size",
      width: 110,
      valueGetter: (_value, row) => row.filter_size?.name ?? "—",
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
          Filters
        </Typography>
        <Button variant="contained" startIcon={<AddIcon />} onClick={handleAdd}>
          Add Filter
        </Button>
      </Box>

      <DataGrid
        rows={filters}
        columns={columns}
        loading={isLoading}
        autoHeight
        disableRowSelectionOnClick
        pageSizeOptions={[25, 50, 100]}
        initialState={{ pagination: { paginationModel: { pageSize: 25 } } }}
      />

      <FilterFormDialog
        open={formOpen}
        filter={editFilter}
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
