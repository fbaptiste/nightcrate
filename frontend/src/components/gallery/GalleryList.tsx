import type { RefObject } from "react";
import Box from "@mui/material/Box";
import Link from "@mui/material/Link";
import { Link as RouterLink } from "react-router-dom";
import type { GalleryItem } from "@/api/gallery";
import DistanceRuler from "@/components/objects/DistanceRuler";
import TargetRows from "@/components/objects/TargetRows";
import { formatHoursMinutes } from "@/components/projects/IntegrationBars";
import { formatImagingRuns, pickRendition, tileImageUrl } from "@/lib/galleryRendition";
import { typeLine } from "@/lib/objectFacts";
import ExpandButton from "./ExpandButton";
import GalleryImage from "./GalleryImage";
import RigSummary from "./RigSummary";
import StatusPills from "./StatusPills";
import MatchChips from "./MatchChips";
import SolveMarkedImage from "./SolveMarkedImage";

interface Props {
  items: GalleryItem[];
  ws: string;
  onExpand: (id: number) => void;
  expandRefs: RefObject<Map<number, HTMLButtonElement>>;
  unavailableSolveIds: ReadonlySet<number>;
  solveRetries: ReadonlyMap<number, number>;
  onSolveUnavailable: (solveId: number) => void;
  showMatchNotes: boolean;
}

interface RowProps {
  item: GalleryItem;
  index: number;
  ws: string;
  onExpand: (id: number) => void;
  expandRefs: RefObject<Map<number, HTMLButtonElement>>;
  unavailableSolveIds: ReadonlySet<number>;
  solveRetries: ReadonlyMap<number, number>;
  onSolveUnavailable: (solveId: number) => void;
  showMatchNotes: boolean;
}

function GalleryListRow({
  item,
  index,
  ws,
  onExpand,
  expandRefs,
  unavailableSolveIds,
  solveRetries,
  onSolveUnavailable,
  showMatchNotes,
}: RowProps) {
  const runs = formatImagingRuns(item);
  const imageId = item.main_image_id;
  const src = tileImageUrl(item, "small", 180, window.devicePixelRatio || 1, ws);
  const solve =
    item.solve && !unavailableSolveIds.has(item.solve.solve_id) ? item.solve : null;
  const integration = item.integration_minutes
    ? formatHoursMinutes(item.integration_minutes)
    : "None recorded";

  const registerExpandButton = (button: HTMLButtonElement | null) => {
    if (button) expandRefs.current.set(item.project_id, button);
    else expandRefs.current.delete(item.project_id);
  };

  return (
    <Box
      sx={{
        display: "grid",
        gridTemplateColumns: "180px 1fr",
        gap: "20px",
        py: "16px",
        borderBottom: 1,
        borderColor: "divider",
        ...(index === 0 ? { pt: 0 } : {}),
      }}
    >
      <Box
        sx={{
          position: "relative",
          width: 180,
          aspectRatio: "4 / 3",
          bgcolor: "common.black",
          borderRadius: "6px",
          overflow: "hidden",
        }}
      >
        {solve ? (
          <SolveMarkedImage
            key={`${solve.solve_id}-${solveRetries.get(solve.solve_id) ?? 0}`}
            projectId={item.project_id}
            solve={solve}
            variant={pickRendition(180, window.devicePixelRatio || 1)}
            ws={ws}
            alt={item.name}
            onUnavailable={() => onSolveUnavailable(solve.solve_id)}
            matchMainTarget={item.match_main_target}
            matchInImage={item.match_in_image}
            compactChips
          />
        ) : src ? (
          <GalleryImage src={src} alt={item.name} />
        ) : (
          <Box
            sx={{
              display: "grid",
              placeItems: "center",
              height: "100%",
              color: "#8e8c88",
              fontSize: 13,
            }}
          >
            No main image
          </Box>
        )}
        {!solve && (
          <MatchChips
            mainTarget={item.match_main_target}
            inImage={item.match_in_image}
            compact
          />
        )}
        {(solve != null || imageId != null) && (
          <ExpandButton
            buttonRef={registerExpandButton}
            label={`View ${item.name} full size`}
            onClick={() => onExpand(item.project_id)}
            size="compact"
          />
        )}
      </Box>
      <Box sx={{ minWidth: 0 }}>
        <Box sx={{ display: "flex", alignItems: "center", gap: "10px", mb: "6px" }}>
          <Link
            component={RouterLink}
            to={`/projects/${item.project_id}`}
            underline="hover"
            color="text.primary"
            sx={{ fontSize: 16, fontWeight: 600 }}
          >
            {item.name}
          </Link>
          <StatusPills status={item.status} retired={item.retired} />
        </Box>
        {showMatchNotes && item.match_main_target && !item.has_solve && (
          <Box sx={{ color: "text.secondary", fontSize: 12.5, mb: "6px" }}>
            Not plate solved, so nothing is marked.
          </Box>
        )}
        {showMatchNotes && item.match_main_target && item.has_solve && !item.solve && (
          <Box sx={{ color: "text.secondary", fontSize: 12.5, mb: "6px" }}>
            Not in the plate-solved image.
          </Box>
        )}
        <Box sx={{ display: "grid", gridTemplateColumns: "minmax(0, 1fr) minmax(0, 290px)", gap: "32px", alignItems: "start" }}>
          <Box sx={{ minWidth: 0 }}>
            <TargetRows targets={item.targets} size="list" showBadges />
            <Box sx={{ color: "text.secondary", fontSize: 12.5, mt: "1px" }}>
              {typeLine(item.targets)}
            </Box>
            <DistanceRuler size="list" targets={item.targets} others={item.other_distances} />
          </Box>
          <Box component="dl" sx={{ m: 0, display: "grid", gridTemplateColumns: "auto 1fr", gap: "4px 16px", fontSize: 14 }}>
            <Box component="dt" sx={{ color: "text.secondary" }}>Imaging dates</Box>
            <Box component="dd" sx={{ m: 0, color: runs.length ? "text.primary" : "text.secondary" }}>
              {runs.length ? runs.map((run) => <Box key={run}>{run}</Box>) : "No imaging dates"}
              {item.nights > 0 && <Box sx={{ color: "text.secondary" }}>{item.nights} {item.nights === 1 ? "night" : "nights"}</Box>}
            </Box>
            <Box component="dt" sx={{ color: "text.secondary" }}>Integration</Box>
            <Box component="dd" sx={{ m: 0, color: item.integration_minutes ? "text.primary" : "text.secondary" }}>{integration}</Box>
            <Box component="dt" sx={{ color: "text.secondary" }}>Rigs</Box>
            <Box component="dd" sx={{ m: 0 }}><RigSummary rigs={item.rigs} /></Box>
          </Box>
        </Box>
      </Box>
    </Box>
  );
}

export default function GalleryList({
  items,
  ws,
  onExpand,
  expandRefs,
  unavailableSolveIds,
  solveRetries,
  onSolveUnavailable,
  showMatchNotes,
}: Props) {
  return (
    <Box sx={{ maxWidth: 980 }}>
      {items.map((item, index) => (
        <GalleryListRow
          key={item.project_id}
          item={item}
          index={index}
          ws={ws}
          onExpand={onExpand}
          expandRefs={expandRefs}
          unavailableSolveIds={unavailableSolveIds}
          solveRetries={solveRetries}
          onSolveUnavailable={onSolveUnavailable}
          showMatchNotes={showMatchNotes}
        />
      ))}
    </Box>
  );
}
