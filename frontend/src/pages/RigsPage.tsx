import { useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import {
  DndContext,
  DragOverlay,
  closestCenter,
  PointerSensor,
  useSensor,
  useSensors,
  type DragEndEvent,
} from "@dnd-kit/core";
import {
  SortableContext,
  arrayMove,
  rectSortingStrategy,
  useSortable,
} from "@dnd-kit/sortable";
import { CSS } from "@dnd-kit/utilities";
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
import DragIndicatorIcon from "@mui/icons-material/DragIndicator";
import RigCard from "@/components/rigs/RigCard";
import RigFormDialog from "@/components/rigs/RigFormDialog";
import NewRigDialog from "@/components/rigs/NewRigDialog";
import RigDetailPanel from "@/components/rigs/RigDetailPanel";
import { setActivity } from "@/api/client";
import {
  fetchRigs,
  setRigMine,
  cloneRig,
  deleteRig,
  restoreRig,
  updateRig,
  reorderRigs,
  type Rig,
} from "@/api/rigs";

export default function RigsPage() {
  const queryClient = useQueryClient();
  // The whole catalog, retired rows included: this page owns claiming a
  // pre-defined rig and un-retiring one. Every other consumer wants only the
  // user's own kit and asks for ["rigs", "mine"] — a distinct key, because the
  // two share a prefix but not a result set. Invalidating ["rigs"] still hits
  // both.
  const { data: rigs = [], isLoading } = useQuery({
    queryKey: ["rigs", "all"],
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

  // Seeded all-in-one smart telescopes are a catalog, not the user's kit, so
  // they get their own collapsed section instead of padding out "my rigs".
  const activeRigs = rigs.filter((r) => r.active && r.is_mine);
  // Every unclaimed catalog rig belongs here regardless of `active`. Retiring a
  // catalog entry is not a meaningful state — it is either yours or it is not —
  // so a retired one would otherwise vanish into "Retired Rigs", which reads as
  // if the telescope itself had been discontinued.
  // Pre-defined rigs the user hasn't adopted are offered by the New Rig dialog,
  // not listed here — this page is "my rigs" and nothing else. A retired rig is
  // never on offer: deleting a customised pre-defined rig retires it precisely
  // so the edits survive, and re-offering it would hide them.
  const availablePredefined = rigs.filter(
    (r) => r.source === "seed" && r.active && !r.is_mine,
  );
  const retiredRigs = rigs.filter((r) => !r.active);

  const handleToggleMine = async (id: number, isMine: boolean) => {
    try {
      await setRigMine(id, isMine);
      invalidate();
      showSnack(isMine ? "Added to your rigs" : "Removed from your rigs", "success");
    } catch (e) {
      showSnack(e instanceof Error ? e.message : "Failed to update rig", "error");
    }
  };

  const resolvedSelected = selectedRig
    ? rigs.find((r) => r.id === selectedRig.id) ?? null
    : null;

  const sensors = useSensors(
    useSensor(PointerSensor, { activationConstraint: { distance: 5 } }),
  );

  const [draggingId, setDraggingId] = useState<number | null>(null);
  const draggingRig = draggingId
    ? rigs.find((r) => r.id === draggingId) ?? null
    : null;

  const handleDragEnd = async (event: DragEndEvent) => {
    const { active, over } = event;
    setDraggingId(null);
    if (!over || active.id === over.id) return;
    const oldIdx = activeRigs.findIndex((r) => r.id === active.id);
    const newIdx = activeRigs.findIndex((r) => r.id === over.id);
    if (oldIdx === -1 || newIdx === -1) return;
    const reordered = arrayMove(activeRigs, oldIdx, newIdx);
    queryClient.setQueryData<Rig[]>(["rigs"], (prev) => {
      if (!prev) return prev;
      // Everything that isn't in the reordered list — retired rigs and the
      // unclaimed pre-defined ones the New Rig dialog offers — must survive,
      // or they vanish from the cache until the refetch lands.
      const moved = new Set(reordered.map((r) => r.id));
      return [...reordered, ...prev.filter((r) => !moved.has(r.id))];
    });
    try {
      await reorderRigs(reordered.map((r) => r.id));
      invalidate();
    } catch {
      invalidate();
    }
  };

  const [chooserOpen, setChooserOpen] = useState(false);

  const handleNewRig = () => {
    setEditingRig(null);
    // Nothing left to adopt — don't make the user dismiss an empty chooser.
    if (availablePredefined.length === 0) {
      setDialogOpen(true);
      return;
    }
    setChooserOpen(true);
  };

  const handleChoosePredefined = async (rig: Rig) => {
    setChooserOpen(false);
    await handleToggleMine(rig.id, true);
  };

  const handleEdit = (rig: Rig) => {
    setEditingRig(rig);
    setDialogOpen(true);
  };

  const handleSelect = (rig: Rig) => {
    setSelectedRig((prev) => {
      const next = prev?.id === rig.id ? null : rig;
      setActivity(next ? `Rigs — ${next.name}` : "Rigs");
      return next;
    });
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
      const { outcome } = await deleteRig(id);
      if (selectedRig?.id === id) setSelectedRig(null);
      invalidate();
      // The server decides which happened, so say which rather than guess.
      showSnack(
        outcome === "removed"
          ? "Removed from your rigs."
          : "Rig retired — it had changes worth keeping.",
        "success",
      );
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
      {!isLoading && activeRigs.length === 0 && (
        <Typography color="text.secondary" sx={{ textAlign: "center", mt: 6 }}>
          No rigs yet. Click &lsquo;New Rig&rsquo; to add a pre-defined one or
          build your own.
        </Typography>
      )}

      {/* Active rigs — single-column sortable list */}
      {activeRigs.length > 0 && (
        <DndContext
          sensors={sensors}
          collisionDetection={closestCenter}
          onDragStart={(e) => setDraggingId(Number(e.active.id))}
          onDragCancel={() => setDraggingId(null)}
          onDragEnd={handleDragEnd}
        >
          <SortableContext
            items={activeRigs.map((r) => r.id)}
            strategy={rectSortingStrategy}
          >
            <Box
              sx={{
                display: "grid",
                gridTemplateColumns: { xs: "1fr", md: "1fr 1fr" },
                gap: 2,
                alignItems: "start",
              }}
            >
              {activeRigs.map((rig) => (
                <SortableRigCard
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
          </SortableContext>
          {/* The card travels with the pointer, leaving its slot free to act as
              the dashed drop indicator. */}
          <DragOverlay>
            {draggingRig && (
              <Box sx={{ opacity: 0.9, cursor: "grabbing" }}>
                <RigCard
                  rig={draggingRig}
                  onSelect={() => {}}
                  onEdit={() => {}}
                  onClone={() => {}}
                  onDelete={() => {}}
                  onRestore={() => {}}
                  onSetDefault={() => {}}
                />
              </Box>
            )}
          </DragOverlay>
        </DndContext>
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
            {retiredVisible ? "▾" : "▸"} Retired Rigs (
            {retiredRigs.length})
          </Typography>
          {retiredVisible && (
            <Box sx={{ display: "flex", flexDirection: "column", gap: 2 }}>
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

      {/* Detail panel */}
      <Collapse in={resolvedSelected !== null} timeout="auto" unmountOnExit>
        <Divider sx={{ mt: 3 }} />
        <Paper variant="outlined" sx={{ p: 2, mt: 1, position: "relative" }}>
          <IconButton
            size="small"
            onClick={() => setSelectedRig(null)}
            sx={{ position: "absolute", top: 8, right: 8, zIndex: 1 }}
            aria-label="Close rig detail"
          >
            <CloseIcon fontSize="small" />
          </IconButton>
          {resolvedSelected && <RigDetailPanel rig={resolvedSelected} />}
        </Paper>
      </Collapse>

      {/* Rig form dialog */}
      <NewRigDialog
        key={chooserOpen ? "open" : "closed"}
        open={chooserOpen}
        available={availablePredefined}
        onClose={() => setChooserOpen(false)}
        onChoosePredefined={handleChoosePredefined}
        onChooseCustom={() => {
          setChooserOpen(false);
          setEditingRig(null);
          setDialogOpen(true);
        }}
      />

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


function SortableRigCard({
  rig,
  selected,
  onSelect,
  onEdit,
  onClone,
  onDelete,
  onRestore,
  onSetDefault,
}: {
  rig: Rig;
  selected: boolean;
  onSelect: (r: Rig) => void;
  onEdit: (r: Rig) => void;
  onClone: (id: number) => void;
  onDelete: (id: number) => void;
  onRestore: (id: number) => void;
  onSetDefault: (id: number) => void;
}) {
  const { attributes, listeners, setNodeRef, transform, transition, isDragging } =
    useSortable({ id: rig.id });

  const style = {
    transform: CSS.Transform.toString(transform),
    transition,
  };

  // While this item is being dragged its card rides in the DragOverlay, so the
  // slot it leaves behind becomes the drop indicator: a dashed rectangle that
  // moves with the sort as other cards shift around it. Keeping the card
  // mounted but invisible preserves the slot's exact size.
  return (
    <Box
      ref={setNodeRef}
      style={style}
      sx={{
        display: "flex",
        alignItems: "stretch",
        ...(isDragging && {
          border: "2px dashed",
          borderColor: "primary.main",
          borderRadius: 1,
          bgcolor: "action.hover",
          "& > *": { visibility: "hidden" },
        }),
      }}
    >
      <Box
        {...attributes}
        {...listeners}
        sx={{
          display: "flex",
          alignItems: "center",
          px: 0.5,
          cursor: "grab",
          color: "text.disabled",
          "&:hover": { color: "text.secondary" },
        }}
      >
        <DragIndicatorIcon fontSize="small" />
      </Box>
      <Box sx={{ flex: 1, minWidth: 0 }}>
        <RigCard
          rig={rig}
          selected={selected}
          onSelect={onSelect}
          onEdit={onEdit}
          onClone={onClone}
          onDelete={onDelete}
          onRestore={onRestore}
          onSetDefault={onSetDefault}
        />
      </Box>
    </Box>
  );
}
