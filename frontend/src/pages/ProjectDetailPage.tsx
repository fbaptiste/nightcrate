import { useCallback, useLayoutEffect, useMemo, useRef, useState } from "react";
import { useParams, useNavigate, useSearchParams } from "react-router-dom";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import Box from "@mui/material/Box";
import Button from "@mui/material/Button";
import Chip from "@mui/material/Chip";
import Tooltip from "@mui/material/Tooltip";
import IconButton from "@mui/material/IconButton";
import OpenInFullIcon from "@mui/icons-material/OpenInFull";
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
  fetchProjectRigSetups,
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
  type Project,
  type ProjectUpdate,
  type CropSize,
  type ThumbnailCropDef,
} from "@/api/projects";
import ImageGalleryStrip from "@/components/projects/ImageGalleryStrip";
import ThumbnailCropEditor from "@/components/projects/ThumbnailCropEditor";
import ProjectCatalogTab from "@/components/projects/ProjectCatalogTab";
import ProjectPlateSolveTab from "@/components/projects/ProjectPlateSolveTab";
import ProjectSessionsTab from "@/components/projects/ProjectSessionsTab";
import ProjectNotesTab from "@/components/projects/ProjectNotesTab";
import ProjectMetadataSection from "@/components/projects/ProjectMetadataSection";
import ProjectEquipmentSection from "@/components/projects/ProjectEquipmentSection";
import ProjectStatusChip from "@/components/projects/ProjectStatusChip";
import PlateSolveLine from "@/components/projects/PlateSolveLine";
import IntegrationBars, { formatHoursMinutes } from "@/components/projects/IntegrationBars";
import AddTargetDialog from "@/components/projects/AddTargetDialog";
import MarkdownEditor from "@/components/common/MarkdownEditor";
import { getProjectSolve } from "@/api/projectSolve";
import { getIntegration } from "@/api/projectSessions";
import {
  addProjectTarget,
  listProjectTargets,
  removeProjectTarget,
} from "@/api/projectTargets";
import NotListedTag from "@/components/dso/NotListedTag";
import { formatImagingRuns } from "@/lib/galleryRendition";

const escapeHtml = (s: string) =>
  s.replace(/[&<>"]/g, (c) => `&${{ "&": "amp", "<": "lt", ">": "gt", '"': "quot" }[c]};`);

/**
 * Open one project image in its own OS window at ~2/3 of the screen.
 *
 * A real window rather than a modal, so it can be resized, moved to a second
 * display, and left open next to the app. The popup gets a tiny document rather
 * than the bare image URL so the image *fits* the window and keeps fitting as
 * it is resized — pointing a window at an image URL shows it at native size
 * with scrollbars instead.
 */
function openImageWindow(url: string, title: string) {
  const width = Math.round(window.screen.availWidth * (2 / 3));
  const height = Math.round(window.screen.availHeight * (2 / 3));
  // Centre on the window we were launched from, NOT on `screen.availLeft` —
  // that reports the offset of one particular display, so on a multi-monitor
  // desk it throws the popup onto a different screen than the app is on
  // (measured: left = -2133 with a second display to the left of the primary).
  const left = Math.round(window.screenX + (window.outerWidth - width) / 2);
  const top = Math.round(window.screenY + (window.outerHeight - height) / 2);

  const win = window.open(
    "",
    `nightcrate-image-${title}`,
    `popup=yes,width=${width},height=${height},left=${left},top=${top},resizable=yes,scrollbars=no`,
  );
  if (!win) {
    // Popup blocked — fall back to a tab so the click still does something.
    window.open(url, "_blank", "noopener");
    return;
  }
  win.document.write(
    `<!doctype html><html><head><meta charset="utf-8">` +
      `<title>${escapeHtml(title)}</title>` +
      `<style>html,body{margin:0;height:100%;background:#000000;}` +
      `body{display:flex;align-items:center;justify-content:center;}` +
      `img{max-width:100vw;max-height:100vh;object-fit:contain;}</style></head>` +
      `<body><img src="${escapeHtml(url)}" alt="${escapeHtml(title)}"></body></html>`,
  );
  win.document.close();
  win.focus();
}

interface ProjectDescriptionProps {
  value: string;
  onSave: (next: string) => void;
}

function ProjectDescription({ value, onSave }: ProjectDescriptionProps) {
  const [expanded, setExpanded] = useState(false);
  const [hasOverflow, setHasOverflow] = useState(false);
  const rootRef = useRef<HTMLDivElement | null>(null);

  useLayoutEffect(() => {
    if (expanded) return;
    const root = rootRef.current;
    if (!root) return;
    const measure = () => {
      const editorRoot = root.firstElementChild;
      const content = editorRoot?.children.item(1) as HTMLElement | null;
      setHasOverflow(content != null && content.scrollHeight > content.clientHeight + 1);
    };
    measure();
    const observer = new ResizeObserver(measure);
    observer.observe(root);
    return () => observer.disconnect();
  }, [expanded, value]);

  return (
    <Box>
      <Box
        ref={rootRef}
        onClickCapture={() => setExpanded(true)}
        sx={
          expanded
            ? undefined
            : {
                "& > div > div:nth-of-type(2)": {
                  display: "-webkit-box",
                  WebkitBoxOrient: "vertical",
                  WebkitLineClamp: 6,
                  overflow: "hidden",
                },
              }
        }
      >
        <MarkdownEditor
          value={value}
          onSave={onSave}
          label={
            <Typography sx={{ color: "text.secondary", fontSize: "13px", lineHeight: 1.45 }}>
              Description
            </Typography>
          }
          placeholder="Add a description"
          minHeight={0}
        />
      </Box>
      {hasOverflow && (
        <Button
          size="small"
          onClick={() => setExpanded((current) => !current)}
          sx={{ minWidth: 0, px: 0, mt: "2px", fontSize: "13px" }}
        >
          {expanded ? "Show less" : "Show more"}
        </Button>
      )}
    </Box>
  );
}

export default function ProjectDetailPage() {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const [searchParams, setSearchParams] = useSearchParams();
  const queryClient = useQueryClient();
  const projectId = Number(id);
  const [tab, setTab] = useState(searchParams.get("tab") === "plate-solve" ? 3 : 0);
  const [focusNight, setFocusNight] = useState<string | undefined>();
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
  const { data: projectRigSetups = [] } = useQuery({
    queryKey: ["project-rig-setups", projectId],
    queryFn: () => fetchProjectRigSetups(projectId),
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
    queryClient.invalidateQueries({ queryKey: ["project-solve", projectId] });
  }, [queryClient, projectId]);

  const openPlateSolve = useCallback(() => {
    setTab(3);
    const next = new URLSearchParams(searchParams);
    next.set("tab", "plate-solve");
    setSearchParams(next, { replace: true });
  }, [searchParams, setSearchParams]);

  // Apply a server response directly to the cache (no extra round-trip),
  // and refresh the list view that shows thumbnails/counts.
  const applyProject = useCallback(
    (p: Project) => {
      queryClient.setQueryData(["project", projectId], p);
      queryClient.invalidateQueries({ queryKey: ["projects"] });
      queryClient.invalidateQueries({ queryKey: ["project-solve", projectId] });
    },
    [queryClient, projectId],
  );

  const refreshRigDependent = useCallback(() => {
    queryClient.invalidateQueries({ queryKey: ["rigs"] });
    queryClient.invalidateQueries({ queryKey: ["rig-setups"] });
    queryClient.invalidateQueries({ queryKey: ["project-rig-setups", projectId] });
    queryClient.invalidateQueries({ queryKey: ["project", projectId] });
    queryClient.invalidateQueries({ queryKey: ["project-catalog", projectId] });
    queryClient.invalidateQueries({ queryKey: ["project-sessions", projectId] });
    queryClient.invalidateQueries({ queryKey: ["project-integration", projectId] });
    queryClient.invalidateQueries({ queryKey: ["project-solve", projectId] });
    queryClient.invalidateQueries({ queryKey: ["equipment-usage"] });
  }, [queryClient, projectId]);

  const images = useMemo(() => project?.images ?? [], [project?.images]);

  const effectiveMainId = useMemo(() => {
    const existing = images.find((i) => i.is_main);
    return existing?.id ?? images[0]?.id ?? null;
  }, [images]);

  const [viewedImageId, setViewedImageId] = useState<number | null>(null);
  const [mainImgLoaded, setMainImgLoaded] = useState(false);
  const [mainImgFailed, setMainImgFailed] = useState(false);
  const viewedImage = useMemo(() => {
    if (!images.length) return null;
    if (viewedImageId) {
      const found = images.find((i) => i.id === viewedImageId);
      if (found) return found;
    }
    return images.find((i) => i.id === effectiveMainId) ?? images[0] ?? null;
  }, [images, viewedImageId, effectiveMainId]);

  const viewedImageIdentity = viewedImage
    ? `${project?.workspace_key ?? ""}:${viewedImage.id}`
    : null;
  const prevViewedRef = useRef<string | null>(null);
  if (viewedImageIdentity !== prevViewedRef.current) {
    prevViewedRef.current = viewedImageIdentity;
    if (mainImgLoaded) setMainImgLoaded(false);
    if (mainImgFailed) setMainImgFailed(false);
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
    mutationFn: (crops: Partial<Record<CropSize, ThumbnailCropDef>>) =>
      saveThumbnailCrops(projectId, crops),
    onSuccess: (p) => {
      applyProject(p);
      setSnack("Thumbnails updated");
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

  const displayDesc = project.description ?? "";
  const displayNotes = project.notes ?? "";

  const imagingRunLabels = integration
    ? formatImagingRuns({
        imaging_runs: integration.imaging_runs,
        first_date: integration.first_session_date,
        last_date: integration.last_session_date,
      } as Parameters<typeof formatImagingRuns>[0])
    : [];

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

        <ProjectStatusChip
          project={project}
          onUpdated={applyProject}
          onError={setSnack}
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
      <Tabs value={tab} onChange={(_, v) => {
        setTab(v);
        if (v !== 1) setFocusNight(undefined);
        const next = new URLSearchParams(searchParams);
        if (v === 3) next.set("tab", "plate-solve");
        else {
          next.delete("tab");
          next.delete("solve");
          next.delete("hdu");
        }
        setSearchParams(next, { replace: true });
      }} sx={{ mb: 2 }}>
        <Tab label="Overview" />
        <Tab label="Sessions" />
        <Tab label="Files" />
        <Tab label="Plate Solve" />
        <Tab label="Notes" />
      </Tabs>

      {tab === 1 && <ProjectSessionsTab projectId={projectId} focusNight={focusNight} />}
      {tab === 2 && <ProjectCatalogTab projectId={projectId} />}
      {tab === 3 && (
        <ProjectPlateSolveTab projectId={projectId} onMainsChange={invalidate} />
      )}
      {tab === 4 && (
        <ProjectNotesTab
          projectId={projectId}
          notes={displayNotes}
          onSave={(next) => {
            if (next !== (project.notes ?? "")) metaMut.mutate({ notes: next });
          }}
          onOpenNight={(night) => {
            setFocusNight(night);
            setTab(1);
            const next = new URLSearchParams(searchParams);
            next.delete("tab");
            next.delete("solve");
            next.delete("hdu");
            setSearchParams(next, { replace: true });
          }}
        />
      )}

      {/* Overview tab */}
      {tab === 0 && (
        <Box sx={{ maxWidth: 1280 }}>
          <Box
            sx={{
              display: "grid",
              gridTemplateColumns: "560px minmax(0, 1fr)",
              gap: "28px",
              alignItems: "start",
              "@media (max-width: 1099.95px)": { gridTemplateColumns: "minmax(0, 1fr)" },
            }}
          >
            <Box sx={{ minWidth: 0 }}>
              <Box
                sx={{
                  width: "100%",
                  aspectRatio: "4 / 3",
                  position: "relative",
                  borderRadius: "6px",
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
                    {((!mainImgLoaded && !mainImgFailed) || addMut.isPending) && (
                      <CircularProgress size={32} />
                    )}
                    <Box
                      component="img"
                      key={renderedImageUrl(
                        projectId,
                        viewedImage.id,
                        "thumb_lg",
                        project.workspace_key,
                      )}
                      src={renderedImageUrl(
                        projectId,
                        viewedImage.id,
                        "thumb_lg",
                        project.workspace_key,
                      )}
                      alt={project.name}
                      onLoad={() => {
                        setMainImgFailed(false);
                        setMainImgLoaded(true);
                      }}
                      onError={() => {
                        setMainImgLoaded(false);
                        setMainImgFailed(true);
                      }}
                      sx={{
                        maxWidth: "100%",
                        maxHeight: "100%",
                        objectFit: "contain",
                        display: mainImgLoaded && !addMut.isPending ? "block" : "none",
                      }}
                    />
                    {mainImgFailed && !addMut.isPending && (
                      <Typography sx={{ color: "#8e8c88", fontSize: "13px" }}>
                        No preview
                      </Typography>
                    )}
                    {mainImgLoaded && !addMut.isPending && (
                      <Tooltip title="Open in a larger window">
                        <IconButton
                          size="small"
                          aria-label="Open image in a larger window"
                          onClick={() =>
                            openImageWindow(
                              renderedImageUrl(
                                projectId,
                                viewedImage.id,
                                "full",
                                project.workspace_key,
                              ),
                              project.name,
                            )
                          }
                          sx={{
                            position: "absolute",
                            top: 8,
                            right: 8,
                            color: "common.white",
                            bgcolor: "rgba(0,0,0,0.45)",
                            "&:hover": { bgcolor: "rgba(0,0,0,0.75)" },
                          }}
                        >
                          <OpenInFullIcon fontSize="small" />
                        </IconButton>
                      </Tooltip>
                    )}
                  </>
                ) : addMut.isPending ? (
                  <CircularProgress size={32} />
                ) : (
                  <Typography color="text.secondary" sx={{ px: 2, textAlign: "center" }}>
                    No images yet. Use the gallery strip below to add images.
                  </Typography>
                )}
              </Box>

              <ImageGalleryStrip
                projectId={projectId}
                workspaceKey={project.workspace_key}
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
            </Box>

            <Box sx={{ display: "flex", minWidth: 0, flexDirection: "column", gap: "18px" }}>
              <Box>
                <Box sx={{ display: "flex", alignItems: "center", gap: "6px", mb: "6px" }}>
                  <Typography sx={{ color: "text.secondary", fontSize: "13px", lineHeight: 1.45 }}>
                    Main targets
                  </Typography>
                  <Tooltip
                    describeChild
                    title="Add a target from the catalog here, or plate solve an image on the Plate Solve tab and choose targets from the objects it finds."
                  >
                    <IconButton
                      size="small"
                      onClick={() => setAddTargetOpen(true)}
                      aria-label="Add target"
                      sx={{ width: "22px", height: "22px" }}
                    >
                      <AddIcon sx={{ fontSize: "16px" }} />
                    </IconButton>
                  </Tooltip>
                </Box>
                {mainTargets.length > 0 ? (
                  <Box sx={{ display: "flex", flexWrap: "wrap", gap: "6px" }}>
                    {mainTargets.map((target) => (
                      <Chip
                        key={target.dso_id}
                        label={
                          <Box component="span" sx={{ display: "inline-flex", alignItems: "center" }}>
                            {target.common_name ?? target.primary_designation}
                            {!target.active && <NotListedTag />}
                          </Box>
                        }
                        size="small"
                        onClick={solveDsoIds.has(target.dso_id) ? openPlateSolve : undefined}
                        onDelete={() => removeTargetMut.mutate(target.dso_id)}
                        sx={(theme) => ({
                          height: "26px",
                          bgcolor: theme.palette.mode === "dark" ? "#31343a" : "#ebe8e3",
                          fontSize: "13px",
                        })}
                      />
                    ))}
                  </Box>
                ) : (
                  <Typography sx={{ color: "text.secondary", fontSize: "13px" }}>
                    No targets yet.
                  </Typography>
                )}
                <PlateSolveLine
                  solvedAt={solve?.solved_at ?? project.solved_at}
                  objectCount={solve?.objects.length}
                  onOpen={openPlateSolve}
                />
              </Box>

              <ProjectMetadataSection
                project={project}
                imagingRuns={imagingRunLabels}
                nightCount={integration?.night_count ?? 0}
                onUpdated={applyProject}
                onChanged={refreshRigDependent}
              />

              <Box
                sx={(theme) => ({
                  borderTop: `1px solid ${theme.palette.mode === "dark" ? "#34373d" : "#dcd9d4"}`,
                  pt: "14px",
                })}
              >
                <ProjectDescription
                  value={displayDesc}
                  onSave={(next) => {
                    const value = next.trim();
                    if (value !== (project.description ?? "")) {
                      metaMut.mutate({ description: value });
                    }
                  }}
                />
              </Box>

              {integration && integration.total_actual_minutes > 0 && (
                <Box
                  sx={(theme) => ({
                    borderTop: `1px solid ${theme.palette.mode === "dark" ? "#34373d" : "#dcd9d4"}`,
                    pt: "14px",
                  })}
                >
                  <Typography sx={{ mb: "8px", color: "text.secondary", fontSize: "13px" }}>
                    Integration{" "}
                    <Box component="span" sx={{ color: "text.primary", fontWeight: 500 }}>
                      {formatHoursMinutes(integration.total_actual_minutes)} in all
                    </Box>
                  </Typography>
                  <IntegrationBars summary={integration} compact showHeading={false} />
                </Box>
              )}
            </Box>
          </Box>

          <ProjectEquipmentSection
            project={project}
            rigSetups={projectRigSetups}
            onUpdated={applyProject}
            onChanged={refreshRigDependent}
            onError={setSnack}
          />
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
        workspaceKey={project.workspace_key}
        images={images}
        mainImageId={effectiveMainId}
        existingCrops={project.thumbnail_crops}
        onApply={(crops) => cropMut.mutateAsync(crops)}
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
