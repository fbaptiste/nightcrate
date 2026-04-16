import { useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import Alert from "@mui/material/Alert";
import Box from "@mui/material/Box";
import Button from "@mui/material/Button";
import Collapse from "@mui/material/Collapse";
import Divider from "@mui/material/Divider";
import IconButton from "@mui/material/IconButton";
import Paper from "@mui/material/Paper";
import Snackbar from "@mui/material/Snackbar";
import Typography from "@mui/material/Typography";
import AddIcon from "@mui/icons-material/Add";
import CloseIcon from "@mui/icons-material/Close";
import RigCard from "@/components/rigs/RigCard";
import RigFormDialog from "@/components/rigs/RigFormDialog";
import CalculatorPanel from "@/components/rigs/CalculatorPanel";
import {
  fetchRigs,
  cloneRig,
  deleteRig,
  restoreRig,
  updateRig,
  type Rig,
} from "@/api/rigs";

export default function RigsPage() {
  const queryClient = useQueryClient();
  const { data: rigs = [], isLoading } = useQuery({
    queryKey: ["rigs"],
    queryFn: () => fetchRigs(false),
  });

  const [dialogOpen, setDialogOpen] = useState(false);
  const [editingRig, setEditingRig] = useState<Rig | null>(null);
  const [selectedRig, setSelectedRig] = useState<Rig | null>(null);
  const [snack, setSnack] = useState<{
    open: boolean;
    message: string;
    severity: "success" | "error";
  }>({ open: false, message: "", severity: "success" });

  const invalidate = () =>
    queryClient.invalidateQueries({ queryKey: ["rigs"] });

  const showSnack = (message: string, severity: "success" | "error") =>
    setSnack({ open: true, message, severity });

  const [retiredVisible, setRetiredVisible] = useState(false);

  const activeRigs = rigs.filter((r) => r.active);
  const retiredRigs = rigs.filter((r) => !r.active);

  // Keep selected rig in sync with latest data after refetch
  const resolvedSelected = selectedRig
    ? rigs.find((r) => r.id === selectedRig.id) ?? null
    : null;

  const handleNewRig = () => {
    setEditingRig(null);
    setDialogOpen(true);
  };

  const handleEdit = (rig: Rig) => {
    setEditingRig(rig);
    setDialogOpen(true);
  };

  const handleSelect = (rig: Rig) => {
    setSelectedRig((prev) => (prev?.id === rig.id ? null : rig));
  };

  const handleClone = async (id: number) => {
    try {
      await cloneRig(id);
      invalidate();
      showSnack("Rig cloned.", "success");
    } catch (err) {
      showSnack(
        err instanceof Error ? err.message : "Clone failed",
        "error",
      );
    }
  };

  const handleDelete = async (id: number) => {
    try {
      await deleteRig(id);
      if (selectedRig?.id === id) setSelectedRig(null);
      invalidate();
      showSnack("Rig retired.", "success");
    } catch (err) {
      showSnack(
        err instanceof Error ? err.message : "Delete failed",
        "error",
      );
    }
  };

  const handleRestore = async (id: number) => {
    try {
      await restoreRig(id);
      invalidate();
      showSnack("Rig restored.", "success");
    } catch (err) {
      showSnack(
        err instanceof Error ? err.message : "Restore failed",
        "error",
      );
    }
  };

  const handleSetDefault = async (id: number) => {
    try {
      await updateRig(id, { is_default: true });
      invalidate();
    } catch (err) {
      showSnack(
        err instanceof Error ? err.message : "Failed to set default",
        "error",
      );
    }
  };

  return (
    <Box sx={{ p: 3 }}>
      {/* Header */}
      <Box
        sx={{
          display: "flex",
          alignItems: "center",
          justifyContent: "space-between",
          mb: 3,
        }}
      >
        <Typography variant="h5">Rigs</Typography>
        <Button
          variant="contained"
          startIcon={<AddIcon />}
          onClick={handleNewRig}
        >
          New Rig
        </Button>
      </Box>

      {isLoading && (
        <Typography color="text.secondary">Loading...</Typography>
      )}

      {/* Empty state */}
      {!isLoading && rigs.length === 0 && (
        <Typography color="text.secondary" sx={{ textAlign: "center", mt: 6 }}>
          No rigs configured. Click &lsquo;New Rig&rsquo; to create your first
          imaging rig.
        </Typography>
      )}

      {/* Active rigs grid */}
      {activeRigs.length > 0 && (
        <Box
          sx={{
            display: "grid",
            gridTemplateColumns: "repeat(auto-fill, minmax(400px, 1fr))",
            gap: 2,
          }}
        >
          {activeRigs.map((rig) => (
            <RigCard
              key={rig.id}
              rig={rig}
              selected={resolvedSelected?.id === rig.id}
              onSelect={handleSelect}
              onEdit={handleEdit}
              onClone={handleClone}
              onDelete={handleDelete}
              onRestore={handleRestore}
              onSetDefault={handleSetDefault}
            />
          ))}
        </Box>
      )}

      {/* Retired rigs section */}
      {retiredRigs.length > 0 && (
        <Box sx={{ mt: 3 }}>
          <Typography
            variant="subtitle1"
            sx={{
              cursor: "pointer",
              userSelect: "none",
              color: "text.secondary",
              mb: 1,
            }}
            onClick={() => setRetiredVisible((v) => !v)}
          >
            {retiredVisible ? "\u25BE" : "\u25B8"} Retired Rigs (
            {retiredRigs.length})
          </Typography>
          {retiredVisible && (
            <Box
              sx={{
                display: "grid",
                gridTemplateColumns: "repeat(auto-fill, minmax(400px, 1fr))",
                gap: 2,
              }}
            >
              {retiredRigs.map((rig) => (
                <RigCard
                  key={rig.id}
                  rig={rig}
                  selected={resolvedSelected?.id === rig.id}
                  onSelect={handleSelect}
                  onEdit={handleEdit}
                  onClone={handleClone}
                  onDelete={handleDelete}
                  onRestore={handleRestore}
                  onSetDefault={handleSetDefault}
                />
              ))}
            </Box>
          )}
        </Box>
      )}

      {/* Detail panel — slides open below the card grid when a rig is selected */}
      <Collapse in={resolvedSelected !== null} timeout="auto" unmountOnExit>
        <Divider sx={{ mt: 3 }} />
        <Paper variant="outlined" sx={{ p: 2, mt: 1, position: "relative" }}>
          <IconButton
            size="small"
            onClick={() => setSelectedRig(null)}
            sx={{ position: "absolute", top: 8, right: 8 }}
          >
            <CloseIcon fontSize="small" />
          </IconButton>
          <Typography variant="h6" sx={{ mb: 1 }}>
            {resolvedSelected?.name}
          </Typography>
          {resolvedSelected && <CalculatorPanel rig={resolvedSelected} />}
        </Paper>
      </Collapse>

      {/* Rig form dialog */}
      <RigFormDialog
        open={dialogOpen}
        rig={editingRig}
        onClose={() => {
          setDialogOpen(false);
          setEditingRig(null);
        }}
        onSaved={() => queryClient.invalidateQueries({ queryKey: ["rigs"] })}
      />

      {/* Snackbar */}
      <Snackbar
        open={snack.open}
        autoHideDuration={3000}
        onClose={() => setSnack((s) => ({ ...s, open: false }))}
        anchorOrigin={{ vertical: "bottom", horizontal: "center" }}
      >
        <Alert
          severity={snack.severity}
          onClose={() => setSnack((s) => ({ ...s, open: false }))}
        >
          {snack.message}
        </Alert>
      </Snackbar>
    </Box>
  );
}
