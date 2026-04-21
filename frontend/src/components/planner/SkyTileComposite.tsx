/**
 * v0.18.0 / Pass C — composite of sky-tile cells for a single view.
 *
 * Fetches the grid layout from ``/api/planner/sky-tile-grid`` (pure
 * HEALPix + WCS math server-side, <10 ms) and renders each cell at its
 * returned ``pixel_x / pixel_y`` inside a box sized to
 * ``composite_width_px × composite_height_px`` source pixels. Every
 * cell in the composite shares the same region-tangent, so adjacent
 * cells stitch pixel-perfectly.
 *
 * The composite's *source* size (what this component reports via
 * ``getSourceSize`` on ``onLayout``) is distinct from whatever CSS
 * size the parent renders it at — the caller transforms (pan/zoom/
 * rotate) the ``<div>`` to fit its viewport.
 *
 * ``view_center_pixel_x / y`` is the pixel inside the composite that
 * corresponds to the requested ``(ra, dec)``. Callers use it to anchor
 * pan / centring.
 */
import { useEffect, useMemo, useState } from "react";
import Box from "@mui/material/Box";
import { useQuery } from "@tanstack/react-query";
import {
  fetchSkyTileGrid,
  type SkyTileGridLayout,
  type SkyTileTier,
} from "@/api/planner";
import SkyTileCell from "./SkyTileCell";

interface Props {
  /** View centre in ICRS degrees. */
  raDeg: number;
  decDeg: number;
  /** Either supply an explicit tier or a rig ``fov_major_deg`` that the
   *  backend maps to a tier via ``tier_for_fov``. At least one is
   *  required. */
  tier?: SkyTileTier;
  fovMajorDeg?: number;
  /** View side in degrees (extent_deg × extent_deg). */
  extentDeg: number;
  /** Long-poll window handed down to each cell. Defaults to 4000 ms
   *  (matches the simulator's first-load ``waitMs`` from earlier). */
  waitMs?: number;
  /** Fires when the layout is fetched and cells are mounted. Gives the
   *  caller the composite's native pixel dimensions + view-centre
   *  offset so it can position / scale correctly. */
  onLayout?: (layout: SkyTileGridLayout) => void;
}

export default function SkyTileComposite({
  raDeg,
  decDeg,
  tier,
  fovMajorDeg,
  extentDeg,
  waitMs = 4000,
  onLayout,
}: Props) {
  const query = useQuery({
    // Round the ra/dec key inputs so that tiny jitter on the input
    // props doesn't refire the layout request and remount the cells.
    queryKey: [
      "sky-tile-grid",
      raDeg.toFixed(4),
      decDeg.toFixed(4),
      tier ?? null,
      fovMajorDeg != null ? fovMajorDeg.toFixed(4) : null,
      extentDeg.toFixed(4),
    ],
    queryFn: () =>
      fetchSkyTileGrid({ raDeg, decDeg, tier, fovMajorDeg, extentDeg }),
    // Layouts are pure math; keep them fresh indefinitely for the
    // current view.
    staleTime: 60 * 60 * 1000,
  });

  const layout = query.data;

  // Fire the onLayout callback when new layout data arrives.
  useMemo(() => {
    if (layout) onLayout?.(layout);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [layout]);

  // Stage the cell mount so the centre cell (containing the DSO's
  // view-centre pixel) loads first and the user sees the target
  // quickly. Non-centre cells mount only after the centre reports
  // ``onReady``, so the 4-slot CDS semaphore isn't contended by
  // surrounding cells while the centre is mid-flight. On warm cache
  // every cell is ready instantly and the two phases collapse into
  // one render frame.
  const [centerReady, setCenterReady] = useState(false);
  useEffect(() => {
    // Reset staging when the target / tier / extent changes.
    setCenterReady(false);
  }, [layout]);

  const centerCellIdx = useMemo(() => {
    if (!layout || layout.cells.length === 0) return -1;
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
    // Fallback: the cell whose centre is nearest the view centre —
    // handles edge cases where the DSO sits exactly on a cell seam.
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
  }, [layout]);

  if (!layout) {
    // Empty placeholder so the pan-group has a stable sizing anchor
    // while the layout request is in flight (~10 ms).
    return null;
  }

  return (
    <Box
      sx={{
        position: "relative",
        width: layout.composite_width_px,
        height: layout.composite_height_px,
      }}
    >
      {layout.cells.map((cell, i) => {
        const isCenter = i === centerCellIdx;
        // Defer non-centre cells until the centre lands. The parent
        // already sizes the pan group to ``composite_width_px ×
        // composite_height_px``, so empty slots render as the
        // container's black background — not visible because the
        // pan-group transform keeps the viewport over the centre.
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
              waitMs={waitMs}
              onReady={isCenter ? () => setCenterReady(true) : undefined}
            />
          </Box>
        );
      })}
    </Box>
  );
}
