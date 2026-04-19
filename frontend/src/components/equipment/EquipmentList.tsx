import { useEffect, useMemo, useRef, useState } from "react";
import { useSearchParams } from "react-router-dom";
import { DataGrid, type GridColDef, useGridApiRef } from "@mui/x-data-grid";
import Alert from "@mui/material/Alert";
import Box from "@mui/material/Box";
import Button from "@mui/material/Button";
import Collapse from "@mui/material/Collapse";
import Divider from "@mui/material/Divider";
import FormControlLabel from "@mui/material/FormControlLabel";
import IconButton from "@mui/material/IconButton";
import Paper from "@mui/material/Paper";
import Snackbar from "@mui/material/Snackbar";
import Switch from "@mui/material/Switch";
import Tooltip from "@mui/material/Tooltip";
import Typography from "@mui/material/Typography";
import AddIcon from "@mui/icons-material/Add";
import CloseIcon from "@mui/icons-material/Close";
import EditIcon from "@mui/icons-material/Edit";
import DeleteIcon from "@mui/icons-material/Delete";
import RestoreIcon from "@mui/icons-material/RestoreFromTrash";
import StarIcon from "@mui/icons-material/Star";
import StarOutlineIcon from "@mui/icons-material/StarOutline";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { restoreEquipmentItem, toggleEquipmentMine } from "@/api/equipment";
import ConfirmDeleteDialog from "@/components/equipment/shared/ConfirmDeleteDialog";

interface EquipmentListProps<T extends { id: number }> {
  title: string;
  addLabel?: string;
  queryKey: string;
  tableName: string;
  fetchFn: (includeRetired?: boolean, mine?: boolean) => Promise<T[]>;
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
  mineOnly?: boolean;
  /**
   * Column fields (beyond "manufacturer") whose filter input should be a
   * dropdown populated with the unique displayed values from the current
   * rows. Uses each column's `valueGetter` (or the raw row field) to
   * materialize the option list.
   */
  dropdownFilterFields?: string[];
}

function deriveAddLabel(title: string): string {
  const singular = title.endsWith("s") ? title.slice(0, -1) : title;
  return `Add ${singular}`;
}

export default function EquipmentList<T extends { id: number; active?: boolean; is_mine?: boolean }>({
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
  mineOnly = false,
  dropdownFilterFields,
}: EquipmentListProps<T>) {
  const queryClient = useQueryClient();
  const [formOpen, setFormOpen] = useState(false);
  const [editItem, setEditItem] = useState<T | null>(null);
  const [deleteTarget, setDeleteTarget] = useState<T | null>(null);
  const [showRetired, setShowRetired] = useState(false);
  const [detailItem, setDetailItem] = useState<T | null>(null);
  const [mineError, setMineError] = useState<string | null>(null);
  const apiRef = useGridApiRef();
  const pendingSelectId = useRef<number | null>(null);

  const [searchParams, setSearchParams] = useSearchParams();

  const { data: items = [], isLoading } = useQuery({
    queryKey: [queryKey, { showRetired, mineOnly }],
    queryFn: () => fetchFn(showRetired, mineOnly),
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

  const handleMineToggle = async (item: T) => {
    const newValue = !item.is_mine;
    // Optimistic cache update
    queryClient.setQueryData<T[]>(
      [queryKey, { showRetired, mineOnly }],
      (prev) =>
        prev?.map((row) =>
          row.id === item.id ? ({ ...row, is_mine: newValue } as T) : row,
        ) ?? prev,
    );
    try {
      await toggleEquipmentMine(tableName, item.id, newValue);
      void queryClient.invalidateQueries({ queryKey: [queryKey] });
      void queryClient.invalidateQueries({ queryKey: ["mine-counts"] });
    } catch (err) {
      // Roll back on failure
      queryClient.setQueryData<T[]>(
        [queryKey, { showRetired, mineOnly }],
        (prev) =>
          prev?.map((row) =>
            row.id === item.id ? ({ ...row, is_mine: !newValue } as T) : row,
          ) ?? prev,
      );
      setMineError(
        err instanceof Error ? err.message : "Failed to update 'mine' status",
      );
    }
  };

  const mineColumn: GridColDef<T> = {
    field: "is_mine",
    headerName: "",
    width: 48,
    sortable: false,
    filterable: false,
    renderHeader: () => (
      <Tooltip title="Mine">
        <StarOutlineIcon fontSize="small" />
      </Tooltip>
    ),
    renderCell: (params) => {
      const isMine = Boolean(params.row.is_mine);
      return (
        <IconButton
          size="small"
          onClick={(e) => {
            e.stopPropagation();
            void handleMineToggle(params.row);
          }}
          aria-label={
            isMine
              ? `Remove ${getItemName(params.row)} from My Equipment`
              : `Add ${getItemName(params.row)} to My Equipment`
          }
        >
          {isMine ? (
            <StarIcon fontSize="small" color="primary" />
          ) : (
            <StarOutlineIcon fontSize="small" />
          )}
        </IconButton>
      );
    },
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

  // Derive unique displayed values per field so selected columns get a
  // dropdown filter (type: 'singleSelect') instead of a free-text input.
  // "manufacturer" is included implicitly; wrappers can opt in additional
  // columns via `dropdownFilterFields`.
  const dropdownFields = useMemo(
    () => ["manufacturer", ...(dropdownFilterFields ?? [])],
    [dropdownFilterFields],
  );

  const dropdownOptions = useMemo(() => {
    const map = new Map<string, string[]>();
    if (items.length === 0) return map;
    const naturalSort = (a: string, b: string) =>
      a.localeCompare(b, undefined, { numeric: true, sensitivity: "base" });
    for (const field of dropdownFields) {
      const col = columns.find((c) => c.field === field);
      if (!col) continue;
      const values = new Set<string>();
      for (const item of items) {
        let raw: unknown;
        if (col.valueGetter) {
          raw = (col.valueGetter as (v: unknown, r: T) => unknown)(undefined, item);
        } else {
          raw = (item as Record<string, unknown>)[field];
        }
        if (raw == null || raw === "—" || raw === "") continue;
        values.add(String(raw));
      }
      if (values.size > 0) {
        map.set(field, Array.from(values).sort(naturalSort));
      }
    }
    return map;
  }, [items, columns, dropdownFields]);

  const augmentedColumns: GridColDef<T>[] = columns.map((col) => {
    const opts = dropdownOptions.get(col.field);
    if (!opts) return col;
    return { ...col, type: "singleSelect", valueOptions: opts } as GridColDef<T>;
  });

  const allColumns = [mineColumn, ...augmentedColumns, actionsColumn];
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
          slots={{
            noRowsOverlay: mineOnly
              ? () => (
                  <Box
                    sx={{
                      display: "flex",
                      alignItems: "center",
                      justifyContent: "center",
                      height: "100%",
                      p: 2,
                      color: "text.secondary",
                      fontStyle: "italic",
                      textAlign: "center",
                    }}
                  >
                    No equipment marked as yours yet. Open any item and check "Mark as
                    mine", or click the star in a list.
                  </Box>
                )
              : undefined,
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

      <Snackbar
        open={mineError !== null}
        autoHideDuration={4000}
        onClose={() => setMineError(null)}
        anchorOrigin={{ vertical: "bottom", horizontal: "center" }}
      >
        <Alert severity="warning" onClose={() => setMineError(null)}>
          {mineError}
        </Alert>
      </Snackbar>
    </Box>
  );
}
