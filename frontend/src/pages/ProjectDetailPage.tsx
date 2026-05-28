import { useCallback, useMemo, useRef, useState } from "react";
import { useParams, useNavigate } from "react-router-dom";
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
import Dialog from "@mui/material/Dialog";
import DialogActions from "@mui/material/DialogActions";
import DialogContent from "@mui/material/DialogContent";
import DialogTitle from "@mui/material/DialogTitle";
import {
  fetchProject,
  updateProject,
  deleteProject,
  restoreProject,
  permanentlyDeleteProject,
  addImages,
  removeImage,
  reorderImages,
  setMainImage,
  saveThumbnailCrops,
  renderedImageUrl,
  PROJECT_STATUS_COLORS,
  type Project,
  type ProjectUpdate,
  type ThumbnailCropDef,
} from "@/api/projects";
import ImageGalleryStrip from "@/components/projects/ImageGalleryStrip";
import ThumbnailCropEditor from "@/components/projects/ThumbnailCropEditor";
import ProjectPlateSolveTab from "@/components/projects/ProjectPlateSolveTab";
import { getProjectSolve } from "@/api/projectSolve";

export default function ProjectDetailPage() {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const projectId = Number(id);
  const [tab, setTab] = useState(0);
  const [snack, setSnack] = useState<string | null>(null);

  const [editingName, setEditingName] = useState(false);
  const [nameInput, setNameInput] = useState("");
  const [editingDesc, setEditingDesc] = useState(false);
  const [descInput, setDescInput] = useState("");
  const [editingNotes, setEditingNotes] = useState(false);
  const [notesInput, setNotesInput] = useState("");
  const [confirmDeleteOpen, setConfirmDeleteOpen] = useState(false);
  const [cropEditorOpen, setCropEditorOpen] = useState(false);

  const { data: project, isLoading } = useQuery({
    queryKey: ["project", projectId],
    queryFn: () => fetchProject(projectId),
    enabled: !isNaN(projectId),
  });

  const { data: solve } = useQuery({
    queryKey: ["project-solve", projectId],
    queryFn: () => getProjectSolve(projectId),
    enabled: !isNaN(projectId),
  });
  const mainTargets = (solve?.objects ?? []).filter((o) => o.is_main);

  const invalidate = useCallback(() => {
    queryClient.invalidateQueries({ queryKey: ["project", projectId] });
    queryClient.invalidateQueries({ queryKey: ["projects"] });
  }, [queryClient, projectId]);

  // Apply a server response directly to the cache (no extra round-trip),
  // and refresh the list view that shows thumbnails/counts.
  const applyProject = useCallback(
    (p: Project) => {
      queryClient.setQueryData(["project", projectId], p);
      queryClient.invalidateQueries({ queryKey: ["projects"] });
    },
    [queryClient, projectId],
  );

  const images = project?.images ?? [];

  const effectiveMainId = useMemo(() => {
    const existing = images.find((i) => i.is_main);
    return existing?.id ?? images[0]?.id ?? null;
  }, [images]);

  const [viewedImageId, setViewedImageId] = useState<number | null>(null);
  const [mainImgLoaded, setMainImgLoaded] = useState(false);
  const viewedImage = useMemo(() => {
    if (!images.length) return null;
    if (viewedImageId) {
      const found = images.find((i) => i.id === viewedImageId);
      if (found) return found;
    }
    return images.find((i) => i.id === effectiveMainId) ?? images[0] ?? null;
  }, [images, viewedImageId, effectiveMainId]);

  const prevViewedRef = useRef<number | null>(null);
  if (viewedImage?.id !== prevViewedRef.current) {
    prevViewedRef.current = viewedImage?.id ?? null;
    if (mainImgLoaded) setMainImgLoaded(false);
  }

  // ── Mutations ──────────────────────────────────────────────────────────
  const metaMut = useMutation({
    mutationFn: (patch: ProjectUpdate) => updateProject(projectId, patch),
    onSuccess: applyProject,
    onError: (err) => setSnack(String(err)),
  });

  const addMut = useMutation({
    mutationFn: (paths: string[]) => addImages(projectId, paths),
    onSuccess: (imgs) => {
      invalidate();
      setSnack(`Added ${imgs.length} image${imgs.length !== 1 ? "s" : ""}`);
    },
    onError: (err) => setSnack(String(err)),
  });

  const removeMut = useMutation({
    mutationFn: (imageId: number) => removeImage(projectId, imageId),
    onSuccess: invalidate,
    onError: (err) => setSnack(String(err)),
  });

  const reorderMut = useMutation({
    mutationFn: (ids: number[]) => reorderImages(projectId, ids),
    onMutate: async (ids) => {
      await queryClient.cancelQueries({ queryKey: ["project", projectId] });
      const prev = queryClient.getQueryData<Project>(["project", projectId]);
      if (prev) {
        const byId = new Map(prev.images.map((i) => [i.id, i]));
        const reordered = ids
          .map((id, idx) => {
            const img = byId.get(id);
            return img ? { ...img, display_order: idx } : null;
          })
          .filter((i): i is NonNullable<typeof i> => i !== null);
        queryClient.setQueryData<Project>(["project", projectId], { ...prev, images: reordered });
      }
      return { prev };
    },
    onError: (err, _ids, ctx) => {
      if (ctx?.prev) queryClient.setQueryData(["project", projectId], ctx.prev);
      setSnack(String(err));
    },
    onSettled: invalidate,
  });

  const mainMut = useMutation({
    mutationFn: (imageId: number) => setMainImage(projectId, imageId),
    onSuccess: applyProject,
    onError: (err) => setSnack(String(err)),
  });

  const cropMut = useMutation({
    mutationFn: (crops: Record<string, ThumbnailCropDef>) =>
      saveThumbnailCrops(projectId, crops),
    onSuccess: (p) => {
      applyProject(p);
      setSnack("Thumbnails updated");
    },
    onError: (err) => setSnack(String(err)),
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

  const displayDesc = project.description ?? "";
  const displayNotes = project.notes ?? "";

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
              if (trimmed && trimmed !== project.name) metaMut.mutate({ name: trimmed });
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
              setNameInput(project.name);
              setEditingName(true);
            }}
          >
            {project.name}
          </Typography>
        )}

        <Chip
          label={project.status}
          size="small"
          color={PROJECT_STATUS_COLORS[project.status] ?? "default"}
        />

        {project.active ? (
          <IconButton size="small" onClick={() => deleteMut.mutate()} title="Retire project">
            <DeleteIcon fontSize="small" />
          </IconButton>
        ) : (
          <>
            <Button size="small" onClick={() => restoreMut.mutate()} startIcon={<RestoreIcon />}>
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

      {/* Tabs */}
      <Tabs value={tab} onChange={(_, v) => setTab(v)} sx={{ mb: 2 }}>
        <Tab label="Overview" />
        <Tab label="Plate Solve" />
      </Tabs>

      {tab === 1 && <ProjectPlateSolveTab projectId={projectId} />}

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
                bgcolor: images.length > 0 ? "common.black" : undefined,
                border: images.length === 0 ? 2 : 0,
                borderColor: "divider",
                borderStyle: images.length === 0 ? "dashed" : undefined,
                display: "flex",
                alignItems: "center",
                justifyContent: "center",
              }}
            >
              {viewedImage ? (
                <>
                  {(!mainImgLoaded || addMut.isPending) && <CircularProgress size={32} />}
                  <Box
                    component="img"
                    key={viewedImage.id}
                    src={renderedImageUrl(projectId, viewedImage.id, "thumb_lg")}
                    alt={project.name}
                    onLoad={() => setMainImgLoaded(true)}
                    sx={{
                      maxWidth: "100%",
                      maxHeight: "100%",
                      objectFit: "contain",
                      display: mainImgLoaded && !addMut.isPending ? "block" : "none",
                    }}
                  />
                </>
              ) : addMut.isPending ? (
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
                    if (v !== (project.description ?? "")) metaMut.mutate({ description: v });
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

              {mainTargets.length > 0 && (
                <Box sx={{ mt: 1.5 }}>
                  <Typography variant="subtitle2" color="text.secondary" sx={{ mb: 0.5 }}>
                    Main targets
                  </Typography>
                  <Box sx={{ display: "flex", flexWrap: "wrap", gap: 0.5 }}>
                    {mainTargets.map((o) => (
                      <Chip
                        key={o.dso_id}
                        label={o.common_name ?? o.primary_designation}
                        size="small"
                        onClick={() => setTab(1)}
                      />
                    ))}
                  </Box>
                </Box>
              )}
            </Box>
          </Box>

          {/* Image gallery strip */}
          <ImageGalleryStrip
            projectId={projectId}
            images={images}
            viewedImageId={viewedImage?.id ?? null}
            mainImageId={effectiveMainId}
            onViewImage={setViewedImageId}
            onSetMain={(imageId) => mainMut.mutate(imageId)}
            onRemove={(imageId) => removeMut.mutate(imageId)}
            onReorder={(ids) => reorderMut.mutate(ids)}
            onAddImages={(paths) => addMut.mutate(paths)}
            isAdding={addMut.isPending}
          />

          {images.length > 0 && (
            <Button size="small" onClick={() => setCropEditorOpen(true)} sx={{ mt: 0.5 }}>
              Customize thumbnails
            </Button>
          )}

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
                  if (v !== (project.notes ?? "")) metaMut.mutate({ notes: v });
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
            This will permanently delete "{project.name}" and all its pre-calculated images. This
            cannot be undone.
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

      <ThumbnailCropEditor
        open={cropEditorOpen}
        onClose={() => setCropEditorOpen(false)}
        projectId={projectId}
        images={images}
        mainImageId={effectiveMainId}
        existingCrops={project.thumbnail_crops}
        onApply={(crops) => cropMut.mutate(crops)}
      />

      <Snackbar
        open={!!snack}
        autoHideDuration={3000}
        onClose={() => setSnack(null)}
        message={snack}
      />
    </Box>
  );
}
