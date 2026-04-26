import Box from "@mui/material/Box";
import { RIG_BLUE, RIG_ORANGE } from "@/lib/rigColors";
import type { AnnotatedDso } from "@/api/plateSolve";

const MIN_CIRCLE_RADIUS_FRAC = 0.004;
const FALLBACK_RADIUS_FRAC = 0.004;
const FONT_FRAC = 0.012;
const STROKE_FRAC = 0.0015;
const SELECTED_STROKE_FRAC = 0.0025;
const TEXT_STROKE_FRAC = 0.002;
const LABEL_GAP_FRAC = 0.003;

interface Props {
  dsos: AnnotatedDso[];
  imageWidth: number;
  imageHeight: number;
  zoom: number;
  selectedId: number | null;
  onDsoClick: (id: number) => void;
}

export function PlateSolveAnnotationOverlay({
  dsos,
  imageWidth,
  imageHeight,
  selectedId,
  onDsoClick,
}: Props) {
  const refDim = Math.max(imageWidth, imageHeight);
  const fontSize = refDim * FONT_FRAC;
  const textStroke = refDim * TEXT_STROKE_FRAC;
  const strokeW = refDim * STROKE_FRAC;
  const selectedStrokeW = refDim * SELECTED_STROKE_FRAC;
  const minRadius = refDim * MIN_CIRCLE_RADIUS_FRAC;
  const fallbackRadius = refDim * FALLBACK_RADIUS_FRAC;
  const labelGap = refDim * LABEL_GAP_FRAC;

  return (
    <Box
      component="svg"
      sx={{
        position: "absolute",
        top: 0,
        left: 0,
        width: "100%",
        height: "100%",
        pointerEvents: "none",
      }}
      viewBox={`0 0 ${imageWidth} ${imageHeight}`}
      preserveAspectRatio="xMidYMid meet"
    >
      {dsos.map((dso) => {
        const isSelected = dso.id === selectedId;
        const color = isSelected ? RIG_ORANGE : RIG_BLUE;
        const sw = isSelected ? selectedStrokeW : strokeW;

        const hasEllipse =
          dso.ellipse_semi_major_px != null &&
          dso.ellipse_semi_minor_px != null &&
          dso.ellipse_semi_major_px > minRadius;

        const r = hasEllipse
          ? dso.ellipse_semi_major_px!
          : dso.ellipse_semi_major_px != null
            ? Math.max(minRadius, dso.ellipse_semi_major_px)
            : fallbackRadius;

        return (
          <g
            key={dso.id}
            onClick={(e) => {
              e.stopPropagation();
              onDsoClick(dso.id);
            }}
            style={{ pointerEvents: "all", cursor: "pointer" }}
          >
            {hasEllipse ? (
              <ellipse
                cx={dso.pixel_x}
                cy={dso.pixel_y}
                rx={dso.ellipse_semi_major_px!}
                ry={dso.ellipse_semi_minor_px!}
                transform={
                  dso.ellipse_angle_deg
                    ? `rotate(${dso.ellipse_angle_deg} ${dso.pixel_x} ${dso.pixel_y})`
                    : undefined
                }
                fill="transparent"
                stroke={color}
                strokeWidth={sw}
                opacity={isSelected ? 1.0 : 0.85}
              />
            ) : (
              <circle
                cx={dso.pixel_x}
                cy={dso.pixel_y}
                r={r}
                fill="transparent"
                stroke={color}
                strokeWidth={sw}
                opacity={isSelected ? 1.0 : 0.85}
              />
            )}
            <text
              x={dso.pixel_x + r + labelGap}
              y={dso.pixel_y + fontSize * 0.35}
              fill={color}
              fontSize={fontSize}
              fontWeight={isSelected ? 700 : 500}
              stroke="#000000"
              strokeWidth={textStroke}
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
