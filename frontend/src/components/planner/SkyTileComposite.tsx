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
import { useEffect, useMemo, useRef, useState } from "react";
import Box from "@mui/material/Box";
import { useQuery } from "@tanstack/react-query";
import {
  fetchSkyTileGrid,
  type SkyTileCellLayout,
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
  /** Rig sensor rectangle in angular degrees — centred on the view
   *  centre on first paint. When supplied, cells that intersect the
   *  rectangle are loaded first; cells outside it load after. Without
   *  this, priority falls back to distance-from-view-centre only. */
  rigMajorDeg?: number;
  rigMinorDeg?: number;
}

// Cells partitioned into load-order phases. Phase 1 always holds at
// most one cell; the others may be empty. Each phase starts fetching
// only after every cell in the previous phase has reported ready (or
// permanently failed), so the browser never races phase-N requests
// against phase-(N+1) requests that the user cares less about.
interface PhasePartition {
  centreCell: SkyTileCellLayout | null;
  rigCells: SkyTileCellLayout[];
  nearCells: SkyTileCellLayout[];
  restCells: SkyTileCellLayout[];
}

const EMPTY_PARTITION: PhasePartition = {
  centreCell: null,
  rigCells: [],
  nearCells: [],
  restCells: [],
};

function cellKey(cell: SkyTileCellLayout): string {
  return `${cell.nside}_${cell.ipix}_${cell.tier}_${cell.cell_i}_${cell.cell_j}`;
}

export default function SkyTileComposite({
  raDeg,
  decDeg,
  tier,
  fovMajorDeg,
  extentDeg,
  waitMs = 4000,
  onLayout,
  rigMajorDeg,
  rigMinorDeg,
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

  // Fire the onLayout callback when new layout data arrives. Must be
  // ``useEffect`` — React may drop or re-run ``useMemo`` factories
  // (and does in StrictMode), so side effects can't live there.
  useEffect(() => {
    if (layout) onLayout?.(layout);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [layout]);

  // Partition every cell in the layout into one of four load-order
  // phases. Order: centre → rig-intersecting → near-ring → rest.
  // Cells within each phase past the centre are sorted by distance
  // from the view centre so the browser fires them roughly
  // centre-outward when the phase mounts.
  const partition = useMemo<PhasePartition>(() => {
    if (!layout) return EMPTY_PARTITION;
    const vcx = layout.view_center_pixel_x;
    const vcy = layout.view_center_pixel_y;

    // Rig rectangle in composite source-pixel space, centred on the
    // view-centre pixel. Axis-aligned — the simulator starts at
    // rotation 0, and by the time the user rotates the rig, every
    // phase is long since mounted.
    let rigBounds: { xMin: number; xMax: number; yMin: number; yMax: number } | null =
      null;
    if (rigMajorDeg != null && rigMinorDeg != null && rigMajorDeg > 0 && rigMinorDeg > 0) {
      const pxPerDeg = layout.cell_width_px / layout.cell_size_deg;
      const halfW = (rigMajorDeg * pxPerDeg) / 2;
      const halfH = (rigMinorDeg * pxPerDeg) / 2;
      rigBounds = {
        xMin: vcx - halfW,
        xMax: vcx + halfW,
        yMin: vcy - halfH,
        yMax: vcy + halfH,
      };
    }

    // "Near ring" is the rig rectangle expanded by one cell on each
    // side. Any non-rig cell that intersects this expanded rectangle
    // counts as an immediate neighbour of the frame — loaded before
    // far-out peripheral cells. When no rig is supplied, near ring
    // is a single-cell-sized square around the view centre, which
    // catches the 8 cells immediately surrounding the centre.
    const cellW = layout.cell_width_px;
    const cellH = layout.cell_height_px;
    const nearBounds = rigBounds
      ? {
          xMin: rigBounds.xMin - cellW,
          xMax: rigBounds.xMax + cellW,
          yMin: rigBounds.yMin - cellH,
          yMax: rigBounds.yMax + cellH,
        }
      : {
          xMin: vcx - cellW,
          xMax: vcx + cellW,
          yMin: vcy - cellH,
          yMax: vcy + cellH,
        };

    function overlaps(
      cell: SkyTileCellLayout,
      bounds: { xMin: number; xMax: number; yMin: number; yMax: number },
    ): boolean {
      const xMin = cell.pixel_x;
      const xMax = cell.pixel_x + cellW;
      const yMin = cell.pixel_y;
      const yMax = cell.pixel_y + cellH;
      return (
        xMax > bounds.xMin &&
        xMin < bounds.xMax &&
        yMax > bounds.yMin &&
        yMin < bounds.yMax
      );
    }

    function distanceSq(cell: SkyTileCellLayout): number {
      const cx = cell.pixel_x + cellW / 2;
      const cy = cell.pixel_y + cellH / 2;
      return (cx - vcx) ** 2 + (cy - vcy) ** 2;
    }

    // Find the cell that contains the view-centre pixel — that's
    // always phase 1. Tie-break by closest cell centre if none of the
    // cells strictly contain the view-centre pixel (should never
    // happen when the grid is built correctly, but guards against an
    // off-by-one at region boundaries).
    let centreCell: SkyTileCellLayout | null = null;
    for (const cell of layout.cells) {
      if (
        vcx >= cell.pixel_x &&
        vcx < cell.pixel_x + cellW &&
        vcy >= cell.pixel_y &&
        vcy < cell.pixel_y + cellH
      ) {
        centreCell = cell;
        break;
      }
    }
    if (centreCell == null && layout.cells.length > 0) {
      centreCell = [...layout.cells].sort(
        (a, b) => distanceSq(a) - distanceSq(b),
      )[0];
    }

    const centreKey = centreCell != null ? cellKey(centreCell) : null;

    const rigCells: SkyTileCellLayout[] = [];
    const nearCells: SkyTileCellLayout[] = [];
    const restCells: SkyTileCellLayout[] = [];
    for (const cell of layout.cells) {
      if (centreKey != null && cellKey(cell) === centreKey) continue;
      if (rigBounds && overlaps(cell, rigBounds)) {
        rigCells.push(cell);
      } else if (overlaps(cell, nearBounds)) {
        nearCells.push(cell);
      } else {
        restCells.push(cell);
      }
    }

    rigCells.sort((a, b) => distanceSq(a) - distanceSq(b));
    nearCells.sort((a, b) => distanceSq(a) - distanceSq(b));
    restCells.sort((a, b) => distanceSq(a) - distanceSq(b));

    return { centreCell, rigCells, nearCells, restCells };
  }, [layout, rigMajorDeg, rigMinorDeg]);

  // Phase gates — each flips true when every cell in the previous
  // phase has reported ready (or permanently failed — SkyTileCell
  // fires onReady on the failure branch too, so one broken tile
  // doesn't wedge later phases).
  const [centreReady, setCentreReady] = useState(false);
  const [rigReady, setRigReady] = useState(false);
  const [nearReady, setNearReady] = useState(false);

  // Per-phase ready counters. Refs, not state — we don't need the
  // intermediate values to trigger re-renders; only the crossing of
  // each phase's threshold is render-relevant.
  const rigReadyCountRef = useRef(0);
  const nearReadyCountRef = useRef(0);

  // Reset every gate + counter when the layout or rig dims change.
  useEffect(() => {
    setCentreReady(false);
    setRigReady(false);
    setNearReady(false);
    rigReadyCountRef.current = 0;
    nearReadyCountRef.current = 0;
  }, [layout, rigMajorDeg, rigMinorDeg]);

  // If a phase is empty, advance past it immediately once its
  // predecessor is ready. Keeps the "nothing to load in phase 2" case
  // from leaving phase 3 wedged.
  useEffect(() => {
    if (centreReady && partition.rigCells.length === 0 && !rigReady) {
      setRigReady(true);
    }
  }, [centreReady, partition.rigCells.length, rigReady]);

  useEffect(() => {
    if (rigReady && partition.nearCells.length === 0 && !nearReady) {
      setNearReady(true);
    }
  }, [rigReady, partition.nearCells.length, nearReady]);

  if (!layout) {
    // Empty placeholder so the pan-group has a stable sizing anchor
    // while the layout request is in flight (~10 ms).
    return null;
  }

  const onRigCellReady = () => {
    rigReadyCountRef.current += 1;
    if (rigReadyCountRef.current >= partition.rigCells.length) {
      setRigReady(true);
    }
  };

  const onNearCellReady = () => {
    nearReadyCountRef.current += 1;
    if (nearReadyCountRef.current >= partition.nearCells.length) {
      setNearReady(true);
    }
  };

  return (
    <Box
      sx={{
        position: "relative",
        width: layout.composite_width_px,
        height: layout.composite_height_px,
      }}
    >
      {/* Phase 1 — centre cell. Alone on screen until it paints so
          the backend's 8-slot CDS semaphore is fully dedicated to the
          target-containing tile on cold cache. */}
      {partition.centreCell && (
        <Box
          key={cellKey(partition.centreCell)}
          sx={{
            position: "absolute",
            left: partition.centreCell.pixel_x,
            top: partition.centreCell.pixel_y,
            width: layout.cell_width_px,
            height: layout.cell_height_px,
          }}
        >
          <SkyTileCell
            cell={partition.centreCell}
            width={layout.cell_width_px}
            height={layout.cell_height_px}
            waitMs={waitMs}
            fetchPriority="high"
            onReady={() => setCentreReady(true)}
          />
        </Box>
      )}

      {/* Phase 2 — rig-intersecting cells. Only relevant when the
          rig rectangle spans more than one tile (wide / mosaic
          targets). Mounts after the centre reports ready. */}
      {centreReady &&
        partition.rigCells.map((cell) => (
          <Box
            key={cellKey(cell)}
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
              fetchPriority="high"
              onReady={onRigCellReady}
            />
          </Box>
        ))}

      {/* Phase 3 — near ring. Non-rig cells whose pixel bounds
          overlap the rig rectangle expanded by one cell on each side.
          For small rigs that fit in one tile this is the 8 immediate
          neighbours. Mounts after all phase-2 cells are ready. */}
      {rigReady &&
        partition.nearCells.map((cell) => (
          <Box
            key={cellKey(cell)}
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
              onReady={onNearCellReady}
            />
          </Box>
        ))}

      {/* Phase 4 — far-out cells. Lowest fetch priority; mounts only
          after every near-ring cell has painted. */}
      {nearReady &&
        partition.restCells.map((cell) => (
          <Box
            key={cellKey(cell)}
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
              fetchPriority="low"
            />
          </Box>
        ))}
    </Box>
  );
}
