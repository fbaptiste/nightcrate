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
import AddIcon from "@mui/icons-material/Add";
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
import ProjectSessionsTab from "@/components/projects/ProjectSessionsTab";
import ProjectMetadataSection from "@/components/projects/ProjectMetadataSection";
import IntegrationBars from "@/components/projects/IntegrationBars";
import AddTargetDialog from "@/components/projects/AddTargetDialog";
import MarkdownEditor from "@/components/common/MarkdownEditor";
import { getProjectSolve } from "@/api/projectSolve";
import { getIntegration } from "@/api/projectSessions";
import {
  addProjectTarget,
  listProjectTargets,
  removeProjectTarget,
} from "@/api/projectTargets";

export default function ProjectDetailPage() {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const projectId = Number(id);
  const [tab, setTab] = useState(0);
  const [snack, setSnack] = useState<string | null>(null);

  const [editingName, setEditingName] = useState(false);
  const [nameInput, setNameInput] = useState("");
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
  const { data: integration } = useQuery({
    queryKey: ["project-integration", projectId],
    queryFn: () => getIntegration(projectId),
    enabled: !isNaN(projectId),
  });

  // Main targets are persistent project_target rows — survive solve deletion;
  // populated either manually (Overview) or by a plate solve auto-flagging
  // its best-guess main object.
  const { data: mainTargets = [] } = useQuery({
    queryKey: ["project-targets", projectId],
    queryFn: () => listProjectTargets(projectId),
    enabled: !isNaN(projectId),
  });

  // DSOs that the current solve also identified — used to make those chips
  // clickable to jump to the Plate Solve tab.
  const solveDsoIds = useMemo(
    () => new Set((solve?.objects ?? []).map((o) => o.dso_id)),
    [solve],
  );

  const [addTargetOpen, setAddTargetOpen] = useState(false);

  const invalidateTargets = useCallback(() => {
    queryClient.invalidateQueries({ queryKey: ["project-targets", projectId] });
    // The solve response derives `is_main` from project_target, so refresh it
    // too — keeps the Plate Solve tab's star toggles in sync.
    queryClient.invalidateQueries({ queryKey: ["project-solve", projectId] });
  }, [queryClient, projectId]);

  const addTargetMut = useMutation({
    mutationFn: (dsoId: number) => addProjectTarget(projectId, dsoId),
    onSuccess: invalidateTargets,
    onError: (e) => setSnack(String(e)),
  });

  const removeTargetMut = useMutation({
    mutationFn: (dsoId: number) => removeProjectTarget(projectId, dsoId),
    onSuccess: invalidateTargets,
    onError: (e) => setSnack(String(e)),
  });

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

  const formatDate = (iso: string) =>
    // Anchor at midday to avoid a timezone day-shift when parsing a bare date.
    new Date(`${iso}T12:00:00`).toLocaleDateString(undefined, {
      year: "numeric",
      month: "short",
      day: "numeric",
    });
  const dateRange =
    integration?.first_session_date && integration?.last_session_date
      ? integration.first_session_date === integration.last_session_date
        ? formatDate(integration.first_session_date)
        : `${formatDate(integration.first_session_date)} – ${formatDate(integration.last_session_date)}`
      : null;

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
            sx={{ minWidth: 320 }}
          />
        ) : (
          <Typography
            variant="h5"
            fontWeight={600}
            sx={{ cursor: "pointer" }}
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
          sx={{ ml: "100px" }}
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
        <Tab label="Sessions" />
        <Tab label="Plate Solve" />
        <Tab label="Notes" />
      </Tabs>

      {tab === 1 && <ProjectSessionsTab projectId={projectId} />}
      {tab === 2 && <ProjectPlateSolveTab projectId={projectId} />}
      {tab === 3 && (
        <Box sx={{ maxWidth: 820 }}>
          <MarkdownEditor
            value={displayNotes}
            onSave={(next) => {
              const v = next.trim();
              if (v !== (project.notes ?? "")) metaMut.mutate({ notes: v });
            }}
            placeholder="Click to add notes..."
          />
        </Box>
      )}

      {/* Overview tab */}
      {tab === 0 && (
        <Box sx={{ maxWidth: 1280 }}>
          {/* Two-column row, sized to the image height so the description
              scrolls inside its column rather than overflowing below. */}
          <Box sx={{ display: "flex", gap: 3, mb: 2, height: 520 }}>
            <Box
              sx={{
                width: 520,
                height: 520,
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

            {/* RIGHT: metadata above, scrollable description below */}
            <Box
              sx={{
                flexGrow: 1,
                minWidth: 0,
                display: "flex",
                flexDirection: "column",
              }}
            >
              <Box sx={{ mb: 1.5 }}>
                <Box sx={{ display: "flex", alignItems: "center", gap: 0.5, mb: 0.5 }}>
                  <Typography variant="subtitle2" color="text.secondary">
                    Main targets
                  </Typography>
                  <IconButton
                    size="small"
                    onClick={() => setAddTargetOpen(true)}
                    aria-label="Add target"
                  >
                    <AddIcon fontSize="small" />
                  </IconButton>
                </Box>
                {mainTargets.length > 0 ? (
                  <Box sx={{ display: "flex", flexWrap: "wrap", gap: 0.5 }}>
                    {mainTargets.map((t) => (
                      <Chip
                        key={t.dso_id}
                        label={t.common_name ?? t.primary_designation}
                        size="small"
                        onClick={solveDsoIds.has(t.dso_id) ? () => setTab(2) : undefined}
                        onDelete={() => removeTargetMut.mutate(t.dso_id)}
                      />
                    ))}
                  </Box>
                ) : (
                  <Typography variant="body2" color="text.secondary">
                    No targets yet.
                  </Typography>
                )}
              </Box>

              {dateRange && (
                <Box sx={{ mb: 3 }}>
                  <Typography variant="subtitle2" color="text.secondary" sx={{ mb: 0.5 }}>
                    Imaging dates
                  </Typography>
                  <Typography variant="body2">{dateRange}</Typography>
                </Box>
              )}

              <Box sx={{ mb: 2 }}>
                <ProjectMetadataSection project={project} onUpdated={applyProject} />
              </Box>

              <Box sx={{ flexGrow: 1, minHeight: 0, overflowY: "auto" }}>
                <MarkdownEditor
                  value={displayDesc}
                  onSave={(next) => {
                    const v = next.trim();
                    if (v !== (project.description ?? "")) metaMut.mutate({ description: v });
                  }}
                  placeholder="Add description…"
                  minHeight={40}
                />
              </Box>
            </Box>
          </Box>

          {/* Thumbnails — full width below, given room to grow horizontally */}
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

          {/* Integration — left-aligned, narrow */}
          {integration && integration.lines.length > 0 && (
            <Box sx={{ mt: 3 }}>
              <IntegrationBars summary={integration} />
            </Box>
          )}

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

      <AddTargetDialog
        open={addTargetOpen}
        onClose={() => setAddTargetOpen(false)}
        onSelect={(dsoId) => addTargetMut.mutateAsync(dsoId)}
        excludeDsoIds={new Set(mainTargets.map((t: { dso_id: number }) => t.dso_id))}
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
