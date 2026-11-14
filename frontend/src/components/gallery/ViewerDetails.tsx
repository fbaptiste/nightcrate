import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import Box from "@mui/material/Box";
import Button from "@mui/material/Button";
import CircularProgress from "@mui/material/CircularProgress";
import { Link } from "react-router-dom";
import type { GalleryItem } from "@/api/gallery";
import { fetchProjectInfo, projectInfoKey } from "@/api/projectInfo";
import DistanceRuler from "@/components/objects/DistanceRuler";
import TargetRows from "@/components/objects/TargetRows";
import WikipediaBadge from "@/components/objects/WikipediaBadge";
import { formatHoursMinutes } from "@/components/projects/IntegrationBars";
import { formatImagingRuns } from "@/lib/galleryRendition";
import { formatDistance, typeLine } from "@/lib/objectFacts";

export type ViewerDetailsData = Pick<
  GalleryItem,
  | "project_id"
  | "targets"
  | "other_distances"
  | "imaging_runs"
  | "first_date"
  | "last_date"
  | "nights"
  | "integration_minutes"
  | "rigs"
>;

interface Props {
  projectId: number;
  details?: ViewerDetailsData;
  active: boolean;
}

export default function ViewerDetails({ projectId, details, active }: Props) {
  const [highlightKey, setHighlightKey] = useState<string | null>(null);
  const query = useQuery({
    queryKey: projectInfoKey(projectId),
    queryFn: () => fetchProjectInfo(projectId),
    enabled: active && details == null,
  });
  const data: ViewerDetailsData | undefined = details ?? query.data;
  if (!data) {
    return (
      <Box sx={{ minHeight: 120, display: "grid", placeItems: "center", color: "#a3a09b", fontSize: 14 }}>
        {query.isError
          ? "Couldn't load this project's details."
          : <CircularProgress size={24} sx={{ color: "#e2e0dd" }} />}
      </Box>
    );
  }

  const runs = formatImagingRuns(data);
  const sortedTargets = [...data.targets].sort((a, b) => {
    if (a.distance_pc == null) return 1;
    if (b.distance_pc == null) return -1;
    return a.distance_pc - b.distance_pc;
  });

  return (
    <Box sx={{ color: "#e2e0dd", fontSize: 15, "& a[aria-label*='Wikipedia']": { color: "#e2e0dd", borderColor: "rgba(255,255,255,0.28)", "&:hover": { color: "#d4993f", borderColor: "#d4993f" } } }}>
      <TargetRows
        targets={data.targets}
        size="viewer"
        showBadges
        onHighlight={setHighlightKey}
      />
      <Box sx={{ color: "#a3a09b", fontSize: 14, mt: "2px" }}>{typeLine(data.targets)}</Box>
      <DistanceRuler
        size="viewer"
        targets={data.targets}
        others={data.other_distances}
        highlightKey={highlightKey}
      />

      {data.targets.length > 4 && (
        <Box sx={{ mt: "14px", borderTop: "1px solid rgba(255,255,255,0.14)", maxHeight: 300, overflowY: "auto", scrollbarWidth: "thin" }}>
          <Box sx={{ display: "flex", justifyContent: "space-between", color: "#a3a09b", fontSize: 12.5, pt: "10px", pb: "4px" }}>
            <span>Nearest first</span><span>Distance</span>
          </Box>
          {sortedTargets.map((target) => (
            <Box
              key={target.dso_id}
              onPointerEnter={() => setHighlightKey(`t:${target.dso_id}`)}
              onPointerLeave={() => setHighlightKey(null)}
              sx={{ display: "grid", gridTemplateColumns: "minmax(0, 1fr) auto 28px", alignItems: "center", gap: "12px", py: "5px", px: "4px", borderRadius: "4px", fontSize: 14, "&:hover": { bgcolor: "rgba(255,255,255,0.05)" } }}
            >
              <Box sx={{ minWidth: 0, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{target.name}</Box>
              <Box sx={{ whiteSpace: "nowrap", fontVariantNumeric: "tabular-nums", color: target.distance_pc == null ? "#a3a09b" : "inherit" }}>
                {target.distance_pc == null
                  ? "no distance"
                  : formatDistance(target.distance_pc, target.distance_estimated, "short", false)}
              </Box>
              {target.wikipedia_url ? <WikipediaBadge url={target.wikipedia_url} name={target.name} /> : <span />}
            </Box>
          ))}
        </Box>
      )}

      <Box sx={{ mt: "18px", pt: "14px", borderTop: "1px solid rgba(255,255,255,0.14)", color: "#a3a09b", fontSize: 14, lineHeight: 1.5 }}>
        <Box sx={{ color: "#e2e0dd" }}>
          {runs.length ? runs.map((run) => <Box key={run}>Imaged {run}</Box>) : "No imaging dates"}
        </Box>
        <Box>
          {data.nights > 0 ? `${data.nights} ${data.nights === 1 ? "night" : "nights"}` : "No nights"}, {data.integration_minutes ? formatHoursMinutes(data.integration_minutes) : "None recorded"}
        </Box>
        <Box>{data.rigs.length ? data.rigs.map((rig) => rig.name).join(", ") : "No rigs"}</Box>
      </Box>
      <Button
        component={Link}
        to={`/projects/${projectId}`}
        variant="contained"
        onClick={(event) => event.stopPropagation()}
        sx={{ mt: "18px", height: 36, px: "16px", fontSize: 14, bgcolor: "#d4993f", color: "#24272c", "&:hover": { bgcolor: "#e0aa58" } }}
      >
        Open project
      </Button>
    </Box>
  );
}
