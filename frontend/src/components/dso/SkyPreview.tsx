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
 * Shows a spinner while the layout request is in flight; individual
 * cell fetches show their own spinners until they land. "No image
 * available" is the caller's responsibility (render a different
 * placeholder when ``raDeg`` / ``decDeg`` is null).
 */
import { useQuery } from "@tanstack/react-query";
import Box from "@mui/material/Box";
import CircularProgress from "@mui/material/CircularProgress";
import { fetchSkyTileGrid } from "@/api/planner";
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

  if (!query.data) {
    return (
      <Box
        sx={{
          width: size,
          height: size,
          display: "flex",
          alignItems: "center",
          justifyContent: "center",
          bgcolor: "action.hover",
        }}
      >
        <CircularProgress size={28} thickness={4} />
      </Box>
    );
  }

  const layout = query.data;
  // Scale so the preview extent exactly fills the viewport. The
  // composite is extentDeg × px_per_deg source pixels on the
  // narrowest axis, so ``size / (extent × px_per_deg)`` is the zoom.
  const pxPerDeg = layout.cell_width_px / layout.cell_size_deg;
  const viewExtentPx = extentDeg * pxPerDeg;
  const scale = size / viewExtentPx;
  // Translate so the DSO's pixel lands at the viewport centre.
  const translateX = size / 2 - layout.view_center_pixel_x * scale;
  const translateY = size / 2 - layout.view_center_pixel_y * scale;

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
              waitMs={4000}
            />
          </Box>
        ))}
      </Box>
    </Box>
  );
}
