import { useMemo, useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import Box from "@mui/material/Box";
import Button from "@mui/material/Button";
import Chip from "@mui/material/Chip";
import CircularProgress from "@mui/material/CircularProgress";
import IconButton from "@mui/material/IconButton";
import Tooltip from "@mui/material/Tooltip";
import Typography from "@mui/material/Typography";
import Dialog from "@mui/material/Dialog";
import DialogActions from "@mui/material/DialogActions";
import DialogContent from "@mui/material/DialogContent";
import DialogTitle from "@mui/material/DialogTitle";
import DeleteIcon from "@mui/icons-material/Delete";
import StarIcon from "@mui/icons-material/Star";
import StarBorderIcon from "@mui/icons-material/StarBorder";
import TravelExploreIcon from "@mui/icons-material/TravelExplore";
import { FileBrowser } from "@/components/fits/FileBrowser";
import DsoAnnotationOverlay from "@/components/plate-solve/DsoAnnotationOverlay";
import {
  getProjectSolve,
  createProjectSolve,
  setProjectObjectMain,
  deleteProjectSolve,
  projectSolveImageUrl,
  type ProjectSolve,
} from "@/api/projectSolve";

function fileName(path: string): string {
  return path.split("/").pop()?.split("::").pop() ?? path;
}

function SummaryRow({ label, value }: { label: string; value: string }) {
  return (
    <Box sx={{ display: "flex", justifyContent: "space-between", gap: 2, py: 0.25 }}>
      <Typography variant="caption" color="text.secondary">
        {label}
      </Typography>
      <Typography variant="caption" sx={{ fontVariantNumeric: "tabular-nums" }}>
        {value}
      </Typography>
    </Box>
  );
}

interface Props {
  projectId: number;
  onMainsChange?: () => void;
}

export default function ProjectPlateSolveTab({ projectId, onMainsChange }: Props) {
  const queryClient = useQueryClient();
  const [browserOpen, setBrowserOpen] = useState(false);
  const [selectedId, setSelectedId] = useState<number | null>(null);
  const [confirmDelete, setConfirmDelete] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const { data: solve, isLoading } = useQuery({
    queryKey: ["project-solve", projectId],
    queryFn: () => getProjectSolve(projectId),
  });

  const applySolve = (s: ProjectSolve | null) => {
    queryClient.setQueryData(["project-solve", projectId], s);
    // Solve mains live in project_target — keep the Overview's chips in sync.
    queryClient.invalidateQueries({ queryKey: ["project-targets", projectId] });
    onMainsChange?.();
  };

  const solveMut = useMutation({
    mutationFn: (imagePath: string) => createProjectSolve(projectId, { image_path: imagePath }),
    onSuccess: applySolve,
    onError: (err) => setError(String(err)),
  });

  const mainMut = useMutation({
    mutationFn: ({ dsoId, isMain }: { dsoId: number; isMain: boolean }) =>
      setProjectObjectMain(projectId, dsoId, isMain),
    onSuccess: applySolve,
    onError: (err) => setError(String(err)),
  });

  const deleteMut = useMutation({
    mutationFn: () => deleteProjectSolve(projectId),
    onSuccess: () => {
      applySolve(null);
      setSelectedId(null);
    },
    onError: (err) => setError(String(err)),
  });

  const overlayDsos = useMemo(
    () =>
      (solve?.objects ?? []).map((o) => ({
        id: o.dso_id,
        pixel_x: o.pixel_x,
        pixel_y: o.pixel_y,
        ellipse_semi_major_px: o.ellipse_semi_major_px,
        ellipse_semi_minor_px: o.ellipse_semi_minor_px,
        ellipse_angle_deg: o.ellipse_angle_deg,
        common_name: o.common_name,
        primary_designation: o.primary_designation,
      })),
    [solve],
  );
  const mainIds = useMemo(
    () => new Set((solve?.objects ?? []).filter((o) => o.is_main).map((o) => o.dso_id)),
    [solve],
  );

  if (isLoading) {
    return <Typography color="text.secondary">Loading…</Typography>;
  }

  // ── Empty state ──────────────────────────────────────────────────────────
  if (!solve) {
    return (
      <Box sx={{ textAlign: "center", py: 6, px: 2 }}>
        <TravelExploreIcon sx={{ fontSize: 48, color: "text.secondary", opacity: 0.4 }} />
        <Typography variant="body1" sx={{ mt: 1 }}>
          No plate solve yet
        </Typography>
        <Typography variant="body2" color="text.secondary" sx={{ mt: 0.5, mb: 2 }}>
          Plate-solve a linear FITS/XISF to identify the catalog objects in this project. The
          solve image is kept separate from the gallery.
        </Typography>
        <Button
          variant="contained"
          startIcon={solveMut.isPending ? <CircularProgress size={16} /> : <TravelExploreIcon />}
          disabled={solveMut.isPending}
          onClick={() => setBrowserOpen(true)}
        >
          {solveMut.isPending ? "Solving…" : "Plate solve an image"}
        </Button>
        {error && (
          <Typography variant="caption" color="error" sx={{ display: "block", mt: 2 }}>
            {error}
          </Typography>
        )}
        <FileBrowser
          open={browserOpen}
          onClose={() => setBrowserOpen(false)}
          onSelect={(path) => {
            setBrowserOpen(false);
            setError(null);
            solveMut.mutate(path);
          }}
          title="Choose an image to plate solve"
          emptyMessage="No image files in this directory"
        />
      </Box>
    );
  }

  // ── Solved state ─────────────────────────────────────────────────────────
  const centerText =
    solve.ra_hms && solve.dec_dms
      ? `${solve.ra_hms} / ${solve.dec_dms}`
      : `${solve.center_ra_deg.toFixed(4)}° / ${solve.center_dec_deg.toFixed(4)}°`;

  return (
    <Box>
      <Box sx={{ display: "flex", alignItems: "center", justifyContent: "space-between", mb: 1 }}>
        <Typography variant="subtitle2" color="text.secondary">
          {fileName(solve.image_path)} — {solve.objects.length} object
          {solve.objects.length !== 1 ? "s" : ""} identified
        </Typography>
        <Button
          size="small"
          color="error"
          startIcon={<DeleteIcon />}
          onClick={() => setConfirmDelete(true)}
        >
          Delete plate solve
        </Button>
      </Box>

      <Box sx={{ display: "flex", gap: 2, alignItems: "flex-start", flexWrap: "wrap" }}>
        {/* Overlay viewer */}
        <Box
          sx={{
            flex: "1 1 480px",
            minWidth: 0,
            maxHeight: "65vh",
            bgcolor: "common.black",
            borderRadius: 1,
            overflow: "hidden",
            display: "flex",
            alignItems: "center",
            justifyContent: "center",
          }}
        >
          <DsoAnnotationOverlay
            imageHref={projectSolveImageUrl(projectId, "full", solve.solved_at)}
            imgW={solve.image_width}
            imgH={solve.image_height}
            dsos={overlayDsos}
            selectedId={selectedId}
            onSelect={setSelectedId}
            mainIds={mainIds}
          />
        </Box>

        {/* Solution + objects */}
        <Box sx={{ flex: "0 0 320px", maxWidth: "100%" }}>
          <Typography variant="overline" color="text.secondary">
            Solution
          </Typography>
          <Box sx={{ mb: 1.5 }}>
            <SummaryRow label="Center" value={centerText} />
            {solve.pixel_scale_arcsec != null && (
              <SummaryRow label="Pixel scale" value={`${solve.pixel_scale_arcsec}″/px`} />
            )}
            {solve.rotation_deg != null && (
              <SummaryRow label="Rotation" value={`${solve.rotation_deg}°`} />
            )}
            {solve.fov_width_arcmin != null && solve.fov_height_arcmin != null && (
              <SummaryRow
                label="Field of view"
                value={`${solve.fov_width_arcmin}′ × ${solve.fov_height_arcmin}′`}
              />
            )}
            <SummaryRow label="Image" value={`${solve.image_width} × ${solve.image_height}`} />
          </Box>

          <Typography variant="overline" color="text.secondary">
            Objects (★ = main)
          </Typography>
          <Box sx={{ maxHeight: "40vh", overflow: "auto", mt: 0.5 }}>
            {solve.objects.map((o) => {
              const isSelected = o.dso_id === selectedId;
              return (
                <Box
                  key={o.dso_id}
                  onClick={() => setSelectedId(o.dso_id)}
                  sx={{
                    display: "flex",
                    alignItems: "center",
                    gap: 0.5,
                    px: 0.5,
                    py: 0.25,
                    borderRadius: 1,
                    cursor: "pointer",
                    bgcolor: isSelected ? "action.selected" : undefined,
                    "&:hover": { bgcolor: "action.hover" },
                  }}
                >
                  <Tooltip title={o.is_main ? "Unset as main" : "Set as main"}>
                    <IconButton
                      size="small"
                      onClick={(e) => {
                        e.stopPropagation();
                        mainMut.mutate({ dsoId: o.dso_id, isMain: !o.is_main });
                      }}
                      sx={{ color: o.is_main ? "warning.main" : "action.disabled", p: 0.25 }}
                    >
                      {o.is_main ? (
                        <StarIcon sx={{ fontSize: 18 }} />
                      ) : (
                        <StarBorderIcon sx={{ fontSize: 18 }} />
                      )}
                    </IconButton>
                  </Tooltip>
                  <Box sx={{ flexGrow: 1, minWidth: 0 }}>
                    <Typography variant="body2" noWrap>
                      {o.common_name ?? o.primary_designation}
                    </Typography>
                    {o.common_name && (
                      <Typography variant="caption" color="text.secondary" noWrap>
                        {o.primary_designation}
                      </Typography>
                    )}
                  </Box>
                  <Chip label={o.type_group} size="small" variant="outlined" />
                </Box>
              );
            })}
            {solve.objects.length === 0 && (
              <Typography variant="body2" color="text.secondary" sx={{ py: 1 }}>
                No catalog objects found in this field.
              </Typography>
            )}
          </Box>
        </Box>
      </Box>

      {error && (
        <Typography variant="caption" color="error" sx={{ display: "block", mt: 1 }}>
          {error}
        </Typography>
      )}

      <Dialog open={confirmDelete} onClose={() => setConfirmDelete(false)}>
        <DialogTitle>Delete plate solve?</DialogTitle>
        <DialogContent>
          <Typography>
            This removes the plate solve, its solved image, and
            {solve.objects.length > 0
              ? ` all ${solve.objects.length} identified object${solve.objects.length !== 1 ? "s" : ""}`
              : " any identified objects"}
            . This cannot be undone.
          </Typography>
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setConfirmDelete(false)}>Cancel</Button>
          <Button
            color="error"
            variant="contained"
            onClick={() => {
              setConfirmDelete(false);
              deleteMut.mutate();
            }}
          >
            Delete
          </Button>
        </DialogActions>
      </Dialog>
    </Box>
  );
}
