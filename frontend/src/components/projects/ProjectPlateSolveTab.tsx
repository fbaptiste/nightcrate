import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useSearchParams } from "react-router-dom";
import Box from "@mui/material/Box";
import Button from "@mui/material/Button";
import Dialog from "@mui/material/Dialog";
import DialogActions from "@mui/material/DialogActions";
import DialogContent from "@mui/material/DialogContent";
import DialogTitle from "@mui/material/DialogTitle";
import Snackbar from "@mui/material/Snackbar";
import Typography from "@mui/material/Typography";
import { alpha, useTheme } from "@mui/material/styles";

import { fetchHeader } from "@/api/images";
import {
  parseApiError,
  type PlateSolveRequest,
  type PlateSolveResult,
} from "@/api/plateSolve";
import {
  createProjectSolve,
  deleteProjectSolve,
  getProjectSolve,
  setProjectObjectMain,
  type IdentifiedDso,
  type ProjectSolve,
} from "@/api/projectSolve";
import { headerNumber } from "@/components/analyzer/analyzerHelpers";
import { FileBrowser } from "@/components/fits/FileBrowser";
import ImagePreview from "@/components/plate-solve/ImagePreview";
import PlateSolvePanel, {
  type SolveOutcome,
} from "@/components/plate-solve/PlateSolvePanel";
import { solveColors } from "@/components/plate-solve/solvePalette";
import { stepLabel } from "@/components/plate-solve/solveStepLabels";
import { invalidateProjectLinks } from "@/api/projectTargetLinks";
import { invalidateProjectInfo } from "@/api/projectInfo";
import SolvedPlateSolveWorkspace from "@/components/projects/plate-solve/SolvedPlateSolveWorkspace";

function fileName(path: string): string {
  return path.split(/[\\/]/).pop()?.split("::").pop() ?? path;
}

function formatDay(value: string): string {
  return new Intl.DateTimeFormat("en-GB", {
    day: "numeric",
    month: "short",
    year: "numeric",
    timeZone: "UTC",
  }).format(new Date(`${value.slice(0, 10)}T00:00:00Z`));
}

function toResult(solve: ProjectSolve): PlateSolveResult {
  return {
    solved: true,
    solver: solve.solver,
    star_catalog: solve.star_catalog,
    stars_detected: solve.stars_detected,
    stars_matched: solve.stars_matched,
    rms_px: solve.rms_px,
    rms_arcsec: solve.rms_arcsec,
    log_odds: solve.log_odds,
    solve_path: solve.solve_path,
    scale_stage: solve.scale_stage,
    failure_reason: null,
    ra_deg: solve.center_ra_deg,
    dec_deg: solve.center_dec_deg,
    ra_hms: solve.ra_hms,
    dec_dms: solve.dec_dms,
    pixel_scale_arcsec: solve.pixel_scale_arcsec,
    rotation_deg: solve.rotation_deg,
    fov_width_arcmin: solve.fov_width_arcmin,
    fov_height_arcmin: solve.fov_height_arcmin,
    image_width: solve.image_width,
    image_height: solve.image_height,
    cd1_1: solve.wcs.cd1_1,
    cd1_2: solve.wcs.cd1_2,
    cd2_1: solve.wcs.cd2_1,
    cd2_2: solve.wcs.cd2_2,
    crpix1: solve.wcs.crpix1,
    crpix2: solve.wcs.crpix2,
    error_message: null,
    warning: null,
    solve_time_seconds: null,
    attempts: solve.attempts,
  };
}

function foundByText(solve: ProjectSolve): { label: string; seconds: number | null } | null {
  const attempt = solve.attempts.find((item) => item.outcome === "solved");
  if (attempt) return { label: stepLabel(attempt.step), seconds: attempt.seconds };
  if (solve.solve_path === "near_index") {
    return { label: "Search near the supplied position", seconds: null };
  }
  if (solve.solve_path === "near_catalog") {
    return { label: "Match catalog stars near the supplied position", seconds: null };
  }
  if (solve.solve_path === "blind") {
    return { label: "Search the whole sky", seconds: null };
  }
  if (solve.solver === "astap") return { label: "ASTAP", seconds: null };
  return null;
}

interface Props {
  projectId: number;
  onMainsChange?: () => void;
}

export default function ProjectPlateSolveTab({ projectId, onMainsChange }: Props) {
  const theme = useTheme();
  const queryClient = useQueryClient();
  const [params, setParams] = useSearchParams();
  const [browserOpen, setBrowserOpen] = useState(false);
  const [detailsOpen, setDetailsOpen] = useState(false);
  const [confirmDelete, setConfirmDelete] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [pendingIds, setPendingIds] = useState<Set<number>>(() => new Set());
  const chosenPath = params.get("solve");

  const solveQuery = useQuery({
    queryKey: ["project-solve", projectId],
    queryFn: () => getProjectSolve(projectId),
  });
  const solve = solveQuery.data ?? null;
  const headerQuery = useQuery({
    queryKey: ["header", chosenPath, 0],
    queryFn: () => fetchHeader(chosenPath!, 0),
    enabled: !!chosenPath,
    staleTime: Infinity,
  });
  const cards = headerQuery.data ?? [];
  const width = headerNumber(cards, "NAXIS1");
  const height = headerNumber(cards, "NAXIS2");

  const setChosen = (path: string | null) => {
    const next = new URLSearchParams(params);
    next.set("tab", "plate-solve");
    if (path) {
      next.set("solve", path);
      next.set("hdu", "0");
    } else {
      next.delete("solve");
      next.delete("hdu");
    }
    setParams(next, { replace: true });
  };

  const refreshSaved = () => {
    void queryClient.invalidateQueries({ queryKey: ["project-solve", projectId] });
    void queryClient.invalidateQueries({ queryKey: ["project-targets", projectId] });
    void invalidateProjectInfo(queryClient, projectId);
    void invalidateProjectLinks(queryClient);
    onMainsChange?.();
  };

  const solveAdapter = async (request: PlateSolveRequest): Promise<SolveOutcome> => {
    try {
      const created = await createProjectSolve(projectId, {
        image_path: request.image_path,
        hdu: 0,
        operation_id: request.operation_id,
        replace: solve != null,
        ra_hint: request.ra_hint,
        dec_hint: request.dec_hint,
        scale_hint_arcsec: request.scale_hint_arcsec,
        position: request.position,
        scale: request.scale,
        solver: request.solver,
      });
      return { kind: "solved", result: toResult(created) };
    } catch (reason: unknown) {
      return { kind: "failed", ...parseApiError(reason) };
    }
  };

  const mainMutation = useMutation({
    mutationFn: ({ dsoId, isMain }: { dsoId: number; isMain: boolean }) =>
      setProjectObjectMain(projectId, dsoId, isMain),
    onMutate: ({ dsoId, isMain }) => {
      setError(null);
      setPendingIds((current) => new Set(current).add(dsoId));
      queryClient.setQueryData<ProjectSolve | null>(["project-solve", projectId], (current) =>
        current
          ? {
              ...current,
              objects: current.objects.map((object) =>
                object.dso_id === dsoId ? { ...object, is_main: isMain } : object,
              ),
            }
          : current,
      );
    },
    onSuccess: (updated) => {
      queryClient.setQueryData(["project-solve", projectId], updated);
      refreshSaved();
    },
    onSettled: (_data, _reason, variables) => {
      setPendingIds((current) => {
        const next = new Set(current);
        next.delete(variables.dsoId);
        return next;
      });
    },
    onError: (reason, variables) => {
      queryClient.setQueryData<ProjectSolve | null>(["project-solve", projectId], (current) =>
        current
          ? {
              ...current,
              objects: current.objects.map((object) =>
                object.dso_id === variables.dsoId
                  ? { ...object, is_main: !variables.isMain }
                  : object,
              ),
            }
          : current,
      );
      setError(parseApiError(reason).message);
    },
  });
  const deleteMutation = useMutation({
    mutationFn: () => deleteProjectSolve(projectId),
    onSuccess: () => {
      setConfirmDelete(false);
      refreshSaved();
    },
    onError: (reason) => setError(parseApiError(reason).message),
  });

  const handleFileSelect = (path: string) => {
    setBrowserOpen(false);
    setError(null);
    setChosen(path);
  };

  const handleSolved = () => {
    void Promise.all([
      queryClient.refetchQueries({ queryKey: ["project-solve", projectId] }),
      queryClient.refetchQueries({ queryKey: ["project-targets", projectId] }),
    ]).finally(() => setChosen(null));
    void invalidateProjectInfo(queryClient, projectId);
    void invalidateProjectLinks(queryClient);
    onMainsChange?.();
  };

  const fileBrowser = (
    <FileBrowser
      open={browserOpen}
      onClose={() => setBrowserOpen(false)}
      onSelect={handleFileSelect}
      title="Choose an image to plate solve"
      emptyMessage="No image files in this directory"
    />
  );

  if (solveQuery.isLoading) {
    return <Typography color="text.secondary">Loading…</Typography>;
  }

  if (!solve && !chosenPath) {
    return (
      <Box
        sx={{
          height: "100%",
          overflow: "auto",
          maxWidth: 520,
          display: "grid",
          justifyItems: "start",
          gap: 1.25,
          py: 3.5,
          px: 0.5,
        }}
      >
        <Typography component="h2" sx={{ fontSize: 17, fontWeight: 600 }}>
          Place an image on the sky and identify its objects
        </Typography>
        <Typography color="text.secondary">
          Plate solving identifies catalog objects in this image. Choose one or more main targets
          to organize the project's folders and frames in the Files tab. Later, search will find
          projects and frames by their main targets or by any object identified in them.
        </Typography>
        <Button
          variant="contained"
          onClick={() => setBrowserOpen(true)}
          sx={{ minHeight: 40 }}
        >
          Choose image
        </Button>
        {error && (
          <Typography color="error" sx={{ fontSize: 13 }}>
            {error}
          </Typography>
        )}
        {fileBrowser}
      </Box>
    );
  }

  if (chosenPath) {
    return (
      <Box sx={{ height: "100%", overflow: "auto", maxWidth: 1240, display: "grid", gap: 1.5 }}>
        <Box
          sx={{
            display: "flex",
            flexWrap: "wrap",
            gap: "8px 14px",
            alignItems: "baseline",
          }}
        >
          <Typography sx={{ fontWeight: 600 }}>{fileName(chosenPath)}</Typography>
          <Typography color="text.secondary" sx={{ fontSize: 13 }}>
            {width && height
              ? `${width} × ${height} px`
              : headerQuery.isLoading
                ? "Reading image…"
                : "Image size unavailable"}
          </Typography>
          <Box sx={{ flex: 1 }} />
          <Button
            color="inherit"
            onClick={() => setBrowserOpen(true)}
            sx={{ minHeight: 40, color: "text.secondary" }}
          >
            Choose another image
          </Button>
        </Box>
        <Box
          sx={{
            display: "grid",
            gridTemplateColumns: {
              xs: "minmax(0, 1fr)",
              md: "minmax(0, 1fr) 340px",
            },
            gap: 2,
            alignItems: "start",
          }}
        >
          <ImagePreview
            key={chosenPath}
            path={chosenPath}
            hdu={0}
            imgW={width ?? 0}
            imgH={height ?? 0}
          />
          {headerQuery.isError ? (
            <Box sx={{ border: 1, borderColor: "divider", borderRadius: "8px", p: 2 }}>
              <Typography color="error">Unable to read this image.</Typography>
              <Button
                onClick={() => void headerQuery.refetch()}
                sx={{ minHeight: 40 }}
              >
                Retry preview
              </Button>
            </Box>
          ) : (
            <PlateSolvePanel
              image={{ path: chosenPath, hdu: 0, cards }}
              scope={{ surface: "project", projectId }}
              solve={solveAdapter}
              primaryLabel={
                solve ? "Solve and replace saved solution" : "Solve and save to project"
              }
              replacing={solve != null}
              active
              onSolved={handleSolved}
              onStale={refreshSaved}
              onChooseImage={() => setBrowserOpen(true)}
              dismiss={
                solve
                  ? { label: "Keep the saved solution", onClick: () => setChosen(null) }
                  : undefined
              }
            />
          )}
        </Box>
        {fileBrowser}
      </Box>
    );
  }

  if (!solve) return null;

  const done =
    theme.palette.mode === "dark" ? solveColors.done.dark : solveColors.done.light;
  const center =
    solve.ra_hms && solve.dec_dms
      ? `${solve.ra_hms}  ${solve.dec_dms}`
      : `${solve.center_ra_deg.toFixed(4)}°  ${solve.center_dec_deg.toFixed(4)}°`;
  const foundBy = foundByText(solve);
  const fitError = [
    solve.rms_px != null ? `${solve.rms_px.toFixed(2)} px` : null,
    solve.rms_arcsec != null ? `(${solve.rms_arcsec.toFixed(2)}″)` : null,
  ]
    .filter(Boolean)
    .join(" ");
  const facts = [
    { label: "Centre", value: center },
    {
      label: "Pixel scale",
      value:
        solve.pixel_scale_arcsec != null ? `${solve.pixel_scale_arcsec.toFixed(2)}″/px` : "—",
    },
    {
      label: "Field",
      value:
        solve.fov_width_arcmin != null && solve.fov_height_arcmin != null
          ? `${(solve.fov_width_arcmin / 60).toFixed(2)}° × ${(solve.fov_height_arcmin / 60).toFixed(2)}°`
          : "—",
    },
    {
      label: "Rotation",
      value: solve.rotation_deg != null ? `${solve.rotation_deg.toFixed(1)}°` : "—",
    },
    { label: "Solver", value: solve.solver === "native" ? "Built-in" : "ASTAP" },
    ...(foundBy
      ? [
          {
            label: "Found by",
            value: `${foundBy.label}${foundBy.seconds != null ? `, ${foundBy.seconds.toFixed(1)} s` : ""}`,
          },
        ]
      : []),
    ...(solve.stars_matched != null
      ? [
          {
            label: "Stars matched",
            value:
              solve.stars_detected != null
                ? `${solve.stars_matched} of ${solve.stars_detected}`
                : solve.stars_matched.toLocaleString(),
          },
        ]
      : []),
    ...(fitError ? [{ label: "Fit error", value: fitError }] : []),
  ];

  return (
    <Box
      sx={{
        width: "100%",
        maxWidth: 1280,
        height: "100%",
        minHeight: 0,
        display: "flex",
        flexDirection: "column",
        gap: 1.5,
        overflow: "auto",
      }}
    >
      <Box
        sx={{
          display: "flex",
          flexWrap: "wrap",
          gap: 1,
          alignItems: "center",
        }}
      >
        <Typography sx={{ fontWeight: 600 }}>{fileName(solve.image_path)}</Typography>
        <Typography color="text.secondary" sx={{ mr: 0.75, fontSize: 13 }}>
          {solve.image_width} × {solve.image_height} px
        </Typography>
        <Box
          sx={{
            minHeight: 32,
            px: 1.25,
            borderRadius: "999px",
            bgcolor: alpha(done, 0.12),
            border: `1px solid ${alpha(done, 0.4)}`,
            display: "flex",
            gap: 0.75,
            alignItems: "center",
          }}
        >
          <Box
            sx={{
              width: 18,
              height: 18,
              borderRadius: "50%",
              bgcolor: done,
              color: "#0d1f1d",
              display: "grid",
              placeItems: "center",
              fontSize: 11,
              fontWeight: 700,
            }}
          >
            ✓
          </Box>
          <Typography sx={{ fontWeight: 600, fontSize: 13 }}>
            Solved and saved, {formatDay(solve.solved_at)}
          </Typography>
        </Box>
        <Box sx={{ flex: 1 }} />
        <Button
          variant="outlined"
          onClick={() => setChosen(solve.image_path)}
          sx={{ minHeight: 40 }}
        >
          Solve again
        </Button>
        <Button variant="outlined" onClick={() => setBrowserOpen(true)} sx={{ minHeight: 40 }}>
          Choose another image
        </Button>
        <Button
          color="inherit"
          onClick={() => setConfirmDelete(true)}
          sx={{ minHeight: 40, color: "text.secondary" }}
        >
          Remove solution
        </Button>
      </Box>

      <Box
        sx={{
          bgcolor: "background.paper",
          border: 1,
          borderColor: "divider",
          borderRadius: "8px",
          p: 1.25,
          display: "flex",
          flexWrap: "wrap",
          alignItems: "center",
          gap: "10px 22px",
        }}
      >
        {facts.map((fact) => (
          <Box key={fact.label} sx={{ minWidth: 0, fontVariantNumeric: "tabular-nums" }}>
            <Typography
              component="div"
              color="text.secondary"
              sx={{ fontSize: 11.5, lineHeight: 1.2 }}
            >
              {fact.label}
            </Typography>
            <Typography component="div" sx={{ fontSize: 13, lineHeight: 1.45 }}>
              {fact.value}
            </Typography>
          </Box>
        ))}
        <Button
          variant="text"
          onClick={() => setDetailsOpen((value) => !value)}
          sx={{ ml: "auto", minHeight: 32, whiteSpace: "nowrap" }}
        >
          {detailsOpen ? "Hide solution details" : "View solution details"}
        </Button>
      </Box>

      {detailsOpen && (
        <Box
          sx={{
            mt: -1,
            borderRadius: "6px",
            p: "10px 12px",
            bgcolor: alpha(theme.palette.secondary.main, 0.12),
            border: `1px solid ${alpha(theme.palette.secondary.main, 0.35)}`,
          }}
        >
          <Box
            component="dl"
            sx={{
              m: 0,
              display: "grid",
              gridTemplateColumns: "auto minmax(0, 1fr)",
              gap: "4px 12px",
              fontSize: 13,
              "& dt": { color: "text.secondary" },
              "& dd": { m: 0 },
            }}
          >
            {solve.star_catalog && (
              <>
                <dt>Star catalog</dt>
                <dd>{solve.star_catalog}</dd>
              </>
            )}
            {solve.scale_stage && (
              <>
                <dt>Scale stage</dt>
                <dd>{solve.scale_stage}</dd>
              </>
            )}
            {solve.attempts.map((attempt, index) => (
              <Box component="div" key={`${attempt.step}:${index}`} sx={{ display: "contents" }}>
                <dt>{index === 0 ? "Attempts" : ""}</dt>
                <dd>
                  {stepLabel(attempt.step)} — {attempt.outcome}
                  {attempt.seconds != null ? `, ${attempt.seconds.toFixed(1)} s` : ""}
                </dd>
              </Box>
            ))}
          </Box>
        </Box>
      )}

      <SolvedPlateSolveWorkspace
        projectId={projectId}
        solve={solve}
        pendingIds={pendingIds}
        onToggleMain={async (object: IdentifiedDso, isMain: boolean) => {
          try {
            await mainMutation.mutateAsync({ dsoId: object.dso_id, isMain });
            return true;
          } catch {
            return false;
          }
        }}
      />

      <Snackbar
        open={error != null}
        autoHideDuration={5000}
        onClose={() => setError(null)}
        message={error}
      />
      {fileBrowser}
      <Dialog open={confirmDelete} onClose={() => setConfirmDelete(false)}>
        <DialogTitle>Remove saved solution?</DialogTitle>
        <DialogContent>
          <Typography>
            The saved plate solution and its object annotations will be removed. Main targets stay
            in the project.
          </Typography>
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setConfirmDelete(false)}>Cancel</Button>
          <Button color="error" onClick={() => deleteMutation.mutate()}>
            Remove saved solution
          </Button>
        </DialogActions>
      </Dialog>
    </Box>
  );
}
