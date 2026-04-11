import { useEffect, useRef, useState } from "react";
import { useSearchParams } from "react-router-dom";
import { DataGrid, type GridColDef, useGridApiRef } from "@mui/x-data-grid";
import Box from "@mui/material/Box";
import Button from "@mui/material/Button";
import Collapse from "@mui/material/Collapse";
import Divider from "@mui/material/Divider";
import FormControlLabel from "@mui/material/FormControlLabel";
import IconButton from "@mui/material/IconButton";
import Paper from "@mui/material/Paper";
import Switch from "@mui/material/Switch";
import Typography from "@mui/material/Typography";
import AddIcon from "@mui/icons-material/Add";
import CloseIcon from "@mui/icons-material/Close";
import EditIcon from "@mui/icons-material/Edit";
import DeleteIcon from "@mui/icons-material/Delete";
import RestoreIcon from "@mui/icons-material/RestoreFromTrash";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { restoreEquipmentItem } from "@/api/equipment";
import ConfirmDeleteDialog from "@/components/equipment/shared/ConfirmDeleteDialog";

interface EquipmentListProps<T extends { id: number }> {
  title: string;
  addLabel?: string;
  queryKey: string;
  tableName: string;
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
  /** Optional detail panel rendered below the grid when a row is clicked. */
  renderDetail?: (item: T) => React.ReactNode;
}

function deriveAddLabel(title: string): string {
  const singular = title.endsWith("s") ? title.slice(0, -1) : title;
  return `Add ${singular}`;
}

export default function EquipmentList<T extends { id: number; active?: boolean }>({
  title,
  addLabel,
  queryKey,
  tableName,
  fetchFn,
  deleteFn,
  columns,
  getItemName,
  FormDialog,
  renderDetail,
}: EquipmentListProps<T>) {
  const queryClient = useQueryClient();
  const [formOpen, setFormOpen] = useState(false);
  const [editItem, setEditItem] = useState<T | null>(null);
  const [deleteTarget, setDeleteTarget] = useState<T | null>(null);
  const [showRetired, setShowRetired] = useState(false);
  const [detailItem, setDetailItem] = useState<T | null>(null);
  const apiRef = useGridApiRef();
  const pendingSelectId = useRef<number | null>(null);

  const [searchParams, setSearchParams] = useSearchParams();

  const { data: items = [], isLoading } = useQuery({
    queryKey: [queryKey, { showRetired }],
    queryFn: () => fetchFn(showRetired),
  });

  // Auto-select item from URL ?select=ID param
  useEffect(() => {
    const selectId = searchParams.get("select");
    if (selectId && items.length > 0 && renderDetail) {
      const id = parseInt(selectId, 10);
      const found = items.find((item) => item.id === id);
      if (found) {
        setDetailItem(found);
        pendingSelectId.current = id;
        setSearchParams({}, { replace: true });
      }
    }
  }, [searchParams, items, renderDetail, setSearchParams]);

  // Scroll to the selected row after the grid has rendered
  useEffect(() => {
    if (pendingSelectId.current == null || items.length === 0) return;
    const id = pendingSelectId.current;
    // Small delay to let the DataGrid finish rendering sorted rows
    const timer = setTimeout(() => {
      try {
        const api = apiRef.current;
        if (!api) return;
        const rowIndex = api.getRowIndexRelativeToVisibleRows(id);
        if (rowIndex >= 0) {
          api.scrollToIndexes({ rowIndex });
        }
      } catch {
        // apiRef not ready yet — ignore
      }
      pendingSelectId.current = null;
    }, 100);
    return () => clearTimeout(timer);
  }, [detailItem, items, apiRef]);

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
    if (detailItem && (detailItem as T).id === deleteTarget.id) {
      setDetailItem(null);
    }
  };

  const handleRestore = async (item: T) => {
    await restoreEquipmentItem(tableName, item.id);
    void queryClient.invalidateQueries({ queryKey: [queryKey] });
  };

  const handleRowClick = (item: T) => {
    if (!renderDetail) return;
    setDetailItem((prev) => (prev?.id === item.id ? null : item));
  };

  const actionsColumn: GridColDef<T> = {
    field: "actions",
    headerName: "Actions",
    width: 100,
    sortable: false,
    filterable: false,
    renderCell: (params) => {
      const isRetired = params.row.active === false;
      if (isRetired) {
        return (
          <IconButton
            size="small"
            onClick={(e) => {
              e.stopPropagation();
              void handleRestore(params.row);
            }}
            aria-label={`Restore ${getItemName(params.row)}`}
            color="primary"
          >
            <RestoreIcon fontSize="small" />
          </IconButton>
        );
      }
      return (
        <Box>
          <IconButton
            size="small"
            onClick={(e) => {
              e.stopPropagation();
              handleEdit(params.row);
            }}
            aria-label={`Edit ${getItemName(params.row)}`}
          >
            <EditIcon fontSize="small" />
          </IconButton>
          <IconButton
            size="small"
            onClick={(e) => {
              e.stopPropagation();
              setDeleteTarget(params.row);
            }}
            aria-label={`Retire ${getItemName(params.row)}`}
          >
            <DeleteIcon fontSize="small" />
          </IconButton>
        </Box>
      );
    },
  };

  const allColumns = [...columns, actionsColumn];
  const buttonLabel = addLabel ?? deriveAddLabel(title);

  return (
    <Box sx={{ display: "flex", flexDirection: "column", height: "100%" }}>
      <Box sx={{ display: "flex", alignItems: "center", mb: 2 }}>
        <Typography variant="h6">
          {title}
        </Typography>
        <FormControlLabel
          control={
            <Switch
              size="small"
              checked={showRetired}
              onChange={(_, checked) => setShowRetired(checked)}
            />
          }
          label={<Typography variant="caption">Show Retired</Typography>}
          sx={{ ml: 2 }}
        />
        <Box sx={{ flex: 1 }} />
        <Button variant="contained" startIcon={<AddIcon />} onClick={handleAdd}>
          {buttonLabel}
        </Button>
      </Box>

      <Box sx={{ flex: 1, minHeight: 300 }}>
        <DataGrid
          apiRef={apiRef}
          rows={items}
          columns={allColumns}
          loading={isLoading}
          disableRowSelectionOnClick
          hideFooter
          initialState={{
            sorting: {
              sortModel: [
                { field: "manufacturer", sort: "asc" },
                { field: "model_name", sort: "asc" },
                { field: "name", sort: "asc" },
              ],
            },
          }}
          onRowClick={renderDetail ? (params) => handleRowClick(params.row) : undefined}
          getRowClassName={(params) => {
            const classes: string[] = [];
            if (params.row.active === false) classes.push("row-retired");
            if (renderDetail && detailItem?.id === params.row.id) classes.push("row-selected");
            if (renderDetail) classes.push("row-clickable");
            return classes.join(" ");
          }}
          sx={{
            border: 0,
            "& .row-retired": {
              opacity: 0.45,
              fontStyle: "italic",
            },
            "& .row-clickable": {
              cursor: "pointer",
            },
            "& .row-selected": {
              bgcolor: "action.selected",
            },
          }}
        />
      </Box>

      {/* Detail panel */}
      {renderDetail && (
        <Collapse in={detailItem !== null} unmountOnExit>
          <Divider sx={{ my: 1 }} />
          <Paper variant="outlined" sx={{ p: 2, position: "relative" }}>
            <IconButton
              size="small"
              onClick={() => setDetailItem(null)}
              sx={{ position: "absolute", top: 8, right: 8 }}
              aria-label="Close detail"
            >
              <CloseIcon fontSize="small" />
            </IconButton>
            <Typography variant="subtitle2" color="text.secondary" sx={{ mb: 1.5 }}>
              {detailItem ? getItemName(detailItem) : ""}
            </Typography>
            {detailItem && renderDetail(detailItem)}
          </Paper>
        </Collapse>
      )}

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
