import { useCallback, useMemo, useState } from "react";
import Box from "@mui/material/Box";
import Button from "@mui/material/Button";
import IconButton from "@mui/material/IconButton";
import Snackbar from "@mui/material/Snackbar";
import Alert from "@mui/material/Alert";
import TextField from "@mui/material/TextField";
import Tooltip from "@mui/material/Tooltip";
import DeleteIcon from "@mui/icons-material/Delete";
import AddIcon from "@mui/icons-material/Add";
import EditIcon from "@mui/icons-material/Edit";
import EditOffIcon from "@mui/icons-material/EditOff";
import UndoIcon from "@mui/icons-material/Undo";
import {
  DataGrid,
  type GridColDef,
  type GridRenderCellParams,
  type GridRenderEditCellParams,
  useGridApiRef,
} from "@mui/x-data-grid";
import type { HeaderCard, HeaderOperation } from "@/api/images";
import { patchHeader } from "@/api/images";

/** Keywords that control FITS structure — must not be edited or deleted. */
const STRUCTURAL_KEYWORDS = new Set([
  "SIMPLE", "BITPIX", "NAXIS", "NAXIS1", "NAXIS2", "NAXIS3",
  "EXTEND", "BZERO", "BSCALE", "COMMENT", "HISTORY", "END", "",
]);

function isStructural(key: string): boolean {
  const upper = key.toUpperCase();
  return STRUCTURAL_KEYWORDS.has(upper) || upper.startsWith("NAXIS");
}

interface PendingChange {
  type: "update" | "delete";
  originalKey: string;
  value?: string;
  comment?: string;
}

interface PendingAdd {
  key: string;
  value: string;
  comment: string;
}

interface Props {
  cards: HeaderCard[];
  /** Whether the header can be edited (regular FITS file, not archive/virtual). */
  editable?: boolean;
  /** Absolute file path — needed for PATCH request. */
  path?: string;
  /** HDU index. */
  hdu?: number;
  /** Called after a successful save so the parent can invalidate queries. */
  onSaved?: () => void;
}

export function FitsHeaderTable({ cards, editable = false, path, hdu = 0, onSaved }: Props) {
  const apiRef = useGridApiRef();
  const [editing, setEditing] = useState(false);
  const [changes, setChanges] = useState<Map<string, PendingChange>>(new Map());
  const [additions, setAdditions] = useState<PendingAdd[]>([]);
  const [saving, setSaving] = useState(false);
  const [snackbar, setSnackbar] = useState<{ message: string; severity: "success" | "error" } | null>(null);

  // Add-row form state
  const [newKey, setNewKey] = useState("");
  const [newValue, setNewValue] = useState("");
  const [newComment, setNewComment] = useState("");

  const hasPending = changes.size > 0 || additions.length > 0;

  const handleDiscard = useCallback(() => {
    setChanges(new Map());
    setAdditions([]);
    setNewKey("");
    setNewValue("");
    setNewComment("");
    setEditing(false);
  }, []);

  const handleToggleEdit = useCallback(() => {
    if (editing && hasPending) {
      handleDiscard(); // clears changes and exits edit mode
      return;
    }
    setEditing((prev) => !prev);
  }, [editing, hasPending, handleDiscard]);

  const handleCellEdit = useCallback(
    (key: string, field: "value" | "comment", newVal: string) => {
      setChanges((prev) => {
        const next = new Map(prev);
        const existing = next.get(key);
        if (existing && existing.type === "delete") return next; // row is deleted, ignore
        const card = cards.find((c) => c.key === key);
        if (!card) return next;

        const merged: PendingChange = {
          type: "update",
          originalKey: key,
          value: existing?.value ?? card.value,
          comment: existing?.comment ?? (card.comment || card.description || ""),
          ...{ [field]: newVal },
        };

        // If nothing actually changed, remove the pending entry
        const originalValue = card.value;
        const originalComment = card.comment || card.description || "";
        if (merged.value === originalValue && merged.comment === originalComment) {
          next.delete(key);
        } else {
          next.set(key, merged);
        }
        return next;
      });
    },
    [cards],
  );

  const handleDelete = useCallback((key: string) => {
    setChanges((prev) => {
      const next = new Map(prev);
      next.set(key, { type: "delete", originalKey: key });
      return next;
    });
  }, []);

  const handleUndoDelete = useCallback((key: string) => {
    setChanges((prev) => {
      const next = new Map(prev);
      next.delete(key);
      return next;
    });
  }, []);

  const handleAddRow = useCallback(() => {
    const trimmedKey = newKey.trim().toUpperCase();
    if (!trimmedKey) return;
    if (isStructural(trimmedKey)) return;
    // Check for duplicates against existing keys and pending additions
    const existingKeys = new Set(cards.map((c) => c.key.toUpperCase()));
    const addedKeys = new Set(additions.map((a) => a.key.toUpperCase()));
    if (existingKeys.has(trimmedKey) || addedKeys.has(trimmedKey)) return;

    const newIndex = additions.length;
    setAdditions((prev) => [...prev, { key: trimmedKey, value: newValue, comment: newComment }]);
    setNewKey("");
    setNewValue("");
    setNewComment("");
    // Scroll to the newly added row after React re-renders
    requestAnimationFrame(() => {
      apiRef.current?.scrollToIndexes({ rowIndex: cards.length + newIndex });
    });
  }, [newKey, newValue, newComment, cards, additions, apiRef]);

  const handleRemoveAddition = useCallback((index: number) => {
    setAdditions((prev) => prev.filter((_, i) => i !== index));
  }, []);

  const handleAdditionEdit = useCallback(
    (addIndex: number, field: "key" | "value" | "comment", newVal: string) => {
      setAdditions((prev) =>
        prev.map((a, i) =>
          i === addIndex ? { ...a, [field]: field === "key" ? newVal.toUpperCase() : newVal } : a,
        ),
      );
    },
    [],
  );

  const handleSave = useCallback(async () => {
    if (!path) return;
    const operations: HeaderOperation[] = [];

    for (const change of changes.values()) {
      if (change.type === "delete") {
        operations.push({ op: "delete", key: change.originalKey });
      } else {
        const card = cards.find((c) => c.key === change.originalKey);
        const op: HeaderOperation = {
          op: "update",
          key: change.originalKey,
          value: change.value ?? "",
        };
        // Only send comment if it actually changed
        const originalComment = card?.comment || card?.description || "";
        if (change.comment !== undefined && change.comment !== originalComment) {
          op.comment = change.comment;
        }
        operations.push(op);
      }
    }

    for (const add of additions) {
      operations.push({ op: "add", key: add.key, value: add.value, comment: add.comment });
    }

    if (operations.length === 0) return;

    setSaving(true);
    try {
      await patchHeader(path, hdu, operations);
      setChanges(new Map());
      setAdditions([]);
      setEditing(false);
      setSnackbar({ message: "Header saved", severity: "success" });
      onSaved?.();
    } catch (err) {
      const message = err instanceof Error ? err.message : "Failed to save header";
      setSnackbar({ message, severity: "error" });
    } finally {
      setSaving(false);
    }
  }, [path, hdu, changes, additions, cards, onSaved]);

  const rows = useMemo(() => {
    const baseRows = cards.map((card, i) => {
      const change = changes.get(card.key);
      const isDeleted = change?.type === "delete";
      return {
        id: `existing-${i}`,
        key: card.key,
        value: change?.type === "update" && change.value !== undefined ? change.value : card.value,
        comment:
          change?.type === "update" && change.comment !== undefined
            ? change.comment
            : card.comment || card.description || "",
        _structural: isStructural(card.key),
        _deleted: isDeleted,
        _modified: change?.type === "update",
        _added: false,
        _addIndex: -1,
      };
    });

    const addRows = additions.map((add, i) => ({
      id: `add-${i}`,
      key: add.key,
      value: add.value,
      comment: add.comment,
      _structural: false,
      _deleted: false,
      _modified: false,
      _added: true,
      _addIndex: i,
    }));

    return [...baseRows, ...addRows];
  }, [cards, changes, additions]);

  const columns: GridColDef[] = useMemo(() => {
    const cols: GridColDef[] = [];

    if (editing) {
      cols.push({
        field: "_actions",
        headerName: "",
        width: 50,
        sortable: false,
        filterable: false,
        disableColumnMenu: true,
        renderCell: (params: GridRenderCellParams) => {
          if (params.row._structural) return null;
          if (params.row._deleted) {
            return (
              <Tooltip title="Undo delete">
                <IconButton size="small" onClick={() => handleUndoDelete(params.row.key)}>
                  <UndoIcon fontSize="small" />
                </IconButton>
              </Tooltip>
            );
          }
          if (params.row._added) {
            const addIndex = params.row._addIndex;
            return (
              <Tooltip title="Remove">
                <IconButton size="small" onClick={() => handleRemoveAddition(addIndex)}>
                  <DeleteIcon fontSize="small" />
                </IconButton>
              </Tooltip>
            );
          }
          return (
            <Tooltip title="Delete keyword">
              <IconButton size="small" onClick={() => handleDelete(params.row.key)}>
                <DeleteIcon fontSize="small" />
              </IconButton>
            </Tooltip>
          );
        },
      });
    }

    cols.push(
      {
        field: "key",
        headerName: "Keyword",
        width: 120,
        editable: editing,
        renderCell: (params: GridRenderCellParams) => (
          <Box
            component="span"
            sx={{
              fontFamily: "monospace",
              fontSize: "0.8rem",
              fontWeight: 600,
              textDecoration: params.row._deleted ? "line-through" : "none",
              opacity: params.row._deleted ? 0.5 : 1,
            }}
          >
            {params.value}
          </Box>
        ),
        renderEditCell: (params: GridRenderEditCellParams) => {
          const addIndex = params.row._addIndex;
          return (
            <TextField
              variant="standard"
              size="small"
              fullWidth
              autoFocus
              defaultValue={params.value}
              inputProps={{ sx: { fontFamily: "monospace", fontSize: "0.8rem", px: 1 }, maxLength: 8 }}
              onBlur={(e) => {
                handleAdditionEdit(addIndex, "key", e.target.value);
                apiRef.current?.stopCellEditMode({ id: params.id, field: "key" });
              }}
              onKeyDown={(e) => {
                if (e.key === "Enter") {
                  handleAdditionEdit(addIndex, "key", (e.target as HTMLInputElement).value);
                  apiRef.current?.stopCellEditMode({ id: params.id, field: "key" });
                } else if (e.key === "Escape") {
                  apiRef.current?.stopCellEditMode({ id: params.id, field: "key", ignoreModifications: true });
                }
              }}
            />
          );
        },
      },
      {
        field: "value",
        headerName: "Value",
        width: 200,
        editable: editing,
        renderCell: (params: GridRenderCellParams) => (
          <Box
            component="span"
            sx={{
              fontFamily: "monospace",
              fontSize: "0.8rem",
              textDecoration: params.row._deleted ? "line-through" : "none",
              opacity: params.row._deleted ? 0.5 : 1,
            }}
          >
            {params.value}
          </Box>
        ),
        renderEditCell: (params: GridRenderEditCellParams) => {
          const isAdded = params.row._added;
          const editFn = isAdded
            ? (val: string) => handleAdditionEdit(params.row._addIndex, "value", val)
            : (val: string) => handleCellEdit(params.row.key, "value", val);
          return (
            <TextField
              variant="standard"
              size="small"
              fullWidth
              autoFocus
              defaultValue={params.value}
              inputProps={{ sx: { fontFamily: "monospace", fontSize: "0.8rem", px: 1 } }}
              onBlur={(e) => {
                editFn(e.target.value);
                apiRef.current?.stopCellEditMode({ id: params.id, field: "value" });
              }}
              onKeyDown={(e) => {
                if (e.key === "Enter") {
                  editFn((e.target as HTMLInputElement).value);
                  apiRef.current?.stopCellEditMode({ id: params.id, field: "value" });
                } else if (e.key === "Escape") {
                  apiRef.current?.stopCellEditMode({ id: params.id, field: "value", ignoreModifications: true });
                }
              }}
            />
          );
        },
      },
      {
        field: "comment",
        headerName: "Comment",
        flex: 1,
        editable: editing,
        renderCell: (params: GridRenderCellParams) => (
          <Box
            component="span"
            sx={{
              fontSize: "0.8rem",
              color: "text.secondary",
              textDecoration: params.row._deleted ? "line-through" : "none",
              opacity: params.row._deleted ? 0.5 : 1,
            }}
          >
            {params.value}
          </Box>
        ),
        renderEditCell: (params: GridRenderEditCellParams) => {
          const isAdded = params.row._added;
          const editFn = isAdded
            ? (val: string) => handleAdditionEdit(params.row._addIndex, "comment", val)
            : (val: string) => handleCellEdit(params.row.key, "comment", val);
          return (
            <TextField
              variant="standard"
              size="small"
              fullWidth
              autoFocus
              defaultValue={params.value}
              inputProps={{ sx: { fontSize: "0.8rem", px: 1 } }}
              onBlur={(e) => {
                editFn(e.target.value);
                apiRef.current?.stopCellEditMode({ id: params.id, field: "comment" });
              }}
              onKeyDown={(e) => {
                if (e.key === "Enter") {
                  editFn((e.target as HTMLInputElement).value);
                  apiRef.current?.stopCellEditMode({ id: params.id, field: "comment" });
                } else if (e.key === "Escape") {
                  apiRef.current?.stopCellEditMode({ id: params.id, field: "comment", ignoreModifications: true });
                }
              }}
            />
          );
        },
      },
    );

    return cols;
  }, [editing, handleCellEdit, handleAdditionEdit, handleDelete, handleUndoDelete, handleRemoveAddition, apiRef]);

  const isCellEditable = useCallback(
    (params: { row: { _structural: boolean; _deleted: boolean; _added: boolean }; field: string }) => {
      if (!editing) return false;
      if (params.row._structural) return false;
      if (params.row._deleted) return false;
      // Key is only editable for added rows (existing keys can't be renamed)
      if (params.field === "key" && !params.row._added) return false;
      return true;
    },
    [editing],
  );

  const getRowClassName = useCallback(
    (params: { row: { _deleted: boolean; _modified: boolean; _added: boolean; _structural: boolean } }) => {
      if (params.row._deleted) return "row-deleted";
      if (params.row._added) return "row-added";
      if (params.row._modified) return "row-modified";
      if (params.row._structural && editing) return "row-structural";
      return "";
    },
    [editing],
  );

  return (
    <Box sx={{ display: "flex", flexDirection: "column", height: "100%" }}>
      {/* Toolbar */}
      {editable && (
        <Box sx={{ display: "flex", alignItems: "center", gap: 1, px: 1, py: 0.5, borderBottom: 1, borderColor: "divider" }}>
          <Tooltip title={editing ? "Exit edit mode" : "Edit header"}>
            <IconButton size="small" onClick={handleToggleEdit} color={editing ? "primary" : "default"}>
              {editing ? <EditOffIcon fontSize="small" /> : <EditIcon fontSize="small" />}
            </IconButton>
          </Tooltip>
          {editing && hasPending && (
            <>
              <Button
                size="small"
                variant="contained"
                disabled={saving}
                onClick={handleSave}
              >
                {saving ? "Saving..." : "Save"}
              </Button>
              <Button size="small" disabled={saving} onClick={handleDiscard}>
                Discard
              </Button>
            </>
          )}
        </Box>
      )}

      {/* Add keyword row */}
      {editing && (
        <Box sx={{ display: "flex", alignItems: "center", gap: 1, px: 1, py: 0.5, borderBottom: 1, borderColor: "divider" }}>
          <TextField
            size="small"
            variant="outlined"
            placeholder="KEYWORD"
            value={newKey}
            onChange={(e) => setNewKey(e.target.value.toUpperCase())}
            inputProps={{ sx: { fontFamily: "monospace", fontSize: "0.8rem" }, maxLength: 8 }}
            sx={{ width: 110 }}
          />
          <TextField
            size="small"
            variant="outlined"
            placeholder="Value"
            value={newValue}
            onChange={(e) => setNewValue(e.target.value)}
            inputProps={{ sx: { fontFamily: "monospace", fontSize: "0.8rem" } }}
            sx={{ width: 190 }}
          />
          <TextField
            size="small"
            variant="outlined"
            placeholder="Comment"
            value={newComment}
            onChange={(e) => setNewComment(e.target.value)}
            inputProps={{ sx: { fontSize: "0.8rem" } }}
            sx={{ flex: 0.5 }}
          />
          <Button
            size="small"
            variant="outlined"
            startIcon={<AddIcon />}
            onClick={handleAddRow}
            disabled={!newKey.trim()}
          >
            Add to headers
          </Button>
        </Box>
      )}

      {/* Data grid */}
      <Box sx={{ flexGrow: 1, overflow: "hidden" }}>
        <DataGrid
          apiRef={apiRef}
          rows={rows}
          columns={columns}
          density="compact"
          disableRowSelectionOnClick
          hideFooterSelectedRowCount
          pageSizeOptions={[50, 100, 200]}
          initialState={{ pagination: { paginationModel: { pageSize: 100 } } }}
          isCellEditable={isCellEditable}
          getRowClassName={getRowClassName}
          sx={{
            border: 0,
            height: "100%",
            "& .row-deleted": { bgcolor: "action.disabledBackground" },
            "& .row-modified": { bgcolor: "rgba(25, 118, 210, 0.08)" },
            "& .row-added": { bgcolor: "rgba(237, 108, 2, 0.08)" },
            "& .row-structural": { opacity: 0.5 },
          }}
        />
      </Box>

      {/* Snackbar feedback */}
      <Snackbar
        open={snackbar !== null}
        autoHideDuration={4000}
        onClose={() => setSnackbar(null)}
        anchorOrigin={{ vertical: "bottom", horizontal: "center" }}
      >
        {snackbar ? (
          <Alert onClose={() => setSnackbar(null)} severity={snackbar.severity} variant="filled">
            {snackbar.message}
          </Alert>
        ) : undefined}
      </Snackbar>
    </Box>
  );
}
