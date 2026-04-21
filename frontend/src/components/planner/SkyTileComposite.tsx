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
import { useMemo } from "react";
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
      {layout.cells.map((cell) => (
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
          />
        </Box>
      ))}
    </Box>
  );
}
