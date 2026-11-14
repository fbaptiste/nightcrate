import { useLayoutEffect, useRef, useState } from "react";
import Box from "@mui/material/Box";
import type { GalleryTarget, OtherObjectDistance } from "../../api/gallery";
import {
  groupMarkers,
  labelAnchor,
  rulerX,
  valueLabel,
  type RulerSize,
} from "../../lib/distanceRuler";
import { formatDistance, lightYears, targetLabel } from "../../lib/objectFacts";

interface Props {
  size: RulerSize;
  targets: GalleryTarget[];
  others?: OtherObjectDistance[];
  highlightKey?: string | null;
}

const DIAMETERS: Record<RulerSize, { target: number; other: number; merged: number }> = {
  small: { target: 8, other: 6, merged: 15 },
  card: { target: 10, other: 7, merged: 15 },
  list: { target: 10, other: 7, merged: 15 },
  viewer: { target: 13, other: 8, merged: 19 },
  info: { target: 13, other: 8, merged: 19 },
};

const TICK_LABELS = [
  "100 ly",
  "1,000",
  "10,000",
  "100,000",
  "1 million",
  "10 million",
  "100 million",
  "1 billion",
  "10 billion",
];

function labelForTick(index: number, size: RulerSize): string | null {
  if (size === "small") return null;
  if (size === "info") return TICK_LABELS[index];
  if (size === "card") return index === 8 ? "10 billion" : null;
  if (size === "list") return index === 4 ? "1 million" : index === 8 ? "10 billion ly" : null;
  return index === 4 ? "1 million" : index === 8 ? "10 billion light-years" : null;
}

export default function DistanceRuler({ size, targets, others = [], highlightKey = null }: Props) {
  const rulerRef = useRef<HTMLDivElement>(null);
  const [width, setWidth] = useState(600);
  useLayoutEffect(() => {
    const ruler = rulerRef.current;
    if (!ruler) return;
    const measure = () => setWidth(Math.max(1, ruler.getBoundingClientRect().width));
    measure();
    const observer = new ResizeObserver(measure);
    observer.observe(ruler);
    return () => observer.disconnect();
  }, []);

  const targetItems = targets.flatMap((target) => target.distance_pc == null ? [] : [{
    key: `t:${target.dso_id}`,
    ly: lightYears(target.distance_pc),
    estimated: target.distance_estimated,
  }]);
  const otherItems = (size === "small" ? [] : others).map((other) => ({
    key: `o:${other.dso_id}`,
    ly: lightYears(other.distance_pc),
    estimated: other.distance_estimated,
  }));
  if (!targetItems.length && !otherItems.length) {
    return <Box sx={{ mt: size === "small" ? "6px" : "10px", mb: size === "small" ? "4px" : "8px", color: size === "viewer" ? "#a3a09b" : "text.secondary", fontSize: size === "viewer" || size === "info" ? 14 : 12.5 }}>No distance on record.</Box>;
  }

  const diameters = DIAMETERS[size];
  const targetGroups = groupMarkers(targetItems, width, diameters.target, diameters.merged);
  const otherGroups = groupMarkers(otherItems, width, diameters.other, diameters.merged);
  const merged = [...targetGroups, ...otherGroups].some((group) => group.keys.length > 1);
  const estimatedRing = [...targetGroups, ...otherGroups].some((group) => group.estimated);
  const value = valueLabel(targetItems, size === "viewer" || size === "info" ? "long" : "short", size === "viewer" || size === "info");
  const sortedTargets = [...targetItems].sort((a, b) => a.ly - b.ly);
  const anchor = sortedTargets.length
    ? labelAnchor(rulerX(sortedTargets[0].ly), rulerX(sortedTargets.at(-1)!.ly), size)
    : "start";
  const valuePosition = anchor === "end"
    ? { right: 0 }
    : anchor === "start"
      ? { left: 0 }
      : { left: `${(rulerX(sortedTargets[0].ly) + rulerX(sortedTargets.at(-1)!.ly)) / 2}%`, transform: "translateX(-50%)" };
  const info = size === "info";
  const viewer = size === "viewer";
  const small = size === "small";
  const valueRowHeight = info ? 18 : viewer ? 20 : 16;
  const laneCentre = valueRowHeight + diameters.merged / 2 + 2;
  const lineTop = small
    ? valueRowHeight + diameters.merged / 2 + 2
    : laneCentre + diameters.merged / 2 + 4;
  const height = lineTop + (info ? 62 : viewer ? 29 : small ? 13 : size === "list" ? 24 : 23);
  const bandHeight = info ? 12 : viewer ? 11 : 9;
  const targetLabelText = targets.length === 1 ? "Your target" : "Your targets";
  const ariaDistances = targets.map((target) => target.distance_pc == null
    ? `${targetLabel(target)}: no distance on record`
    : `${targetLabel(target)}: ${formatDistance(target.distance_pc, target.distance_estimated, "long", true)}`,
  ).join("; ");

  const marker = (
    group: ReturnType<typeof groupMarkers>[number],
    kind: "target" | "other",
  ) => {
    const isMerged = group.keys.length > 1;
    const diameter = isMerged ? diameters.merged : diameters[kind];
    const highlighted = highlightKey != null && group.keys.includes(highlightKey);
    const target = kind === "target";
    return (
      <Box
        key={`${kind}-${group.keys.join("-")}`}
        data-keys={group.keys.join(" ")}
        sx={(theme) => ({
          position: "absolute",
          left: `${group.x}%`,
          top: kind === "other" ? laneCentre : lineTop,
          width: diameter,
          height: diameter,
          transform: "translate(-50%, -50%)",
          borderRadius: "50%",
          display: "grid",
          placeItems: "center",
          boxSizing: "border-box",
          bgcolor: group.estimated
            ? viewer ? "#24272c" : (info ? "background.default" : "background.paper")
            : target ? viewer ? "#d4993f" : "primary.main" : viewer ? "#a3a09b" : "text.secondary",
          border: group.estimated ? `2px solid ${target ? viewer ? "#d4993f" : theme.palette.primary.main : viewer ? "#a3a09b" : theme.palette.text.secondary}` : 0,
          color: target ? viewer ? "#24272c" : theme.palette.getContrastText(theme.palette.primary.main) : viewer ? "#24272c" : "background.paper",
          opacity: target ? 1 : isMerged ? 0.85 : 0.6,
          boxShadow: highlighted
            ? `0 0 0 2px ${viewer ? "#24272c" : info ? theme.palette.background.default : theme.palette.background.paper}, 0 0 0 4px ${target ? viewer ? "#d4993f" : theme.palette.primary.main : viewer ? "#e2e0dd" : theme.palette.text.primary}`
            : target && !group.estimated ? `0 0 0 2px ${viewer ? "#24272c" : info ? theme.palette.background.default : theme.palette.background.paper}` : "none",
          zIndex: highlighted ? 3 : target ? 2 : 1,
          fontSize: isMerged ? (info || viewer ? 11 : 9.5) : 0,
          fontWeight: 700,
          lineHeight: 1,
          fontVariantNumeric: "tabular-nums",
        })}
      >
        {isMerged ? group.keys.length : null}
      </Box>
    );
  };

  return (
    <Box>
      <Box
        ref={rulerRef}
        role="img"
        aria-label={`Distance ruler. ${ariaDistances}`}
        sx={{ position: "relative", height, mt: small ? "6px" : info ? "6px" : viewer ? "18px" : "10px", mb: small ? "4px" : "8px" }}
      >
        <Box sx={(theme) => ({
          position: "absolute",
          left: 0,
          top: lineTop - bandHeight / 2,
          width: `${rulerX(100_000)}%`,
          height: bandHeight,
          borderRadius: "2px",
          bgcolor: viewer || theme.palette.mode === "dark" ? "rgba(125,154,184,0.22)" : "rgba(91,122,158,0.16)",
        })} />
        <Box sx={{ position: "absolute", left: 0, right: 0, top: lineTop, height: "1px", bgcolor: viewer ? "rgba(255,255,255,0.22)" : "divider" }} />
        {TICK_LABELS.map((_, index) => {
          const x = index * 12.5;
          const label = labelForTick(index, size);
          return (
            <Box key={index}>
              <Box sx={{ position: "absolute", left: `${x}%`, top: lineTop - (info ? 5 : 3), width: "1px", height: info ? 11 : viewer ? 9 : 7, bgcolor: viewer ? "rgba(255,255,255,0.22)" : "divider" }} />
              {label && (
                <Box sx={{
                  position: "absolute",
                  left: index === 8 ? undefined : `${x}%`,
                  right: index === 8 ? 0 : undefined,
                  top: lineTop + (info ? 11 : viewer ? 11 : 7),
                  transform: info && index > 0 && index < 8 ? "translateX(-50%)" : undefined,
                  color: viewer ? "#a3a09b" : "text.secondary",
                  fontSize: info ? 12 : viewer ? 12 : size === "list" ? 11 : 10.5,
                  lineHeight: info ? "16px" : "14px",
                  whiteSpace: "nowrap",
                  ...(viewer && index === 4 ? { "@container viewer (max-width: 599px)": { display: "none" } } : {}),
                }}>{label}</Box>
              )}
            </Box>
          );
        })}
        {!small && !info && (
          <Box sx={(theme) => ({ position: "absolute", left: 0, top: lineTop + (viewer ? 11 : 7), color: viewer || theme.palette.mode === "dark" ? "#a0b8d0" : "#3f5c78", fontSize: viewer ? 12 : size === "list" ? 11 : 10.5, lineHeight: viewer ? "16px" : "14px", whiteSpace: "nowrap" })}>
            Milky Way: about 100,000 {viewer ? "light-years" : "ly"} across
          </Box>
        )}
        {info && (
          <>
            <Box sx={(theme) => ({ position: "absolute", left: 0, top: lineTop + 33, width: `${rulerX(100_000)}%`, height: 6, border: 1, borderTop: 0, borderColor: theme.palette.mode === "dark" ? "#a0b8d0" : "#3f5c78", borderRadius: "0 0 2px 2px", opacity: 0.8 })} />
            <Box sx={(theme) => ({ position: "absolute", left: 0, top: lineTop + 41, width: `${rulerX(100_000)}%`, color: theme.palette.mode === "dark" ? "#a0b8d0" : "#3f5c78", textAlign: "center", fontSize: 12, lineHeight: "16px", whiteSpace: "nowrap" })}>Milky Way: about 100,000 light-years across</Box>
          </>
        )}
        {otherGroups.map((group) => marker(group, "other"))}
        {targetGroups.map((group) => marker(group, "target"))}
        <Box sx={{ position: "absolute", top: 0, color: viewer ? targetItems.length ? "#e2e0dd" : "#a3a09b" : targetItems.length ? "text.primary" : "text.secondary", fontSize: info ? 14 : viewer ? 15 : size === "list" ? 12.5 : small ? 11 : 12, lineHeight: info ? "18px" : viewer ? "20px" : "16px", fontWeight: targetItems.length ? 600 : 400, whiteSpace: "nowrap", fontVariantNumeric: "tabular-nums", ...valuePosition }}>
          {value ?? `No distance on record for your ${targets.length === 1 ? "target" : "targets"}`}
        </Box>
      </Box>
      {!small && size !== "card" && (
        <Box sx={{ display: "flex", flexWrap: "wrap", gap: "6px 18px", color: viewer ? "#a3a09b" : "text.secondary", fontSize: info || viewer ? 13 : 12.5, mt: info || viewer ? "6px" : "2px" }}>
          <LegendItem kind="target" viewer={viewer}>{targetLabelText}</LegendItem>
          {estimatedRing && <LegendItem kind="estimate" viewer={viewer}>Estimate worked out from redshift</LegendItem>}
          {otherItems.length > 0 && <LegendItem kind="other" viewer={viewer}>Other objects found in the plate-solved picture</LegendItem>}
          {merged && <LegendItem kind="merged" viewer={viewer}>Several at about the same distance</LegendItem>}
        </Box>
      )}
      {size === "card" && otherItems.length > 0 && (
        <Box sx={{ display: "flex", alignItems: "center", gap: "6px", color: "text.secondary", fontSize: 12, mt: "2px" }}>
          <LegendDot kind="other" />
          {otherItems.length} other {otherItems.length === 1 ? "object" : "objects"} found in the plate-solved picture
        </Box>
      )}
    </Box>
  );
}

function LegendDot({ kind, viewer = false }: { kind: "target" | "estimate" | "other" | "merged"; viewer?: boolean }) {
  return (
    <Box component="span" sx={{
      display: "inline-grid",
      placeItems: "center",
      alignSelf: "center",
      flex: "none",
      width: kind === "merged" ? 17 : kind === "estimate" ? 10 : 9,
      height: kind === "merged" ? 17 : kind === "estimate" ? 10 : 9,
      borderRadius: "50%",
      bgcolor: kind === "estimate" ? "transparent" : kind === "other" ? viewer ? "#a3a09b" : "text.secondary" : viewer ? "#d4993f" : "primary.main",
      border: kind === "estimate" ? 2 : 0,
      borderColor: viewer ? "#d4993f" : "primary.main",
      opacity: kind === "other" ? 0.7 : 1,
      color: viewer ? "#24272c" : "primary.contrastText",
      fontSize: 10.5,
      fontWeight: 700,
      lineHeight: 1,
    }}>{kind === "merged" ? "2" : null}</Box>
  );
}

function LegendItem({ kind, viewer, children }: { kind: "target" | "estimate" | "other" | "merged"; viewer: boolean; children: React.ReactNode }) {
  return <Box component="span" sx={{ display: "inline-flex", alignItems: "center", gap: "6px" }}><LegendDot kind={kind} viewer={viewer} />{children}</Box>;
}
