import Box from "@mui/material/Box";
import type { GalleryTarget } from "../../api/gallery";
import { countSummary, targetLabel } from "../../lib/objectFacts";
import WikipediaBadge from "./WikipediaBadge";

interface Props {
  targets: GalleryTarget[];
  size: "card" | "list" | "viewer";
  showBadges: boolean;
  onHighlight?: (key: string | null) => void;
}

export default function TargetRows({ targets, size, showBadges, onHighlight }: Props) {
  if (!targets.length) {
    return <Box sx={{ color: size === "viewer" ? "#a3a09b" : "text.secondary", fontSize: size === "viewer" ? 14 : 12.5 }}>No targets</Box>;
  }
  if (targets.length > 4) {
    const summary = countSummary(targets);
    return (
      <Box>
        <Box sx={{ fontSize: size === "viewer" ? 20 : 15, lineHeight: 1.3, fontWeight: 600 }}>
          {summary.head}
        </Box>
        <Box sx={{ color: size === "viewer" ? "#a3a09b" : "text.secondary", fontSize: size === "viewer" ? 14 : 12.5, mt: "2px" }}>
          {summary.names}
        </Box>
      </Box>
    );
  }
  const one = targets.length === 1;
  return (
    <Box data-target-rows={one ? "single" : "multiple"} sx={{ display: "grid", gap: size === "viewer" ? "4px" : "2px", ...(size === "viewer" ? { "& a[aria-label*='Wikipedia']": { width: 28, height: 28, fontSize: 16 } } : {}) }}>
      {targets.map((target) => {
        const label = targetLabel(target);
        return (
          <Box
            key={target.dso_id}
            onPointerEnter={() => onHighlight?.(`t:${target.dso_id}`)}
            onPointerLeave={() => onHighlight?.(null)}
            sx={{ display: "flex", alignItems: "center", gap: "8px", minWidth: 0 }}
          >
            <Box sx={{ minWidth: 0, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
              <Box
                component="span"
                data-target-name
                sx={{
                  fontWeight: 600,
                  fontSize: one
                    ? size === "viewer" ? 21 : size === "card" ? 17 : 16
                    : size === "viewer" ? 16 : 14,
                  lineHeight: 1.35,
                  letterSpacing: one ? "-0.01em" : undefined,
                }}
              >
                {label}
              </Box>
              {target.catalog_numbers.length > 0 && (
                <Box component="span" sx={{ ml: size === "viewer" ? "6px" : "4px", color: size === "viewer" ? "#a3a09b" : "text.secondary", fontSize: size === "viewer" ? 14 : 12.5 }}>
                  {target.catalog_numbers.join(", ")}
                </Box>
              )}
            </Box>
            {showBadges && target.wikipedia_url && (
              <Box sx={{ ml: "auto", display: "flex" }}>
                <WikipediaBadge url={target.wikipedia_url} name={label} />
              </Box>
            )}
          </Box>
        );
      })}
    </Box>
  );
}
