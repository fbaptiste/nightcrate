/**
 * Oblique "3-D" sky dome for the planner detail panel.
 *
 * Rendered like a classic celestial-dome diagram: a vibrant translucent cyan
 * glass hemisphere over a solid tan ground plane, on its own near-black
 * backdrop so the colours pop and the white compass labels stay legible (the
 * panel's grey background washes everything out, so the dome carries its own
 * dark "card"). Bold bright horizon/equator; a faint alt-az grid for reading
 * azimuth/altitude. The target (blue) and Moon (orange) sit on the dome with
 * their dotted paths and an azimuth meridian down to the horizon. The view is
 * tilted back and rotated a few degrees so it reads as a 3-D object.
 */
import Box from "@mui/material/Box";
import { alpha, useTheme } from "@mui/material/styles";
import { RIG_BLUE, RIG_ORANGE } from "@/lib/rigColors";
import type { SkyDialSample, SkyPathPoint } from "./skyDial";
import SkyDialReadout from "./SkyDialReadout";

interface Props extends SkyDialSample {
  targetPath?: SkyPathPoint[];
  moonPath?: SkyPathPoint[];
  size?: number;
}

const PHI = (22 * Math.PI) / 180; // low camera elevation — shallow floor, tall dome arc
const SIN_PHI = Math.sin(PHI);
const COS_PHI = Math.cos(PHI);
const DEG = Math.PI / 180;
const AZ_OFFSET = 16; // rotate the view so South isn't dead-centre
const GRAD_ID = "sky-dome-3d-grad";
const FLOOR_ID = "sky-dome-3d-floor";
const BACKRIM_ID = "sky-dome-3d-backrim";
const FRONTRIM_ID = "sky-dome-3d-frontrim";

// The 3-D dome is a deliberately theme-independent illustration: a fixed
// night-sky scene that reads identically in light and dark mode (a light
// backdrop would wash out the translucent glass). Its scene colours are
// centralised named constants here — the same fixed-palette approach as
// lib/rigColors.ts — rather than MUI theme tokens. Universal neutrals
// (white labels/glints, black outlines) DO come from the theme, in-component.
const BACKDROP = "#0a0e16"; // near-black card the dome sits on
const EQUATOR = "rgb(150, 232, 250)"; // bright cyan horizon/rim line
const GRID = "rgba(205, 242, 252, 0.32)"; // pale-cyan alt-az grid on the glass

export default function SkyDome3DChart({
  targetAz,
  targetAlt,
  moonAz,
  moonAlt,
  moonIllumPct,
  separationDeg,
  targetPath,
  moonPath,
  size = 220,
}: Props) {
  const theme = useTheme();
  // Universal neutrals from the theme (the scene palette above is fixed).
  const white = theme.palette.common.white;
  const axisColor = alpha(theme.palette.common.black, 0.72); // axes on the floor
  const outline = (o: number) => alpha(theme.palette.common.black, o); // bead/dot edges

  const pad = 26; // room around the dome for the labels on the backdrop
  const R = size / 2 - pad;
  const cx = size / 2;
  const cy = pad + R; // dome top (the limb) sits ``pad`` from the top
  const ry = SIN_PHI * R;
  const H = Math.round(R * (1 + SIN_PHI) + 2 * pad);

  function proj(azDeg: number, altDeg: number): { x: number; y: number } {
    const A = (azDeg + AZ_OFFSET) * DEG;
    const h = Math.max(0, altDeg) * DEG;
    const ch = Math.cos(h);
    return {
      x: cx + ch * Math.sin(A) * R,
      y: cy - (ch * Math.cos(A) * SIN_PHI + Math.sin(h) * COS_PHI) * R,
    };
  }
  const coordOf = (p: SkyPathPoint) => {
    const s = proj(p.az, p.alt);
    return `${s.x.toFixed(1)} ${s.y.toFixed(1)}`;
  };

  // Camera-facing (visible) half of the dome — for hidden-line removal.
  function isNear(azDeg: number, altDeg: number): boolean {
    const A = (azDeg + AZ_OFFSET) * DEG;
    const h = Math.max(0, altDeg) * DEG;
    return Math.cos(h) * Math.cos(A) * COS_PHI - Math.sin(h) * SIN_PHI < 0;
  }
  function nearArcs(points: SkyPathPoint[]): string[] {
    const out: string[] = [];
    let seg: string[] = [];
    const flush = () => {
      if (seg.length >= 2) out.push("M" + seg.join("L"));
      seg = [];
    };
    for (const p of points) {
      if (isNear(p.az, p.alt)) seg.push(coordOf(p));
      else flush();
    }
    flush();
    return out;
  }
  function splitNearFar(points: SkyPathPoint[]): { near: string[]; far: string[] } {
    const near: string[] = [];
    const far: string[] = [];
    let seg: string[] = [];
    let segNear: boolean | null = null;
    const flush = () => {
      if (seg.length >= 2) (segNear ? near : far).push("M" + seg.join("L"));
      seg = [];
    };
    for (const p of points) {
      const n = isNear(p.az, p.alt);
      const c = coordOf(p);
      if (segNear !== null && n !== segNear) {
        seg.push(c);
        flush();
      }
      seg.push(c);
      segNear = n;
    }
    flush();
    return { near, far };
  }
  function bodyMeridian(az: number, alt: number): { near: string[]; far: string[] } {
    if (alt <= 0) return { near: [], far: [] };
    const pts: SkyPathPoint[] = [];
    for (let h = 0; h <= alt + 1e-6; h += 2) pts.push({ az, alt: h });
    return splitNearFar(pts);
  }

  // Body path → dots on the dome, ~4 px apart, depth-shaded (near bright, far
  // faint) so the trail reads as wrapping the surface.
  function pathDots(path: SkyPathPoint[] | undefined): Array<{ x: number; y: number; op: number }> {
    const out: Array<{ x: number; y: number; op: number }> = [];
    let last: { x: number; y: number } | null = null;
    for (const p of path ?? []) {
      if (p.alt <= 0) {
        last = null;
        continue;
      }
      const s = proj(p.az, p.alt);
      if (last && Math.hypot(s.x - last.x, s.y - last.y) < 3.6) continue;
      last = s;
      const A = (p.az + AZ_OFFSET) * DEG; // match proj()/isNear() — same rotation
      const h = p.alt * DEG;
      const depth = Math.cos(h) * Math.cos(A) * COS_PHI - Math.sin(h) * SIN_PHI;
      out.push({ x: s.x, y: s.y, op: Math.max(0.62, Math.min(1, 0.86 - 0.26 * depth)) });
    }
    out.sort((a, b) => a.op - b.op);
    return out;
  }

  // Geometry (az-independent, so the rotation can't break it):
  // limb = top semicircle radius R; front/back horizon = halves of the ellipse.
  let limb = "";
  for (let d = 180; d <= 360; d += 3) {
    const t = d * DEG;
    limb += (limb === "" ? "M" : "L") + `${(cx + R * Math.cos(t)).toFixed(1)} ${(cy + R * Math.sin(t)).toFixed(1)} `;
  }
  limb = limb.trim();
  let frontHorizon = "";
  for (let d = 0; d <= 180; d += 3) {
    const t = d * DEG;
    frontHorizon += (frontHorizon === "" ? "M" : "L") + `${(cx + R * Math.cos(t)).toFixed(1)} ${(cy + ry * Math.sin(t)).toFixed(1)} `;
  }
  frontHorizon = frontHorizon.trim();
  let backHorizon = "";
  for (let d = 180; d <= 360; d += 4) {
    const t = d * DEG;
    backHorizon += (backHorizon === "" ? "M" : "L") + `${(cx + R * Math.cos(t)).toFixed(1)} ${(cy + ry * Math.sin(t)).toFixed(1)} `;
  }
  backHorizon = backHorizon.trim();
  const silhouette = `${limb} L${frontHorizon.slice(1)} Z`; // limb + front horizon, closed

  const fN = proj(0, 0);
  const fS = proj(180, 0);
  const fE = proj(90, 0);
  const fW = proj(270, 0);

  // Faint alt-az grid (front half only): 45° meridians + one high ring.
  const gridMeridians = [0, 45, 90, 135, 180, 225, 270, 315].flatMap((az) => {
    const pts: SkyPathPoint[] = [];
    for (let h = 0; h <= 90 + 1e-6; h += 3) pts.push({ az, alt: h });
    return nearArcs(pts);
  });
  const gridRings = [60].flatMap((alt) => {
    const pts: SkyPathPoint[] = [];
    for (let a = 0; a <= 360 + 1e-6; a += 3) pts.push({ az: a, alt });
    return nearArcs(pts);
  });

  const tMer = bodyMeridian(targetAz, targetAlt);
  const mMer = bodyMeridian(moonAz, moonAlt);
  const tFoot = proj(targetAz, 0);
  const mFoot = proj(moonAz, 0);
  const tDots = pathDots(targetPath);
  const mDots = pathDots(moonPath);

  const targetUp = targetAlt > 0;
  const moonUp = moonAlt > 0;
  const tPos = proj(targetAz, targetAlt);
  const mPos = proj(moonAz, moonAlt);
  const moonOpacity = (moonUp ? 1 : 0.4) * (0.5 + 0.5 * (moonIllumPct / 100));

  const compass: Array<{ label: string; az: number; major: boolean }> = [
    { label: "N", az: 0, major: true },
    { label: "NE", az: 45, major: false },
    { label: "E", az: 90, major: true },
    { label: "SE", az: 135, major: false },
    { label: "S", az: 180, major: true },
    { label: "SW", az: 225, major: false },
    { label: "W", az: 270, major: true },
    { label: "NW", az: 315, major: false },
  ];
  const labelHalo = { paintOrder: "stroke" as const };

  return (
    <Box sx={{ display: "flex", alignItems: "center", gap: 3, flexWrap: "wrap" }}>
      <svg width={size} height={H} style={{ display: "block", flexShrink: 0 }}>
        <defs>
          {/* Vibrant cyan glass: bright lit highlight upper-left → deep teal,
              translucent at the rim so the ground shows through. */}
          <radialGradient id={GRAD_ID} cx="33%" cy="13%" r="98%">
            <stop offset="0%" stopColor="rgb(176, 240, 252)" stopOpacity={0.92} />
            <stop offset="42%" stopColor="rgb(54, 186, 222)" stopOpacity={0.76} />
            <stop offset="76%" stopColor="rgb(24, 120, 166)" stopOpacity={0.64} />
            <stop offset="100%" stopColor="rgb(14, 66, 104)" stopOpacity={0.46} />
          </radialGradient>
          {/* Solid tan ground: brighter at the near edge, darker at the back. */}
          <linearGradient id={FLOOR_ID} gradientUnits="userSpaceOnUse" x1={cx} y1={cy - ry} x2={cx} y2={cy + ry}>
            <stop offset="0%" stopColor="rgb(64, 56, 38)" stopOpacity={1} />
            <stop offset="100%" stopColor="rgb(168, 150, 104)" stopOpacity={1} />
          </linearGradient>
          {/* Equator fades toward the E/W ends where front meets back, so the
              two halves taper into each other instead of butting hard. */}
          <linearGradient id={BACKRIM_ID} gradientUnits="userSpaceOnUse" x1={cx - R} y1={cy} x2={cx + R} y2={cy}>
            <stop offset="0%" stopColor={EQUATOR} stopOpacity={0.08} />
            <stop offset="50%" stopColor={EQUATOR} stopOpacity={0.55} />
            <stop offset="100%" stopColor={EQUATOR} stopOpacity={0.08} />
          </linearGradient>
          <linearGradient id={FRONTRIM_ID} gradientUnits="userSpaceOnUse" x1={cx - R} y1={cy} x2={cx + R} y2={cy}>
            <stop offset="0%" stopColor={EQUATOR} stopOpacity={0.12} />
            <stop offset="20%" stopColor={EQUATOR} stopOpacity={0.85} />
            <stop offset="80%" stopColor={EQUATOR} stopOpacity={0.85} />
            <stop offset="100%" stopColor={EQUATOR} stopOpacity={0.12} />
          </linearGradient>
        </defs>

        {/* Dark backdrop card — makes the vibrant fills + white labels pop. */}
        <rect x={0} y={0} width={size} height={H} rx={12} fill={BACKDROP} />

        {/* Ground plane + base cross-axes. */}
        <ellipse cx={cx} cy={cy} rx={R} ry={ry} fill={`url(#${FLOOR_ID})`} />
        <line x1={fN.x} y1={fN.y} x2={fS.x} y2={fS.y} stroke={axisColor} strokeWidth={1} />
        <line x1={fE.x} y1={fE.y} x2={fW.x} y2={fW.y} stroke={axisColor} strokeWidth={1} />

        {/* Back equator (behind the glass, dashed, fading). */}
        <path d={backHorizon} fill="none" stroke={`url(#${BACKRIM_ID})`} strokeWidth={1.4} strokeDasharray="3,3" />

        {/* Glass dome shell. */}
        <path d={silhouette} fill={`url(#${GRAD_ID})`} stroke="none" />

        {/* Faint alt-az grid on the front of the shell. */}
        {gridMeridians.map((d, i) => (
          <path key={`gm${i}`} d={d} fill="none" stroke={GRID} strokeWidth={0.7} />
        ))}
        {gridRings.map((d, i) => (
          <path key={`gr${i}`} d={d} fill="none" stroke={GRID} strokeWidth={0.7} />
        ))}

        {/* Dome glass edge (limb) + bold bright front equator. */}
        <path d={limb} fill="none" stroke={EQUATOR} strokeOpacity={0.55} strokeWidth={1.25} />
        <path d={frontHorizon} fill="none" stroke={`url(#${FRONTRIM_ID})`} strokeWidth={1.6} strokeLinecap="round" />

        {/* Each body's azimuth meridian + a tick at its compass point. */}
        {mMer.far.map((d, i) => (
          <path key={`mmf${i}`} d={d} fill="none" stroke={RIG_ORANGE} strokeOpacity={0.35} strokeWidth={1.5} strokeLinecap="round" />
        ))}
        {mMer.near.map((d, i) => (
          <path key={`mmn${i}`} d={d} fill="none" stroke={RIG_ORANGE} strokeOpacity={0.9} strokeWidth={2} strokeLinecap="round" />
        ))}
        {moonUp && <circle cx={mFoot.x} cy={mFoot.y} r={2.8} fill={RIG_ORANGE} stroke={outline(0.5)} strokeWidth={0.6} />}
        {tMer.far.map((d, i) => (
          <path key={`tmf${i}`} d={d} fill="none" stroke={RIG_BLUE} strokeOpacity={0.4} strokeWidth={1.5} strokeLinecap="round" />
        ))}
        {tMer.near.map((d, i) => (
          <path key={`tmn${i}`} d={d} fill="none" stroke={RIG_BLUE} strokeOpacity={0.95} strokeWidth={2} strokeLinecap="round" />
        ))}
        {targetUp && <circle cx={tFoot.x} cy={tFoot.y} r={2.8} fill={RIG_BLUE} stroke={outline(0.55)} strokeWidth={0.6} />}

        {/* Body path dots — bold, dark-outlined so they read on the glass. */}
        {mDots.map((d, i) => (
          <circle key={`md${i}`} cx={d.x} cy={d.y} r={2.4} fill={RIG_ORANGE} fillOpacity={d.op} stroke={outline(0.5)} strokeWidth={0.6} />
        ))}
        {tDots.map((d, i) => (
          <circle key={`td${i}`} cx={d.x} cy={d.y} r={2.4} fill={RIG_BLUE} fillOpacity={d.op} stroke={outline(0.6)} strokeWidth={0.6} />
        ))}

        {/* Moon marker (drawn first so the target wins on overlap). */}
        <g opacity={moonUp ? 1 : 0.45}>
          <circle cx={mPos.x} cy={mPos.y} r={6.5} fill={RIG_ORANGE} fillOpacity={moonOpacity} stroke={outline(0.6)} strokeWidth={1.25} strokeDasharray={moonUp ? undefined : "2,2"} />
          {moonUp && <circle cx={mPos.x - 2} cy={mPos.y - 2} r={1.8} fill={white} fillOpacity={0.6} />}
        </g>
        {/* Target marker. */}
        <g opacity={targetUp ? 1 : 0.5}>
          <circle cx={tPos.x} cy={tPos.y} r={5.5} fill={RIG_BLUE} stroke={outline(0.65)} strokeWidth={1.5} />
          {targetUp && <circle cx={tPos.x - 1.6} cy={tPos.y - 1.6} r={1.6} fill={white} fillOpacity={0.7} />}
        </g>

        {/* Compass labels — white with a dark halo, just outside the rim. */}
        {compass.map((c) => {
          const f = proj(c.az, 0);
          const dx = f.x - cx;
          const dy = f.y - cy;
          const len = Math.hypot(dx, dy) || 1;
          const off = c.major ? 15 : 13;
          return (
            <text
              key={c.label}
              x={f.x + (dx / len) * off}
              y={f.y + (dy / len) * off}
              fill={white}
              fillOpacity={c.major ? 1 : 0.8}
              stroke={BACKDROP}
              strokeWidth={c.major ? 2.6 : 2.2}
              strokeLinejoin="round"
              style={labelHalo}
              fontSize={c.major ? 12 : 9}
              fontWeight={c.major ? 700 : 500}
              textAnchor="middle"
              dominantBaseline="central"
            >
              {c.label}
            </text>
          );
        })}
      </svg>

      <SkyDialReadout
        targetAz={targetAz}
        targetAlt={targetAlt}
        moonAz={moonAz}
        moonAlt={moonAlt}
        moonIllumPct={moonIllumPct}
        separationDeg={separationDeg}
      />
    </Box>
  );
}
