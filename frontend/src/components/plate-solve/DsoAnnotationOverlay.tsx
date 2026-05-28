import Box from "@mui/material/Box";
import { RIG_BLUE, RIG_ORANGE, RIG_TEAL } from "@/lib/rigColors";

export interface OverlayDso {
  id: number;
  pixel_x: number;
  pixel_y: number;
  ellipse_semi_major_px: number | null;
  ellipse_semi_minor_px: number | null;
  ellipse_angle_deg: number | null;
  common_name: string | null;
  primary_designation: string;
}

interface Props {
  imageHref: string;
  imgW: number;
  imgH: number;
  dsos: OverlayDso[];
  selectedId: number | null;
  onSelect: (id: number) => void;
  /** Object ids to render as "main" subjects (teal). Optional. */
  mainIds?: Set<number>;
}

/**
 * SVG catalog-annotation overlay drawn over an image in its native pixel
 * coordinate space (viewBox = naxis1 × naxis2). Shared by the Image Analyzer's
 * Identify tab and the project plate-solve view.
 */
export default function DsoAnnotationOverlay({
  imageHref,
  imgW,
  imgH,
  dsos,
  selectedId,
  onSelect,
  mainIds,
}: Props) {
  return (
    <Box
      component="svg"
      viewBox={imgW > 0 ? `0 0 ${imgW} ${imgH}` : undefined}
      preserveAspectRatio="xMidYMid meet"
      sx={{ maxWidth: "100%", maxHeight: "100%", display: "block" }}
    >
      <image href={imageHref} width={imgW || undefined} height={imgH || undefined} />
      {imgW > 0 &&
        dsos.map((dso) => {
          const isSelected = dso.id === selectedId;
          const isMain = mainIds?.has(dso.id) ?? false;
          const refDim = Math.max(imgW, imgH);
          const sw = refDim * (isSelected ? 0.0025 : 0.0015);
          const fs = refDim * 0.012;
          const ts = refDim * 0.002;
          const minR = refDim * 0.004;
          const gap = refDim * 0.003;
          const color = isSelected ? RIG_ORANGE : isMain ? RIG_TEAL : RIG_BLUE;
          const hasEllipse =
            dso.ellipse_semi_major_px != null &&
            dso.ellipse_semi_minor_px != null &&
            dso.ellipse_semi_major_px > minR;
          const a = hasEllipse
            ? dso.ellipse_semi_major_px!
            : dso.ellipse_semi_major_px != null
              ? Math.max(minR, dso.ellipse_semi_major_px)
              : minR;
          const b = hasEllipse ? dso.ellipse_semi_minor_px! : a;
          const theta = ((dso.ellipse_angle_deg ?? 0) * Math.PI) / 180;
          const cosT = Math.cos(theta);
          const sinT = Math.sin(theta);
          const edgeR = (a * b) / Math.sqrt(b * b * cosT * cosT + a * a * sinT * sinT);
          const labelOffset = edgeR + gap;
          return (
            <g
              key={dso.id}
              onClick={(e) => {
                e.stopPropagation();
                onSelect(dso.id);
              }}
              style={{ cursor: "pointer" }}
            >
              {hasEllipse ? (
                <ellipse
                  cx={dso.pixel_x}
                  cy={dso.pixel_y}
                  rx={a}
                  ry={b}
                  transform={
                    dso.ellipse_angle_deg
                      ? `rotate(${dso.ellipse_angle_deg} ${dso.pixel_x} ${dso.pixel_y})`
                      : undefined
                  }
                  fill="transparent"
                  stroke={color}
                  strokeWidth={sw}
                  opacity={isSelected ? 1 : 0.85}
                />
              ) : (
                <circle
                  cx={dso.pixel_x}
                  cy={dso.pixel_y}
                  r={a}
                  fill="transparent"
                  stroke={color}
                  strokeWidth={sw}
                  opacity={isSelected ? 1 : 0.85}
                />
              )}
              <text
                x={dso.pixel_x + labelOffset}
                y={dso.pixel_y + fs * 0.35}
                fill={color}
                fontSize={fs}
                fontWeight={isSelected || isMain ? 700 : 500}
                stroke="#000000"
                strokeWidth={ts}
                paintOrder="stroke"
              >
                {dso.common_name ?? dso.primary_designation}
              </text>
            </g>
          );
        })}
    </Box>
  );
}
