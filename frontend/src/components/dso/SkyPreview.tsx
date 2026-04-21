/**
 * Auto-zoom sky-tile preview for the DSO catalog detail panel.
 *
 * Picks a tier + extent from the object's major axis (via
 * ``previewSpecForDsoSize``), fetches the sky-tile grid layout, and
 * renders the composite inside a square viewport of ``size`` CSS
 * pixels. The composite is scaled so the preview extent exactly fills
 * the viewport and translated so the DSO's (ra, dec) sits at the
 * viewport centre.
 *
 * Reuses the same sky-tile cells the FOV simulator fetches — a
 * neighbour DSO in the same HEALPix region populated by the simulator
 * will hit the cache here, and vice-versa.
 *
 * Loading UX: a centred spinner covers the viewport until the centre
 * cell lands. Because cells are scaled down by the composite's CSS
 * transform, each cell's own built-in spinner is too small to notice
 * — the outer, un-scaled overlay is what the user reads as "still
 * loading". After the centre cell paints, the overlay hides; any
 * peripheral cells still loading show their own tiny spinners but the
 * target is already visible.
 */
import { useEffect, useMemo, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import Box from "@mui/material/Box";
import CircularProgress from "@mui/material/CircularProgress";
import { fetchSkyTileGrid, type SkyTileGridLayout } from "@/api/planner";
import { previewSpecForDsoSize } from "@/lib/skyPreviewExtent";
import SkyTileCell from "@/components/planner/SkyTileCell";

interface Props {
  raDeg: number;
  decDeg: number;
  /** DSO's angular major axis (arcmin). Drives the auto-zoom
   *  decision. ``null`` falls back to a sensible default extent. */
  majAxisArcmin: number | null;
  /** CSS pixel size of the viewport (square). */
  size: number;
}

/** Identify the cell containing the composite's view-centre pixel —
 *  the one the user's eye is anchored on. Falls back to the cell
 *  whose own centre is nearest to the view centre when the view
 *  sits exactly on a seam. */
function findCenterCellIdx(layout: SkyTileGridLayout): number {
  if (layout.cells.length === 0) return -1;
  const cx = layout.view_center_pixel_x;
  const cy = layout.view_center_pixel_y;
  for (let i = 0; i < layout.cells.length; i++) {
    const c = layout.cells[i];
    if (
      cx >= c.pixel_x &&
      cx < c.pixel_x + layout.cell_width_px &&
      cy >= c.pixel_y &&
      cy < c.pixel_y + layout.cell_height_px
    ) {
      return i;
    }
  }
  let best = 0;
  let bestDistSq = Infinity;
  for (let i = 0; i < layout.cells.length; i++) {
    const c = layout.cells[i];
    const cellCx = c.pixel_x + layout.cell_width_px / 2;
    const cellCy = c.pixel_y + layout.cell_height_px / 2;
    const d = (cellCx - cx) ** 2 + (cellCy - cy) ** 2;
    if (d < bestDistSq) {
      bestDistSq = d;
      best = i;
    }
  }
  return best;
}

export default function SkyPreview({
  raDeg,
  decDeg,
  majAxisArcmin,
  size,
}: Props) {
  const { tier, extentDeg } = previewSpecForDsoSize(majAxisArcmin);

  const query = useQuery({
    queryKey: [
      "sky-tile-grid-preview",
      raDeg.toFixed(4),
      decDeg.toFixed(4),
      tier,
      extentDeg.toFixed(4),
    ],
    queryFn: () => fetchSkyTileGrid({ raDeg, decDeg, tier, extentDeg }),
    staleTime: 60 * 60 * 1000,
  });

  const layout = query.data ?? null;
  const [centerReady, setCenterReady] = useState(false);
  useEffect(() => {
    setCenterReady(false);
  }, [layout]);

  const centerCellIdx = useMemo(
    () => (layout ? findCenterCellIdx(layout) : -1),
    [layout],
  );

  // Scale so the preview extent exactly fills the viewport. Computed
  // once the layout lands; rendered inside a scaled container so
  // each cell's native JPEG (e.g. 800×800 narrow-tier source) ends
  // up at whatever CSS footprint fits the preview window.
  const scale = layout
    ? size / (extentDeg * (layout.cell_width_px / layout.cell_size_deg))
    : 1;
  const translateX = layout ? size / 2 - layout.view_center_pixel_x * scale : 0;
  const translateY = layout ? size / 2 - layout.view_center_pixel_y * scale : 0;

  const showOverlay = !layout || !centerReady;

  return (
    <Box
      sx={{
        position: "relative",
        width: size,
        height: size,
        overflow: "hidden",
        bgcolor: "#000000",
      }}
    >
      {layout && (
        <Box
          sx={{
            position: "absolute",
            top: 0,
            left: 0,
            width: layout.composite_width_px,
            height: layout.composite_height_px,
            transform: `translate(${translateX}px, ${translateY}px) scale(${scale})`,
            transformOrigin: "0 0",
          }}
        >
          {layout.cells.map((cell, i) => {
            const isCenter = i === centerCellIdx;
            // Two-phase mount: centre first so the backend's 4-slot
            // semaphore focuses on the target, then the rest come in
            // after ``onReady``.
            if (!isCenter && !centerReady) return null;
            return (
              <Box
                key={`${cell.nside}_${cell.ipix}_${cell.tier}_${cell.cell_i}_${cell.cell_j}`}
                sx={{
                  position: "absolute",
                  left: cell.pixel_x,
                  top: cell.pixel_y,
                  width: layout.cell_width_px,
                  height: layout.cell_height_px,
                }}
              >
                <SkyTileCell
                  cell={cell}
                  width={layout.cell_width_px}
                  height={layout.cell_height_px}
                  waitMs={4000}
                  onReady={isCenter ? () => setCenterReady(true) : undefined}
                />
              </Box>
            );
          })}
        </Box>
      )}

      {showOverlay && (
        <Box
          sx={{
            position: "absolute",
            inset: 0,
            display: "flex",
            alignItems: "center",
            justifyContent: "center",
            // Semi-transparent so any cells already painted are
            // visible behind the spinner — less jarring than a
            // solid block.
            bgcolor: "rgba(0, 0, 0, 0.55)",
            color: "#ffffff",
            pointerEvents: "none",
          }}
        >
          <CircularProgress size={32} thickness={4} color="inherit" />
        </Box>
      )}
    </Box>
  );
}
