import { useCallback, useMemo, useRef, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useSearchParams } from "react-router-dom";
import Box from "@mui/material/Box";
import Button from "@mui/material/Button";
import Checkbox from "@mui/material/Checkbox";
import Dialog from "@mui/material/Dialog";
import DialogActions from "@mui/material/DialogActions";
import DialogContent from "@mui/material/DialogContent";
import DialogTitle from "@mui/material/DialogTitle";
import Table from "@mui/material/Table";
import TableBody from "@mui/material/TableBody";
import TableCell from "@mui/material/TableCell";
import TableContainer from "@mui/material/TableContainer";
import TableHead from "@mui/material/TableHead";
import TableRow from "@mui/material/TableRow";
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
  projectSolveImageUrl,
  setProjectObjectMain,
  type ProjectSolve,
} from "@/api/projectSolve";
import { headerNumber } from "@/components/analyzer/analyzerHelpers";
import { FileBrowser } from "@/components/fits/FileBrowser";
import DsoAnnotationOverlay from "@/components/plate-solve/DsoAnnotationOverlay";
import ImagePreview from "@/components/plate-solve/ImagePreview";
import PlateSolvePanel, {
  type SolveOutcome,
} from "@/components/plate-solve/PlateSolvePanel";
import { solveColors } from "@/components/plate-solve/solvePalette";
import { stepLabel } from "@/components/plate-solve/solveStepLabels";
import { DSO_TYPE_DISPLAY } from "@/lib/dsoTypeNames";
import { invalidateProjectLinks } from "@/api/projectTargetLinks";

function fileName(path: string): string {
  return path.split(/[\\/]/).pop()?.split("::").pop() ?? path;
}

function formatFocalLength(value: number): string {
  return Math.round(value).toLocaleString();
}

function formatPixelSize(value: number): string {
  return value.toLocaleString(undefined, { maximumFractionDigits: 2 });
}

function formatDay(value: string): string {
  return new Intl.DateTimeFormat("en-GB", {
    day: "numeric",
    month: "short",
    year: "numeric",
    timeZone: "UTC",
  }).format(new Date(`${value.slice(0, 10)}T00:00:00Z`));
}

function formatAxis(value: number): string {
  return value.toLocaleString(undefined, { maximumFractionDigits: 1 });
}

function objectSize(major: number | null, minor: number | null): string {
  if (major == null) return "";
  if (minor == null || Math.abs(major - minor) < 0.05) return `${formatAxis(major)}′`;
  return `${formatAxis(major)}′ × ${formatAxis(minor)}′`;
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
  const [selectedId, setSelectedId] = useState<number | null>(null);
  const [detailsOpen, setDetailsOpen] = useState(false);
  const [confirmDelete, setConfirmDelete] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [viewerWidth, setViewerWidth] = useState(0);
  const viewerObserverRef = useRef<ResizeObserver | null>(null);
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

  const setViewerElement = useCallback((viewer: HTMLDivElement | null) => {
    viewerObserverRef.current?.disconnect();
    viewerObserverRef.current = null;
    if (!viewer) return;
    const updateWidth = () => setViewerWidth(viewer.getBoundingClientRect().width);
    updateWidth();
    const observer = new ResizeObserver(updateWidth);
    observer.observe(viewer);
    viewerObserverRef.current = observer;
  }, []);

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
    onSuccess: refreshSaved,
    onError: (reason) => setError(parseApiError(reason).message),
  });
  const deleteMutation = useMutation({
    mutationFn: () => deleteProjectSolve(projectId),
    onSuccess: () => {
      setConfirmDelete(false);
      setSelectedId(null);
      refreshSaved();
    },
    onError: (reason) => setError(parseApiError(reason).message),
  });

  const overlayDsos = useMemo(
    () =>
      (solve?.objects ?? []).map((object) => ({
        id: object.dso_id,
        pixel_x: object.pixel_x,
        pixel_y: object.pixel_y,
        ellipse_semi_major_px: object.ellipse_semi_major_px,
        ellipse_semi_minor_px: object.ellipse_semi_minor_px,
        ellipse_angle_deg: object.ellipse_angle_deg,
        common_name: object.common_name,
        primary_designation: object.primary_designation,
      })),
    [solve],
  );
  const mainIds = useMemo(
    () =>
      new Set(
        (solve?.objects ?? []).filter((object) => object.is_main).map((object) => object.dso_id),
      ),
    [solve],
  );

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
      <Box sx={{ maxWidth: 1240, display: "grid", gap: 1.5 }}>
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
  const imageRatio = solve.image_width / solve.image_height;
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
    <Box sx={{ maxWidth: 1240, display: "grid", gap: 2 }}>
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

      <Box sx={{ display: "flex", justifyContent: "center", width: "100%" }}>
        <Box
          ref={setViewerElement}
          sx={{
            width: `min(100%, ${imageRatio * 560}px, ${imageRatio * 60}vh)`,
            maxHeight: "min(560px, 60vh)",
            bgcolor: "#05070b",
            borderRadius: "6px",
            overflow: "hidden",
            aspectRatio: `${solve.image_width} / ${solve.image_height}`,
          }}
        >
          <DsoAnnotationOverlay
            imageHref={projectSolveImageUrl(projectId, "full", solve.id)}
            imgW={solve.image_width}
            imgH={solve.image_height}
            dsos={overlayDsos}
            selectedId={selectedId}
            onSelect={setSelectedId}
            mainIds={mainIds}
            displayWidthPx={viewerWidth || undefined}
          />
        </Box>
      </Box>

      <Box
        sx={{
          display: "grid",
          gridTemplateColumns: {
            xs: "minmax(0, 1fr)",
            md:
              solve.focal_length_estimates.length > 0
                ? "minmax(0, 1.1fr) minmax(0, 1.2fr)"
                : "1fr",
          },
          gap: 2,
          alignItems: "start",
        }}
      >
        <Box
          sx={{
            bgcolor: "background.paper",
            border: 1,
            borderColor: "divider",
            borderRadius: "8px",
            overflow: "hidden",
          }}
        >
          <Box sx={{ p: "14px 16px 8px" }}>
            <Typography component="h2" sx={{ fontSize: 15, fontWeight: 600 }}>
              Objects in the image ({solve.objects.length})
            </Typography>
          </Box>
          <TableContainer>
            <Table
              size="small"
              aria-label="Objects in the solved image"
              sx={{ "& th": { whiteSpace: "nowrap" } }}
            >
              <TableHead>
                <TableRow>
                  <TableCell>Object</TableCell>
                  <TableCell>Type</TableCell>
                  <TableCell align="right">Size</TableCell>
                  <TableCell align="center">Main target</TableCell>
                </TableRow>
              </TableHead>
              <TableBody>
                {solve.objects.map((object) => {
                  const title = object.common_name ?? object.primary_designation;
                  const seen = new Set([title.toLocaleLowerCase()]);
                  const otherDesignations = [object.primary_designation, ...object.other_names].filter(
                    (name) => {
                      const key = name.toLocaleLowerCase();
                      if (seen.has(key)) return false;
                      seen.add(key);
                      return true;
                    },
                  );
                  const typeName = DSO_TYPE_DISPLAY[object.obj_type] ?? object.obj_type;
                  const selectObject = () => setSelectedId(object.dso_id);
                  return (
                    <TableRow
                      hover
                      key={object.dso_id}
                      tabIndex={0}
                      selected={selectedId === object.dso_id}
                      onClick={selectObject}
                      onKeyDown={(event) => {
                        if (event.key === "Enter" || event.key === " ") {
                          event.preventDefault();
                          selectObject();
                        }
                      }}
                      sx={{ cursor: "pointer" }}
                    >
                      <TableCell>
                        <Typography sx={{ fontWeight: 500, fontSize: 13 }}>{title}</Typography>
                        {otherDesignations.length > 0 && (
                          <Typography color="text.secondary" sx={{ fontSize: 12 }}>
                            {otherDesignations.join(", ")}
                          </Typography>
                        )}
                      </TableCell>
                      <TableCell sx={{ fontSize: 13 }}>{typeName}</TableCell>
                      <TableCell align="right" sx={{ fontSize: 13, whiteSpace: "nowrap" }}>
                        {objectSize(object.maj_axis_arcmin, object.min_axis_arcmin)}
                      </TableCell>
                      <TableCell
                        align="center"
                        onClick={(event) => event.stopPropagation()}
                        onKeyDown={(event) => event.stopPropagation()}
                      >
                        <Checkbox
                          size="small"
                          checked={object.is_main}
                          onChange={(event) =>
                            mainMutation.mutate({
                              dsoId: object.dso_id,
                              isMain: event.target.checked,
                            })
                          }
                          inputProps={{ "aria-label": `Main target: ${title}` }}
                          sx={{ color: done, "&.Mui-checked": { color: done } }}
                        />
                      </TableCell>
                    </TableRow>
                  );
                })}
              </TableBody>
            </Table>
          </TableContainer>
          <Typography color="text.secondary" sx={{ p: "9px 16px 14px", fontSize: 12.5 }}>
            Search finds projects by their main targets or by any object found here.
          </Typography>
        </Box>

        {solve.focal_length_estimates.length > 0 && (
          <Box
            sx={{
              bgcolor: "background.paper",
              border: 1,
              borderColor: "divider",
              borderRadius: "8px",
              overflow: "hidden",
            }}
          >
            <Typography component="h2" sx={{ p: "14px 16px 8px", fontSize: 15, fontWeight: 600 }}>
              Focal length check
            </Typography>
            <TableContainer>
              <Table
                size="small"
                aria-label="Focal length estimates"
                sx={{ "& th": { whiteSpace: "nowrap" } }}
              >
                <TableHead>
                  <TableRow>
                    <TableCell>Setup</TableCell>
                    <TableCell>Camera</TableCell>
                    <TableCell align="right">Rig says</TableCell>
                    <TableCell align="right">Image says</TableCell>
                  </TableRow>
                </TableHead>
                <TableBody>
                  {solve.focal_length_estimates.map((estimate) => (
                    <TableRow key={`${estimate.rig_id}:${estimate.rig_setup_id ?? "now"}`}>
                      <TableCell sx={{ fontSize: 13 }}>
                        <Typography component="div" sx={{ fontSize: 13 }}>
                          {estimate.rig_name}
                        </Typography>
                        <Typography component="div" color="text.secondary" sx={{ fontSize: 12 }}>
                          {estimate.setup_until_at
                            ? `until ${formatDay(estimate.setup_until_at)}`
                            : "now"}
                        </Typography>
                      </TableCell>
                      <TableCell sx={{ fontSize: 13 }}>
                        <Typography component="div" sx={{ fontSize: 13 }}>
                          {estimate.camera_name}
                        </Typography>
                        <Typography component="div" color="text.secondary" sx={{ fontSize: 12 }}>
                          {formatPixelSize(estimate.pixel_size_um)} µm pixels
                        </Typography>
                      </TableCell>
                      <TableCell align="right" sx={{ fontSize: 13, whiteSpace: "nowrap" }}>
                        {formatFocalLength(estimate.rig_focal_length_mm)} mm
                      </TableCell>
                      <TableCell align="right" sx={{ fontSize: 13, whiteSpace: "nowrap" }}>
                        ≈ {formatFocalLength(estimate.estimated_focal_length_mm)} mm
                      </TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            </TableContainer>
            <Typography color="text.secondary" sx={{ p: "9px 16px 14px", fontSize: 12 }}>
              Assumes the image&apos;s pixels are the camera&apos;s own. Binning, drizzling or resizing
              changes this estimate.
            </Typography>
          </Box>
        )}
      </Box>

      {error && (
        <Typography color="error" sx={{ fontSize: 13 }}>
          {error}
        </Typography>
      )}
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
