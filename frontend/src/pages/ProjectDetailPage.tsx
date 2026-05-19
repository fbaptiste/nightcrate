import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useParams, useNavigate, useBlocker } from "react-router-dom";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import Box from "@mui/material/Box";
import Button from "@mui/material/Button";
import Chip from "@mui/material/Chip";
import IconButton from "@mui/material/IconButton";
import CircularProgress from "@mui/material/CircularProgress";
import Snackbar from "@mui/material/Snackbar";
import Tab from "@mui/material/Tab";
import Tabs from "@mui/material/Tabs";
import TextField from "@mui/material/TextField";
import Typography from "@mui/material/Typography";
import ArrowBackIcon from "@mui/icons-material/ArrowBack";
import DeleteIcon from "@mui/icons-material/Delete";
import RestoreIcon from "@mui/icons-material/Restore";
import SaveIcon from "@mui/icons-material/Save";
import Dialog from "@mui/material/Dialog";
import DialogActions from "@mui/material/DialogActions";
import DialogContent from "@mui/material/DialogContent";
import DialogTitle from "@mui/material/DialogTitle";
import {
  fetchProject,
  saveProject,
  deleteProject,
  restoreProject,
  permanentlyDeleteProject,
  discardStaging,
  stageImages,
  unstageImage,
  renderedImageUrl,
  PROJECT_STATUS_COLORS,
  type ProjectSaveRequest,
} from "@/api/projects";
import ImageGalleryStrip from "@/components/projects/ImageGalleryStrip";

export default function ProjectDetailPage() {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const projectId = Number(id);
  const [tab, setTab] = useState(0);
  const [snack, setSnack] = useState<string | null>(null);

  // Staged metadata — local state, only persisted on Save.
  const [editedName, setEditedName] = useState<string | null>(null);
  const [editedDesc, setEditedDesc] = useState<string | null>(null);
  const [editedNotes, setEditedNotes] = useState<string | null>(null);
  const [removedImageIds, setRemovedImageIds] = useState<Set<number>>(new Set());
  const [imageOrder, setImageOrder] = useState<number[] | null>(null);
  const [mainImageId, setMainImageId] = useState<number | null>(null);
  const [editingName, setEditingName] = useState(false);
  const [nameInput, setNameInput] = useState("");
  const [editingDesc, setEditingDesc] = useState(false);
  const [descInput, setDescInput] = useState("");
  const [editingNotes, setEditingNotes] = useState(false);
  const [notesInput, setNotesInput] = useState("");
  const [confirmDeleteOpen, setConfirmDeleteOpen] = useState(false);

  const { data: project, isLoading } = useQuery({
    queryKey: ["project", projectId],
    queryFn: () => fetchProject(projectId),
    enabled: !isNaN(projectId),
  });

  // Discard any leftover staging from a previous interrupted session.
  const discardedRef = useRef(false);
  useEffect(() => {
    if (!project || discardedRef.current) return;
    const hasOrphanedStaging = project.images.some((i) => i.staged);
    if (hasOrphanedStaging) {
      discardStaging(projectId).then(() => {
        queryClient.invalidateQueries({ queryKey: ["project", projectId] });
      });
    }
    discardedRef.current = true;
  }, [project, projectId, queryClient]);

  const invalidate = useCallback(() => {
    queryClient.invalidateQueries({ queryKey: ["project", projectId] });
    queryClient.invalidateQueries({ queryKey: ["projects"] });
  }, [queryClient, projectId]);

  // Visible images: exclude removed, apply local order.
  const visibleImages = useMemo(() => {
    if (!project) return [];
    let imgs = project.images.filter((i) => !removedImageIds.has(i.id));
    if (imageOrder) {
      const orderMap = new Map(imageOrder.map((id, idx) => [id, idx]));
      imgs = [...imgs].sort(
        (a, b) => (orderMap.get(a.id) ?? a.display_order) - (orderMap.get(b.id) ?? b.display_order),
      );
    }
    return imgs;
  }, [project, removedImageIds, imageOrder]);

  const effectiveMainId = useMemo(() => {
    if (mainImageId && visibleImages.some((i) => i.id === mainImageId)) return mainImageId;
    const existing = visibleImages.find((i) => i.is_main);
    return existing?.id ?? visibleImages[0]?.id ?? null;
  }, [mainImageId, visibleImages]);

  const [viewedImageId, setViewedImageId] = useState<number | null>(null);
  const [mainImgLoaded, setMainImgLoaded] = useState(false);
  const viewedImage = useMemo(() => {
    if (!visibleImages.length) return null;
    if (viewedImageId) {
      const found = visibleImages.find((i) => i.id === viewedImageId);
      if (found) return found;
    }
    return visibleImages.find((i) => i.id === effectiveMainId) ?? visibleImages[0] ?? null;
  }, [visibleImages, viewedImageId, effectiveMainId]);

  const prevViewedRef = useRef<number | null>(null);
  if (viewedImage?.id !== prevViewedRef.current) {
    prevViewedRef.current = viewedImage?.id ?? null;
    if (mainImgLoaded) setMainImgLoaded(false);
  }

  // Dirty tracking.
  const hasStagedImages = project?.images.some((i) => i.staged) ?? false;
  const isDirty =
    editedName !== null ||
    editedDesc !== null ||
    editedNotes !== null ||
    removedImageIds.size > 0 ||
    imageOrder !== null ||
    mainImageId !== null ||
    hasStagedImages;

  // Block navigation when dirty — shows Save/Discard/Cancel dialog.
  const blocker = useBlocker(isDirty);
  const [exitDialogOpen, setExitDialogOpen] = useState(false);
  useEffect(() => {
    if (blocker.state === "blocked") setExitDialogOpen(true);
  }, [blocker.state]);

  const resetLocal = useCallback(() => {
    setEditedName(null);
    setEditedDesc(null);
    setEditedNotes(null);
    setRemovedImageIds(new Set());
    setImageOrder(null);
    setMainImageId(null);
    setViewedImageId(null);
  }, []);

  // Mutations.
  const stageMut = useMutation({
    mutationFn: (paths: string[]) => stageImages(projectId, paths),
    onSuccess: (imgs) => {
      invalidate();
      setSnack(`Staged ${imgs.length} image${imgs.length !== 1 ? "s" : ""}`);
    },
    onError: (err) => setSnack(String(err)),
  });

  const buildSaveRequest = useCallback((): ProjectSaveRequest => {
    const req: ProjectSaveRequest = {};
    if (editedName !== null) req.name = editedName;
    if (editedDesc !== null) {
      if (editedDesc === "") req.clear_description = true;
      else req.description = editedDesc;
    }
    if (editedNotes !== null) {
      if (editedNotes === "") req.clear_notes = true;
      else req.notes = editedNotes;
    }
    if (removedImageIds.size > 0) req.remove_image_ids = [...removedImageIds];
    if (imageOrder) req.image_order = imageOrder;
    if (mainImageId !== null) req.main_image_id = mainImageId;
    return req;
  }, [editedName, editedDesc, editedNotes, removedImageIds, imageOrder, mainImageId]);

  const saveMut = useMutation({
    mutationFn: () => saveProject(projectId, buildSaveRequest()),
    onSuccess: () => {
      resetLocal();
      invalidate();
      setSnack("Project saved");
    },
    onError: (err) => setSnack(String(err)),
  });

  const discardMut = useMutation({
    mutationFn: () => discardStaging(projectId),
    onSuccess: () => {
      resetLocal();
      invalidate();
      setSnack("Changes discarded");
    },
  });

  const deleteMut = useMutation({
    mutationFn: () => deleteProject(projectId),
    onSuccess: () => {
      invalidate();
      setSnack("Project retired");
    },
  });

  const restoreMut = useMutation({
    mutationFn: () => restoreProject(projectId),
    onSuccess: () => {
      invalidate();
      setSnack("Project restored");
    },
  });

  const permDeleteMut = useMutation({
    mutationFn: () => permanentlyDeleteProject(projectId),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["projects"] });
      navigate("/projects");
    },
    onError: (err) => setSnack(String(err)),
  });

  if (isLoading) {
    return (
      <Box sx={{ p: 3 }}>
        <Typography color="text.secondary">Loading project...</Typography>
      </Box>
    );
  }

  if (!project) {
    return (
      <Box sx={{ p: 3 }}>
        <Typography color="error">Project not found</Typography>
        <Button onClick={() => navigate("/projects")} sx={{ mt: 1 }}>
          Back to Projects
        </Button>
      </Box>
    );
  }

  const displayName = editedName ?? project.name;
  const displayDesc = editedDesc ?? project.description ?? "";
  const displayNotes = editedNotes ?? project.notes ?? "";

  return (
    <Box sx={{ p: 3, height: "100%", overflow: "auto" }}>
      {/* Header */}
      <Box sx={{ display: "flex", alignItems: "center", gap: 1, mb: 2 }}>
        <IconButton onClick={() => navigate("/projects")} size="small">
          <ArrowBackIcon />
        </IconButton>

        {editingName ? (
          <TextField
            size="small"
            autoFocus
            value={nameInput}
            onChange={(e) => setNameInput(e.target.value)}
            onBlur={() => {
              setEditingName(false);
              const trimmed = nameInput.trim();
              if (trimmed && trimmed !== project.name) setEditedName(trimmed);
            }}
            onKeyDown={(e) => {
              if (e.key === "Enter") (e.target as HTMLInputElement).blur();
              if (e.key === "Escape") setEditingName(false);
            }}
            sx={{ flexGrow: 1 }}
          />
        ) : (
          <Typography
            variant="h5"
            fontWeight={600}
            sx={{ flexGrow: 1, cursor: "pointer" }}
            onClick={() => {
              setNameInput(displayName);
              setEditingName(true);
            }}
          >
            {displayName}
          </Typography>
        )}

        <Chip
          label={project.status}
          size="small"
          color={PROJECT_STATUS_COLORS[project.status] ?? "default"}
        />

        <Button
          variant="contained"
          size="small"
          startIcon={<SaveIcon />}
          onClick={() => saveMut.mutate()}
          disabled={saveMut.isPending}
          sx={{ visibility: isDirty ? "visible" : "hidden" }}
        >
          Save
        </Button>
        <Button
          size="small"
          onClick={() => discardMut.mutate()}
          disabled={discardMut.isPending}
          sx={{ visibility: isDirty ? "visible" : "hidden" }}
        >
          Cancel
        </Button>

        {project.active ? (
          <IconButton
            size="small"
            onClick={() => deleteMut.mutate()}
            title="Retire project"
          >
            <DeleteIcon fontSize="small" />
          </IconButton>
        ) : (
          <>
            <Button
              size="small"
              onClick={() => restoreMut.mutate()}
              startIcon={<RestoreIcon />}
            >
              Restore
            </Button>
            <Button
              size="small"
              color="error"
              onClick={() => setConfirmDeleteOpen(true)}
              startIcon={<DeleteIcon />}
            >
              Delete permanently
            </Button>
          </>
        )}
      </Box>

      <Typography
        variant="caption"
        color="warning.main"
        sx={{ mb: 1, display: "block", visibility: isDirty ? "visible" : "hidden" }}
      >
        Unsaved changes
      </Typography>

      {/* Tabs */}
      <Tabs value={tab} onChange={(_, v) => setTab(v)} sx={{ mb: 2 }}>
        <Tab label="Overview" />
      </Tabs>

      {/* Overview tab */}
      {tab === 0 && (
        <Box>
          {/* Image + Description side by side */}
          <Box sx={{ display: "flex", gap: 3, mb: 2 }}>
            {/* Main image */}
            <Box
              sx={{
                width: 400,
                height: 400,
                flexShrink: 0,
                borderRadius: 1,
                overflow: "hidden",
                bgcolor: visibleImages.length > 0 ? "black" : undefined,
                border: visibleImages.length === 0 ? 2 : 0,
                borderColor: "divider",
                borderStyle: visibleImages.length === 0 ? "dashed" : undefined,
                display: "flex",
                alignItems: "center",
                justifyContent: "center",
              }}
            >
              {viewedImage ? (
                <>
                  {(!mainImgLoaded || stageMut.isPending) && (
                    <CircularProgress size={32} />
                  )}
                  <Box
                    component="img"
                    key={viewedImage.id}
                    src={renderedImageUrl(projectId, viewedImage.id, "thumb_lg")}
                    alt={displayName}
                    onLoad={() => setMainImgLoaded(true)}
                    sx={{
                      maxWidth: "100%",
                      maxHeight: "100%",
                      objectFit: "contain",
                      display: mainImgLoaded && !stageMut.isPending ? "block" : "none",
                    }}
                  />
                </>
              ) : stageMut.isPending ? (
                <CircularProgress size={32} />
              ) : (
                <Typography color="text.secondary" sx={{ px: 2, textAlign: "center" }}>
                  No images yet. Use the gallery strip below to add images.
                </Typography>
              )}
            </Box>

            {/* Description */}
            <Box sx={{ flexGrow: 1, minWidth: 0 }}>
              <Typography variant="subtitle2" color="text.secondary" sx={{ mb: 0.5 }}>
                Description
              </Typography>
              {editingDesc ? (
                <TextField
                  autoFocus
                  fullWidth
                  multiline
                  minRows={3}
                  maxRows={12}
                  size="small"
                  value={descInput}
                  onChange={(e) => setDescInput(e.target.value)}
                  onBlur={() => {
                    setEditingDesc(false);
                    const v = descInput.trim();
                    if (v !== (project.description ?? "")) {
                      setEditedDesc(v || "");
                    }
                  }}
                  onKeyDown={(e) => {
                    if (e.key === "Escape") setEditingDesc(false);
                  }}
                />
              ) : (
                <Typography
                  variant="body2"
                  sx={{
                    cursor: "pointer",
                    color: displayDesc ? "text.primary" : "text.secondary",
                    whiteSpace: "pre-wrap",
                    minHeight: 40,
                    p: 1,
                    borderRadius: 1,
                    "&:hover": { bgcolor: "action.hover" },
                  }}
                  onClick={() => {
                    setDescInput(displayDesc);
                    setEditingDesc(true);
                  }}
                >
                  {displayDesc || "Click to add a description..."}
                </Typography>
              )}
            </Box>
          </Box>

          {/* Image gallery strip */}
          <ImageGalleryStrip
            projectId={projectId}
            images={visibleImages}
            viewedImageId={viewedImage?.id ?? null}
            mainImageId={effectiveMainId}
            onViewImage={setViewedImageId}
            onSetMain={setMainImageId}
            onRemove={(imageId) => {
              const img = project.images.find((i) => i.id === imageId);
              if (img?.staged) {
                unstageImage(projectId, imageId).then(() => invalidate());
              } else {
                setRemovedImageIds((prev) => new Set([...prev, imageId]));
              }
            }}
            onReorder={(ids) => setImageOrder(ids)}
            onAddImages={(paths) => stageMut.mutate(paths)}
            isStaging={stageMut.isPending}
          />

          {/* Notes */}
          <Box sx={{ mt: 2 }}>
            <Typography variant="subtitle2" color="text.secondary" sx={{ mb: 0.5 }}>
              Notes
            </Typography>
            {editingNotes ? (
              <TextField
                autoFocus
                fullWidth
                multiline
                minRows={2}
                maxRows={10}
                size="small"
                value={notesInput}
                onChange={(e) => setNotesInput(e.target.value)}
                onBlur={() => {
                  setEditingNotes(false);
                  const v = notesInput.trim();
                  if (v !== (project.notes ?? "")) {
                    setEditedNotes(v || "");
                  }
                }}
                onKeyDown={(e) => {
                  if (e.key === "Escape") setEditingNotes(false);
                }}
              />
            ) : (
              <Typography
                variant="body2"
                sx={{
                  cursor: "pointer",
                  color: displayNotes ? "text.primary" : "text.secondary",
                  whiteSpace: "pre-wrap",
                  minHeight: 32,
                  p: 1,
                  borderRadius: 1,
                  "&:hover": { bgcolor: "action.hover" },
                }}
                onClick={() => {
                  setNotesInput(displayNotes);
                  setEditingNotes(true);
                }}
              >
                {displayNotes || "Click to add notes..."}
              </Typography>
            )}
          </Box>
        </Box>
      )}

      <Dialog open={confirmDeleteOpen} onClose={() => setConfirmDeleteOpen(false)}>
        <DialogTitle>Delete project permanently?</DialogTitle>
        <DialogContent>
          <Typography>
            This will permanently delete "{project.name}" and all its
            pre-calculated images. This cannot be undone.
          </Typography>
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setConfirmDeleteOpen(false)}>Cancel</Button>
          <Button
            color="error"
            variant="contained"
            onClick={() => {
              setConfirmDeleteOpen(false);
              permDeleteMut.mutate();
            }}
          >
            Delete permanently
          </Button>
        </DialogActions>
      </Dialog>

      {/* Unsaved changes — shown when navigating away while dirty */}
      <Dialog
        open={exitDialogOpen}
        onClose={() => {
          setExitDialogOpen(false);
          blocker.reset?.();
        }}
      >
        <DialogTitle>Unsaved changes</DialogTitle>
        <DialogContent>
          <Typography>
            You have unsaved changes. What would you like to do?
          </Typography>
        </DialogContent>
        <DialogActions>
          <Button
            onClick={() => {
              setExitDialogOpen(false);
              blocker.reset?.();
            }}
          >
            Stay on page
          </Button>
          <Button
            color="warning"
            onClick={async () => {
              setExitDialogOpen(false);
              await discardStaging(projectId).catch(() => {});
              resetLocal();
              blocker.proceed?.();
            }}
          >
            Discard
          </Button>
          <Button
            variant="contained"
            onClick={async () => {
              setExitDialogOpen(false);
              try {
                await saveProject(projectId, buildSaveRequest());
                resetLocal();
                blocker.proceed?.();
              } catch {
                setSnack("Save failed — staying on page");
                blocker.reset?.();
              }
            }}
          >
            Save
          </Button>
        </DialogActions>
      </Dialog>

      <Snackbar
        open={!!snack}
        autoHideDuration={3000}
        onClose={() => setSnack(null)}
        message={snack}
      />
    </Box>
  );
}
