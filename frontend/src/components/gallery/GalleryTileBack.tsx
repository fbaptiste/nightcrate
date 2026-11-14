import { useEffect, useRef, useState, type RefObject } from "react";
import Box from "@mui/material/Box";
import Button from "@mui/material/Button";
import { Link } from "react-router-dom";
import type { GalleryItem } from "@/api/gallery";
import DistanceRuler from "@/components/objects/DistanceRuler";
import TargetRows from "@/components/objects/TargetRows";
import { formatHoursMinutes } from "@/components/projects/IntegrationBars";
import { formatImagingRuns } from "@/lib/galleryRendition";
import { typeLine } from "@/lib/objectFacts";
import StatusPills from "./StatusPills";

type GridView = "small" | "medium" | "large";

interface Props {
  item: GalleryItem;
  view: GridView;
  turned: boolean;
  onTurn: () => void;
  buttonRef: RefObject<HTMLButtonElement | null>;
}

interface BackContentProps {
  item: GalleryItem;
  runs: string[];
  large?: boolean;
}

function SmallBackContent({ item, runs }: BackContentProps) {
  const latest = runs.at(-1) ?? "No imaging dates";
  return (
    <Box sx={{ flex: "1 0 auto", fontSize: 12, lineHeight: 1.45 }}>
      <Box sx={{ whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis", fontWeight: 600 }}>
        {item.targets.length
          ? item.targets.map((target) => target.designation || target.name).join(", ")
          : "No targets"}
      </Box>
      <DistanceRuler size="small" targets={item.targets} others={item.other_distances} />
      <Box>{latest}</Box>
    </Box>
  );
}

function DetailBackContent({ item, runs, large = false }: BackContentProps) {
  const latest = runs.at(-1) ?? "No imaging dates";
  const earlier = runs.slice(0, -1);
  const rigText = item.rigs.length === 0
    ? null
    : item.rigs.length === 1
      ? item.rigs[0].name
      : item.rigs.length === 2
        ? `${item.rigs[0].name} and ${item.rigs[1].name}`
        : `${item.rigs[0].name} and ${item.rigs.length - 1} more`;
  const imagingDetails = [
    item.nights > 0 ? `${item.nights} ${item.nights === 1 ? "night" : "nights"}` : null,
    item.integration_minutes > 0 ? formatHoursMinutes(item.integration_minutes) : null,
    rigText,
  ].filter((detail): detail is string => detail != null);

  return (
    <Box sx={{ flex: "1 0 auto", display: "flex", flexDirection: "column", fontSize: large ? 14 : 13, ...(large ? { "& [data-target-rows='single'] [data-target-name]": { fontSize: "19px" }, "& [data-target-rows] a[aria-label*='Wikipedia']": { width: 24, height: 24, fontSize: 14 } } : {}) }}>
      <TargetRows targets={item.targets} size="card" showBadges />
      <Box sx={{ color: "text.secondary", fontSize: large ? 13 : 12.5, mt: "1px" }}>
        {typeLine(item.targets)}
      </Box>
      <DistanceRuler size="card" targets={item.targets} others={item.other_distances} />
      <Box sx={{ mt: "auto", pt: "8px", borderTop: 1, borderColor: "divider", color: "text.secondary", fontSize: large ? 13 : 12.5, lineHeight: 1.5 }}>
        {runs.length > 0 ? (
          <Box sx={{ display: "flex", minWidth: 0, color: "text.primary" }}>
            <Box component="span" sx={{ mr: "4px", flex: "none" }}>Imaged</Box>
            <Box sx={{ minWidth: 0, flex: 1, whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis" }}>
              {latest}
              {earlier.length > 0 && (
                <Box component="span" aria-label={`and earlier: ${earlier.join(", ")}`} sx={{ display: "inline-block", ml: "4px", px: "6px", border: 1, borderColor: "divider", borderRadius: "9px", color: "text.secondary", fontSize: 11, lineHeight: "16px" }}>
                  +{earlier.length} earlier
                </Box>
              )}
            </Box>
          </Box>
        ) : (
          <Box sx={{ color: "text.secondary" }}>No imaging dates</Box>
        )}
        {imagingDetails.length > 0 && <Box>{imagingDetails.join(", ")}</Box>}
      </Box>
    </Box>
  );
}

export default function GalleryTileBack({
  item,
  view,
  turned,
  onTurn,
  buttonRef,
}: Props) {
  const bodyRef = useRef<HTMLDivElement>(null);
  const [more, setMore] = useState(false);

  useEffect(() => {
    const body = bodyRef.current;
    if (!body) return;
    const check = () => {
      setMore(body.scrollTop + body.clientHeight < body.scrollHeight - 1);
    };
    check();
    const observer = new ResizeObserver(check);
    observer.observe(body);
    body.addEventListener("scroll", check);
    return () => {
      observer.disconnect();
      body.removeEventListener("scroll", check);
    };
  }, [item, view, turned]);

  const runs = formatImagingRuns(item);
  const small = view === "small";
  const large = view === "large";
  let padding = "14px 16px 12px";
  if (small) padding = "10px 10px 8px";
  if (large) padding = "20px 22px 16px";
  const fade = more
    ? { maskImage: "linear-gradient(to bottom, #000000 calc(100% - 28px), transparent)" }
    : {};

  return (
    <Box
      onClick={(event) => {
        if (!(event.target as HTMLElement).closest("a")) onTurn();
      }}
      sx={{
        width: "100%",
        height: "100%",
        bgcolor: "background.paper",
        border: 1,
        borderColor: "divider",
        borderRadius: "6px",
        p: padding,
        display: "flex",
        flexDirection: "column",
        overflow: "hidden",
        cursor: "pointer",
      }}
    >
      <Box
        ref={buttonRef}
        component="button"
        type="button"
        aria-label={`Show image for ${item.name}`}
        onClick={onTurn}
        sx={{
          position: "absolute",
          inset: 0,
          p: 0,
          border: 0,
          bgcolor: "transparent",
          cursor: "pointer",
          borderRadius: "6px",
          "&:focus-visible": { outlineOffset: "-3px" },
        }}
      />
      <Box
        ref={bodyRef}
        sx={{
          position: "relative",
          zIndex: 1,
          flex: "1 1 auto",
          minHeight: 0,
          overflowY: "auto",
          display: "flex",
          flexDirection: "column",
          scrollbarWidth: "none",
          "&::-webkit-scrollbar": { display: "none" },
          ...fade,
        }}
      >
        {!small && (
          <Box sx={{ flex: "none", display: "flex", justifyContent: "flex-end", mb: "4px" }}>
            <StatusPills status={item.status} retired={item.retired} />
          </Box>
        )}
        {small ? (
          <SmallBackContent item={item} runs={runs} />
        ) : (
          <DetailBackContent item={item} runs={runs} large={large} />
        )}
      </Box>
      <Box sx={{ position: "relative", zIndex: 2, flex: "none", pt: "8px" }}>
        <Button
          component={Link}
          to={`/projects/${item.project_id}`}
          variant="contained"
          size="small"
          onClick={(event) => event.stopPropagation()}
          sx={{
            minHeight: small ? 26 : 30,
            height: small ? 26 : 30,
            px: small ? 1 : 1.5,
            fontSize: small ? 12 : 13,
          }}
        >
          Open project
        </Button>
      </Box>
    </Box>
  );
}
