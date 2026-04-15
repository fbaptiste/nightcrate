import { useId } from "react";
import SvgIcon, { type SvgIconProps } from "@mui/material/SvgIcon";

interface MoonPhaseIconProps extends SvgIconProps {
  phaseName: string;
  illuminationPct?: number;
}

/**
 * Renders a moon phase using illumination percentage for accurate visuals.
 *
 * Uses a terminator ellipse approach: the lit/dark boundary is an ellipse
 * whose x-radius varies with illumination. At 0% (new moon) the moon is
 * fully dark; at 100% (full moon) it's fully lit.
 *
 * The phase name determines which side is lit:
 * - Waxing (new → full): right side lit, shadow on left
 * - Waning (full → new): left side lit, shadow on right
 */
export default function MoonPhaseIcon({
  phaseName,
  illuminationPct,
  ...svgProps
}: MoonPhaseIconProps) {
  const uid = useId();
  const clipId = `moon-clip-${uid}`;

  const illum = illuminationPct ?? 50;
  const name = phaseName.toLowerCase();

  // Determine which side is lit based on waxing vs waning
  const isWaxing =
    name.includes("new") ||
    name.includes("waxing") ||
    name === "first quarter";

  // Terminator ellipse rx: maps illumination to how far the terminator
  // is from center. At 50% illumination (quarter), rx=0 (straight line).
  // At 0% or 100%, rx=R (full circle).
  const R = 10; // moon radius
  // t goes from -1 (new, 0%) through 0 (quarter, 50%) to +1 (full, 100%)
  const t = (illum / 50) - 1; // -1 to +1
  const terminatorRx = Math.abs(t) * R;

  // For illumination < 50%, the terminator curves toward the lit side (less lit area).
  // For illumination > 50%, it curves toward the dark side (more lit area).
  // terminatorCx is always at center (12); the ellipse shape + dark rect combo creates the effect.

  // New moon: fully dark
  if (illum <= 1) {
    return (
      <SvgIcon viewBox="0 0 24 24" {...svgProps}>
        <circle cx={12} cy={12} r={R} fill="#2a2d32" />
      </SvgIcon>
    );
  }

  // Full moon: fully lit
  if (illum >= 99) {
    return (
      <SvgIcon viewBox="0 0 24 24" {...svgProps}>
        <circle cx={12} cy={12} r={R} fill="#c8ccd0" />
      </SvgIcon>
    );
  }

  // For waxing phases: right side is lit, left is dark
  // For waning phases: left side is lit, right is dark
  // Shadow side: "left" for waxing, "right" for waning
  const shadowSide = isWaxing ? "left" : "right";
  const shadowX = shadowSide === "left" ? 2 : 12;

  return (
    <SvgIcon viewBox="0 0 24 24" {...svgProps}>
      <defs>
        <clipPath id={clipId}>
          <circle cx={12} cy={12} r={R} />
        </clipPath>
      </defs>
      {/* Base: fully lit moon */}
      <circle cx={12} cy={12} r={R} fill="#c8ccd0" />
      {/* Shadow: cover the dark half */}
      <g clipPath={`url(#${clipId})`}>
        <rect x={shadowX} y={2} width={10} height={20} fill="#2a2d32" />
        {/* Terminator ellipse: either adds or removes shadow depending on phase */}
        {illum < 50 ? (
          // Less than half lit: terminator ellipse extends the shadow further
          // into the lit side. Shadow covers more than half.
          <ellipse cx={12} cy={12} rx={terminatorRx} ry={R} fill="#2a2d32" />
        ) : (
          // More than half lit: terminator ellipse carves light back out of
          // the shadow half. Shadow covers less than half.
          <ellipse cx={12} cy={12} rx={terminatorRx} ry={R} fill="#c8ccd0" />
        )}
      </g>
    </SvgIcon>
  );
}
