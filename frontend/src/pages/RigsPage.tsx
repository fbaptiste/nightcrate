import { useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import Alert from "@mui/material/Alert";
import Box from "@mui/material/Box";
import Button from "@mui/material/Button";
import Snackbar from "@mui/material/Snackbar";
import Typography from "@mui/material/Typography";
import AddIcon from "@mui/icons-material/Add";
import RigCard from "@/components/rigs/RigCard";
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

  // Dialog state — will be wired to RigFormDialog in Task 8
  const [dialogOpen, setDialogOpen] = useState(false);
  const [editingRig, setEditingRig] = useState<Rig | null>(null);
  const [snack, setSnack] = useState<{
    open: boolean;
    message: string;
    severity: "success" | "error";
  }>({ open: false, message: "", severity: "success" });

  // Suppress unused-variable lint for state that Task 8 will consume
  void dialogOpen;
  void editingRig;

  const invalidate = () =>
    queryClient.invalidateQueries({ queryKey: ["rigs"] });

  const showSnack = (message: string, severity: "success" | "error") =>
    setSnack({ open: true, message, severity });

  const [retiredVisible, setRetiredVisible] = useState(false);

  const activeRigs = rigs.filter((r) => r.active);
  const retiredRigs = rigs.filter((r) => !r.active);

  const handleNewRig = () => {
    setEditingRig(null);
    setDialogOpen(true);
  };

  const handleEdit = (rig: Rig) => {
    setEditingRig(rig);
    setDialogOpen(true);
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
