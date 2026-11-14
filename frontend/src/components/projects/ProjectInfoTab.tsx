import { lazy, Suspense, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import Box from "@mui/material/Box";
import Button from "@mui/material/Button";
import CircularProgress from "@mui/material/CircularProgress";
import Dialog from "@mui/material/Dialog";
import DialogActions from "@mui/material/DialogActions";
import DialogContent from "@mui/material/DialogContent";
import Link from "@mui/material/Link";
import Typography from "@mui/material/Typography";
import OpenInFullIcon from "@mui/icons-material/OpenInFull";
import OpenInNewIcon from "@mui/icons-material/OpenInNew";
import { fetchProjectInfo, projectInfoKey } from "@/api/projectInfo";
import DistanceRuler from "@/components/objects/DistanceRuler";
import WikipediaBadge from "@/components/objects/WikipediaBadge";
import SkyChartBoundary from "@/components/sky/SkyChartBoundary";
import { displayConstellation } from "@/lib/constellations";
import { formatDistance, targetLabel, typeLine, typeName } from "@/lib/objectFacts";
import { SKY_PALETTES } from "@/lib/skyChart/palette";
import { formatMonthDay } from "@/lib/skyChart/text";

const SkyChartCompact = lazy(() => import("@/components/sky/SkyChartCompact"));
const SkyChartDialog = lazy(() => import("@/components/sky/SkyChartDialog"));

interface Props {
  projectId: number;
  onPlateSolve: () => void;
}

export default function ProjectInfoTab({ projectId, onPlateSolve }: Props) {
  const [showAll, setShowAll] = useState(false);
  const [highlightKey, setHighlightKey] = useState<string | null>(null);
  const [skyChartOpen, setSkyChartOpen] = useState(false);
  const query = useQuery({
    queryKey: projectInfoKey(projectId),
    queryFn: () => fetchProjectInfo(projectId),
    staleTime: 0,
    refetchOnMount: "always",
  });

  if (query.isPending) return <Box sx={{ p: 2 }}><CircularProgress size={24} /></Box>;
  if (query.isError || !query.data) {
    return <Typography color="error">Couldn&apos;t load this project&apos;s info.</Typography>;
  }
  const info = query.data;
  if (!info.solved || !info.field) {
    return (
      <Box sx={{ maxWidth: 640, py: "48px" }}>
        <Typography component="h2" sx={{ fontSize: 18, lineHeight: 1.4, fontWeight: 600, mb: "6px" }}>
          Info appears once this project is plate solved
        </Typography>
        <Typography sx={{ color: "text.secondary", fontSize: 14, lineHeight: 1.5, mb: "16px" }}>
          Plate solving one of this project&apos;s pictures tells NightCrate exactly what&apos;s in it. This tab then shows your targets with their catalog numbers, constellation, distance and Wikipedia links, plus the other catalogued objects in the picture.
        </Typography>
        <Button variant="contained" onClick={onPlateSolve}>Plate solve it</Button>
      </Box>
    );
  }

  const objects = showAll ? info.other_objects : info.other_objects.slice(0, 10);
  const field = info.field;
  const sectionTitleSx = { fontSize: 15, lineHeight: 1.4, fontWeight: 600, mb: "10px" } as const;
  const skyBoxSx = {
    width: "100%",
    "@media (max-width: 1099.95px)": { maxWidth: 480 },
    aspectRatio: "4 / 3",
    mt: "14px",
    bgcolor: (theme: { palette: { mode: "light" | "dark" } }) => theme.palette.mode === "dark" ? SKY_PALETTES.night.sky : SKY_PALETTES.paper.sky,
  } as const;

  return (
    <Box sx={{ maxWidth: 1280, display: "grid", gridTemplateColumns: "minmax(0, 1fr) 340px", gap: "40px", alignItems: "start", "@media (max-width: 1099.95px)": { gridTemplateColumns: "minmax(0, 1fr)" } }}>
      <Box sx={{ minWidth: 0 }}>
        <Box>
          <Typography component="h2" sx={sectionTitleSx}>{info.targets.length === 1 ? "Target" : "Targets"}</Typography>
          <Box sx={{ borderTop: 1, borderColor: "divider" }}>
            {info.targets.map((target) => {
              const knownAs = target.also_known_as.filter((value) =>
                value.toLocaleLowerCase() !== target.name.toLocaleLowerCase() &&
                !target.catalog_numbers.some((number) => number.toLocaleLowerCase() === value.toLocaleLowerCase()),
              );
              return (
                <Box
                  key={target.dso_id}
                  onPointerEnter={() => setHighlightKey(`t:${target.dso_id}`)}
                  onPointerLeave={() => setHighlightKey(null)}
                  sx={{ display: "grid", gridTemplateColumns: "minmax(0, 1fr) auto", gap: "2px 24px", py: "14px", borderBottom: 1, borderColor: "divider" }}
                >
                  <Box sx={{ minWidth: 0 }}>
                    <Box sx={{ display: "flex", alignItems: "baseline", gap: "8px", flexWrap: "wrap" }}>
                      <Typography component="span" sx={{ fontSize: 20, lineHeight: 1.3, fontWeight: 600 }}>{targetLabel(target)}</Typography>
                      {target.catalog_numbers.length > 0 && <Typography component="span" sx={{ color: "text.secondary", fontSize: 14, lineHeight: 1.4 }}>{target.catalog_numbers.join(", ")}</Typography>}
                    </Box>
                    <Typography sx={{ color: "text.secondary", fontSize: 14, lineHeight: 1.4 }}>{typeLine([target])}</Typography>
                    {knownAs.length > 0 && <Typography sx={{ color: "text.secondary", fontSize: 12.5, lineHeight: 1.4, mt: "3px" }}>Also known as {knownAs.join(", ")}</Typography>}
                  </Box>
                  <Box sx={{ textAlign: "right", whiteSpace: "nowrap" }}>
                    <Typography sx={{ fontSize: 14, lineHeight: 1.5, color: target.distance_pc == null ? "text.secondary" : "text.primary", fontVariantNumeric: "tabular-nums" }}>
                      {target.distance_pc == null ? "No distance on record" : formatDistance(target.distance_pc, target.distance_estimated, "long", true)}
                    </Typography>
                    {target.wikipedia_url && (
                      <Link href={target.wikipedia_url} target="_blank" rel="noopener noreferrer" aria-label={`${target.name} on Wikipedia (opens in a new tab)`} underline="hover" sx={{ display: "inline-flex", alignItems: "center", gap: "4px", color: "primary.main", fontSize: 14, fontWeight: 500 }}>
                        Wikipedia <OpenInNewIcon sx={{ fontSize: 15 }} />
                      </Link>
                    )}
                  </Box>
                </Box>
              );
            })}
          </Box>
        </Box>

        <Box sx={{ mt: "32px" }}>
          <Typography component="h2" sx={sectionTitleSx}>How far away</Typography>
          <DistanceRuler size="info" targets={info.targets} others={info.other_distances} highlightKey={highlightKey} />
        </Box>

        {info.other_objects.length > 0 && (
          <Box sx={{ mt: "32px" }}>
            <Typography component="h2" sx={sectionTitleSx}>
              Also in this picture
              <Box component="span" sx={{ color: "text.secondary", fontSize: 13, fontWeight: 400, ml: "6px" }}>
                {info.other_objects.length} catalogued {info.other_objects.length === 1 ? "object" : "objects"}, nearest first
              </Box>
            </Typography>
            <Box component="table" sx={{ width: "100%", borderCollapse: "collapse", tableLayout: "fixed", fontSize: 14, "& th": { textAlign: "left", color: "text.secondary", fontSize: 13, fontWeight: 500, p: "6px 10px", borderBottom: 1, borderColor: "divider" }, "& td": { p: "7px 10px", borderBottom: 1, borderColor: "divider", verticalAlign: "baseline" }, "& tbody tr:hover td": { bgcolor: "action.hover" } }}>
              <colgroup><col style={{ width: "34%" }} /><col /><col style={{ width: 190 }} /><col style={{ width: 48 }} /></colgroup>
              <thead><tr><th>Object</th><th>Type</th><th style={{ textAlign: "right" }}>Distance</th><th><Box component="span" sx={{ position: "absolute", width: 1, height: 1, overflow: "hidden", clip: "rect(0 0 0 0)" }}>Wikipedia</Box></th></tr></thead>
              <tbody>
                {objects.map((object) => (
                  <tr key={object.dso_id} onPointerEnter={() => setHighlightKey(`o:${object.dso_id}`)} onPointerLeave={() => setHighlightKey(null)}>
                    <td>{object.designation}</td>
                    <td><Box component="span" sx={{ color: "text.secondary" }}>{typeName(object.obj_type)}</Box></td>
                    <td style={{ textAlign: "right", whiteSpace: "nowrap", fontVariantNumeric: "tabular-nums" }}>
                      {object.distance_pc == null
                        ? <Box component="span" sx={{ color: "text.secondary" }}>no distance</Box>
                        : formatDistance(object.distance_pc, object.distance_estimated, "short", false)}
                    </td>
                    <td style={{ textAlign: "right" }}>{object.wikipedia_url && <WikipediaBadge url={object.wikipedia_url} name={object.name} />}</td>
                  </tr>
                ))}
              </tbody>
            </Box>
            {info.other_objects.length > 10 && (
              <Button size="small" onClick={() => setShowAll((current) => !current)} sx={{ minWidth: 0, px: 0, mt: "8px", fontSize: 13 }}>
                {showAll ? "Show fewer" : `Show all ${info.other_objects.length}`}
              </Button>
            )}
          </Box>
        )}
      </Box>

      <Box component="aside" sx={{ borderLeft: 1, borderColor: "divider", pl: "28px", "@media (max-width: 1099.95px)": { borderLeft: 0, pl: 0, borderTop: 1, pt: "20px" } }}>
        <Typography sx={{ fontSize: 26, lineHeight: 1.15, fontWeight: 600, letterSpacing: "-0.015em" }}>{displayConstellation(field.constellation)}</Typography>
        <Typography sx={{ color: "text.secondary", fontSize: 13, mt: "2px" }}>The constellation at the centre of the picture</Typography>
        <SkyChartBoundary fallback={(
          <Box sx={{ ...skyBoxSx, display: "grid", placeItems: "center", px: 2 }}>
            <Typography sx={{ color: "text.secondary", fontSize: 13, textAlign: "center" }}>The sky chart couldn&apos;t load. Reload the page to try again.</Typography>
          </Box>
        )}>
          <Suspense fallback={<Box sx={skyBoxSx} />}>
            <SkyChartCompact field={field} projectId={projectId} projectName={info.name} onOpen={() => setSkyChartOpen(true)} />
          </Suspense>
        </SkyChartBoundary>
        <Typography sx={{ fontSize: 14, lineHeight: 1.5, mt: "14px" }}>
          On the meridian at midnight around{" "}
          <Box component="span" sx={{ fontWeight: 600 }}>{formatMonthDay(field.midnight_meridian_month, field.midnight_meridian_day)}</Box>
        </Typography>
        <Box component="dl" sx={{ m: 0, mt: "16px", display: "grid", gridTemplateColumns: "auto 1fr", gap: "6px 16px", fontSize: 14, "& dt": { color: "text.secondary" }, "& dd": { m: 0, fontVariantNumeric: "tabular-nums" } }}>
          <dt>Centre</dt><dd>{field.centre_ra_hms && field.centre_dec_dms ? `${field.centre_ra_hms}, ${field.centre_dec_dms}` : "—"}</dd>
          <dt>Field</dt><dd>{field.fov_width_deg != null && field.fov_height_deg != null ? `${field.fov_width_deg.toFixed(2)}° × ${field.fov_height_deg.toFixed(2)}°` : "—"}</dd>
          <dt>Rotation</dt><dd>{field.rotation_deg == null ? "—" : `${field.rotation_deg.toFixed(1)}°`}</dd>
        </Box>
        <Button variant="outlined" startIcon={<OpenInFullIcon />} onClick={() => setSkyChartOpen(true)} sx={{ mt: "18px" }}>
          Open the sky chart
        </Button>
      </Box>
      {skyChartOpen && (
        <SkyChartBoundary fallback={(
          <Dialog open fullScreen onClose={() => setSkyChartOpen(false)}>
            <DialogContent sx={{ display: "grid", placeItems: "center" }}>
              <Typography>The sky chart couldn&apos;t load. Reload the page to try again.</Typography>
            </DialogContent>
            <DialogActions><Button onClick={() => setSkyChartOpen(false)}>Close</Button></DialogActions>
          </Dialog>
        )}>
          <Suspense fallback={(
            <Dialog open fullScreen onClose={() => setSkyChartOpen(false)}>
              <Box sx={{ flex: 1, bgcolor: (theme) => theme.palette.mode === "dark" ? SKY_PALETTES.night.sky : SKY_PALETTES.paper.sky }} />
            </Dialog>
          )}>
            <SkyChartDialog open onClose={() => setSkyChartOpen(false)} info={info} />
          </Suspense>
        </SkyChartBoundary>
      )}
    </Box>
  );
}
