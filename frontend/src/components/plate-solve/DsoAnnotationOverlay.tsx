import { memo, useCallback, useLayoutEffect, useRef, useState } from "react";
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
  mainIds?: Set<number>;
  palette?: "default" | "project";
  onDoubleSelect?: (id: number) => void;
  scaleFromCss?: boolean;
}

interface MarkerPalette {
  stroke: string;
  label: string;
  width: number;
  opacity: number;
  selectedOuter?: string;
  selectedOuterWidth?: number;
}

function markerPalette(
  palette: "default" | "project",
  isSelected: boolean,
  isMain: boolean,
): MarkerPalette {
  if (palette === "project") {
    if (isSelected && isMain) {
      return {
        stroke: "#4fb0ff",
        label: "#ffd400",
        width: 2.5,
        opacity: 1,
        selectedOuter: "#ffd400",
        selectedOuterWidth: 2,
      };
    }
    if (isSelected) {
      return { stroke: "#ffd400", label: "#ffd400", width: 2.5, opacity: 1 };
    }
    if (isMain) {
      return { stroke: "#4fb0ff", label: "#4fb0ff", width: 2.5, opacity: 1 };
    }
    return { stroke: "#9a9894", label: "#b8b6b2", width: 1.2, opacity: 0.9 };
  }
  const color = isSelected ? RIG_ORANGE : isMain ? RIG_TEAL : RIG_BLUE;
  return {
    stroke: color,
    label: color,
    width: isSelected ? 2.5 : 1.5,
    opacity: isSelected ? 1 : 0.85,
  };
}

function screenScale(svg: SVGSVGElement | null): number {
  const matrix = svg?.getScreenCTM();
  if (!matrix) return 1;
  return Math.max(0.000001, Math.hypot(matrix.a, matrix.b));
}

function scaledLength(value: number): string {
  return `calc(${value}px * var(--dso-unit, 1))`;
}

interface CssScaledMarkerProps {
  dso: OverlayDso;
  imgW: number;
  isSelected: boolean;
  isMain: boolean;
  palette: "default" | "project";
  onSelect: (id: number) => void;
  onDoubleSelect?: (id: number) => void;
}

const CssScaledMarker = memo(function CssScaledMarker({
  dso,
  imgW,
  isSelected,
  isMain,
  palette,
  onSelect,
  onDoubleSelect,
}: CssScaledMarkerProps) {
  const colors = markerPalette(palette, isSelected, isMain);
  const hasEllipse =
    dso.ellipse_semi_major_px != null &&
    dso.ellipse_semi_minor_px != null &&
    dso.ellipse_semi_major_px > 0 &&
    dso.ellipse_semi_minor_px > 0;
  const a = dso.ellipse_semi_major_px ?? 0;
  const b = dso.ellipse_semi_minor_px ?? 0;
  const angle = dso.ellipse_angle_deg ?? 0;
  const theta = (angle * Math.PI) / 180;
  const cosTheta = Math.cos(theta);
  const sinTheta = Math.sin(theta);
  const edgeRadius = hasEllipse
    ? (a * b) / Math.sqrt(b * b * cosTheta * cosTheta + a * a * sinTheta * sinTheta)
    : 0;
  const rawLabelX = dso.pixel_x + edgeRadius;
  const overflowRight = rawLabelX > imgW;
  const labelX = overflowRight ? imgW : Math.max(0, rawLabelX);
  const labelOffsetX = hasEllipse ? (overflowRight ? -3 : 3) : overflowRight ? -7 : 7;
  const transform = angle
    ? `rotate(${angle} ${dso.pixel_x} ${dso.pixel_y})`
    : undefined;
  const hitWidth = colors.width + 12;
  const select = (event: React.SyntheticEvent) => {
    event.stopPropagation();
    onSelect(dso.id);
  };
  const doubleSelect = (event: React.MouseEvent) => {
    event.stopPropagation();
    onDoubleSelect?.(dso.id);
  };
  const shape = (
    stroke: string,
    strokeWidthCss: number,
    radiusOffsetCss = 0,
    opacity = 1,
    interactive = false,
  ) => {
    if (!hasEllipse) {
      return (
        <g
          style={{
            transform: "scale(var(--dso-unit, 1))",
            transformOrigin: `${dso.pixel_x}px ${dso.pixel_y}px`,
          }}
        >
          <circle
            cx={dso.pixel_x}
            cy={dso.pixel_y}
            r={4 + radiusOffsetCss}
            fill="none"
            stroke={stroke}
            strokeWidth={strokeWidthCss}
            opacity={opacity}
            pointerEvents={interactive ? "stroke" : "none"}
            onClick={interactive ? select : undefined}
            onDoubleClick={interactive ? doubleSelect : undefined}
          />
        </g>
      );
    }
    const geometryStyle =
      radiusOffsetCss === 0
        ? undefined
        : ({
            rx: `calc(${a}px + ${radiusOffsetCss}px * var(--dso-unit, 1))`,
            ry: `calc(${b}px + ${radiusOffsetCss}px * var(--dso-unit, 1))`,
          } as React.CSSProperties);
    return (
      <ellipse
        cx={dso.pixel_x}
        cy={dso.pixel_y}
        rx={a}
        ry={b}
        transform={transform}
        fill="none"
        stroke={stroke}
        opacity={opacity}
        pointerEvents={interactive ? "stroke" : "none"}
        onClick={interactive ? select : undefined}
        onDoubleClick={interactive ? doubleSelect : undefined}
        style={{ ...geometryStyle, strokeWidth: scaledLength(strokeWidthCss) }}
      />
    );
  };

  return (
    <g style={{ cursor: "pointer" }}>
      {colors.selectedOuter &&
        shape(colors.selectedOuter, colors.selectedOuterWidth ?? 2, 2.25)}
      {shape(colors.stroke, colors.width, 0, colors.opacity)}
      {shape("transparent", hitWidth, 0, 1, true)}
      <text
        x={labelX}
        y={dso.pixel_y}
        textAnchor={overflowRight ? "end" : "start"}
        fill={colors.label}
        fontSize={12}
        fontWeight={isSelected || isMain ? 700 : 500}
        stroke="#000000"
        strokeWidth={3}
        strokeLinejoin="round"
        paintOrder="stroke"
        onClick={select}
        onDoubleClick={doubleSelect}
        style={{
          transform: `scale(var(--dso-unit, 1)) translate(${labelOffsetX}px, 4.2px)`,
          transformOrigin: `${labelX}px ${dso.pixel_y}px`,
        }}
      >
        {palette === "project"
          ? `${dso.primary_designation}${dso.common_name ? ` · ${dso.common_name}` : ""}`
          : (dso.common_name ?? dso.primary_designation)}
      </text>
    </g>
  );
});

/**
 * SVG catalog annotations in source-pixel coordinates. Normal callers measure
 * the rendered SVG's CTM; the zoomable project viewer supplies the same scale
 * through one inherited CSS variable so view changes do not rebuild markers.
 */
function DsoAnnotationOverlay({
  imageHref,
  imgW,
  imgH,
  dsos,
  selectedId,
  onSelect,
  mainIds,
  palette = "default",
  onDoubleSelect,
  scaleFromCss = false,
}: Props) {
  const svgRef = useRef<SVGSVGElement | null>(null);
  const [scale, setScale] = useState(1);

  const measure = useCallback(() => {
    const svg = svgRef.current;
    if (!svg) return;
    const next = screenScale(svg);
    setScale((current) => (Math.abs(current - next) > 0.0001 ? next : current));
  }, []);

  useLayoutEffect(() => {
    if (!scaleFromCss) measure();
  });
  useLayoutEffect(() => {
    if (scaleFromCss) return;
    const svg = svgRef.current;
    if (!svg) return;
    measure();
    const observer = new ResizeObserver(measure);
    observer.observe(svg);
    window.addEventListener("resize", measure);
    return () => {
      observer.disconnect();
      window.removeEventListener("resize", measure);
    };
  }, [measure, scaleFromCss]);

  const unitsPerCssPixel = 1 / scale;
  return (
    <Box
      ref={svgRef}
      component="svg"
      width={imgW || undefined}
      height={imgH || undefined}
      viewBox={imgW > 0 ? `0 0 ${imgW} ${imgH}` : undefined}
      preserveAspectRatio="xMidYMid meet"
      sx={{
        width: "100%",
        height: "100%",
        maxWidth: "100%",
        maxHeight: "100%",
        display: "block",
      }}
    >
      <image href={imageHref} width={imgW || undefined} height={imgH || undefined} />
      {imgW > 0 &&
        dsos.map((dso) => {
          const isSelected = dso.id === selectedId;
          const isMain = mainIds?.has(dso.id) ?? false;
          if (scaleFromCss) {
            return (
              <CssScaledMarker
                key={dso.id}
                dso={dso}
                imgW={imgW}
                isSelected={isSelected}
                isMain={isMain}
                palette={palette}
                onSelect={onSelect}
                onDoubleSelect={onDoubleSelect}
              />
            );
          }
          const colors = markerPalette(palette, isSelected, isMain);
          const fontSize = 12 * unitsPerCssPixel;
          const textStroke = 3 * unitsPerCssPixel;
          const minimumRadius = 4 * unitsPerCssPixel;
          const gap = 3 * unitsPerCssPixel;
          const hasEllipse =
            dso.ellipse_semi_major_px != null &&
            dso.ellipse_semi_minor_px != null &&
            dso.ellipse_semi_major_px > minimumRadius;
          const a = hasEllipse
            ? dso.ellipse_semi_major_px!
            : Math.max(minimumRadius, dso.ellipse_semi_major_px ?? minimumRadius);
          const b = hasEllipse ? dso.ellipse_semi_minor_px! : a;
          const angle = dso.ellipse_angle_deg ?? 0;
          const theta = (angle * Math.PI) / 180;
          const cosTheta = Math.cos(theta);
          const sinTheta = Math.sin(theta);
          const edgeRadius =
            (a * b) /
            Math.sqrt(b * b * cosTheta * cosTheta + a * a * sinTheta * sinTheta);
          const rawLabelX = dso.pixel_x + edgeRadius + gap;
          const overflowRight = rawLabelX > imgW - gap;
          const labelX = overflowRight ? imgW - gap : Math.max(gap, rawLabelX);
          const labelY = Math.max(
            fontSize,
            Math.min(imgH - gap, dso.pixel_y + fontSize * 0.35),
          );
          const transform = angle
            ? `rotate(${angle} ${dso.pixel_x} ${dso.pixel_y})`
            : undefined;
          const hitWidth = colors.width + 12;
          const smallOnScreen = 2 * Math.max(a, b) * scale < 12;
          const select = (event: React.SyntheticEvent) => {
            event.stopPropagation();
            onSelect(dso.id);
          };
          const doubleSelect = (event: React.MouseEvent) => {
            event.stopPropagation();
            onDoubleSelect?.(dso.id);
          };
          const shape = (
            stroke: string,
            strokeWidthCss: number,
            radiusOffsetCss = 0,
            opacity = 1,
          ) =>
            hasEllipse ? (
              <ellipse
                cx={dso.pixel_x}
                cy={dso.pixel_y}
                rx={a + radiusOffsetCss * unitsPerCssPixel}
                ry={b + radiusOffsetCss * unitsPerCssPixel}
                transform={transform}
                fill="none"
                stroke={stroke}
                strokeWidth={strokeWidthCss * unitsPerCssPixel}
                opacity={opacity}
                pointerEvents="none"
              />
            ) : (
              <circle
                cx={dso.pixel_x}
                cy={dso.pixel_y}
                r={a + radiusOffsetCss * unitsPerCssPixel}
                fill="none"
                stroke={stroke}
                strokeWidth={strokeWidthCss * unitsPerCssPixel}
                opacity={opacity}
                pointerEvents="none"
              />
            );
          return (
            <g key={dso.id} style={{ cursor: "pointer" }}>
              {colors.selectedOuter &&
                shape(colors.selectedOuter, colors.selectedOuterWidth ?? 2, 2.25)}
              {shape(colors.stroke, colors.width, 0, colors.opacity)}
              {hasEllipse ? (
                <ellipse
                  cx={dso.pixel_x}
                  cy={dso.pixel_y}
                  rx={a}
                  ry={b}
                  transform={transform}
                  fill={smallOnScreen ? "transparent" : "none"}
                  stroke="transparent"
                  strokeWidth={hitWidth * unitsPerCssPixel}
                  pointerEvents={smallOnScreen ? "all" : "stroke"}
                  onClick={select}
                  onDoubleClick={doubleSelect}
                />
              ) : (
                <circle
                  cx={dso.pixel_x}
                  cy={dso.pixel_y}
                  r={a}
                  fill="transparent"
                  stroke="transparent"
                  strokeWidth={hitWidth * unitsPerCssPixel}
                  pointerEvents="all"
                  onClick={select}
                  onDoubleClick={doubleSelect}
                />
              )}
              <text
                x={labelX}
                y={labelY}
                textAnchor={overflowRight ? "end" : "start"}
                fill={colors.label}
                fontSize={fontSize}
                fontWeight={isSelected || isMain ? 700 : 500}
                stroke="#000000"
                strokeWidth={textStroke}
                strokeLinejoin="round"
                paintOrder="stroke"
                onClick={select}
                onDoubleClick={doubleSelect}
              >
                {palette === "project"
                  ? `${dso.primary_designation}${dso.common_name ? ` · ${dso.common_name}` : ""}`
                  : (dso.common_name ?? dso.primary_designation)}
              </text>
            </g>
          );
        })}
    </Box>
  );
}

export default memo(DsoAnnotationOverlay);
