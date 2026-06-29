/**
 * Polar alt-az "sky dome" for the planner detail panel (flat / top-down).
 *
 * A round disk seen as if looking straight up: the rim is the horizon, the
 * centre is the zenith. Compass direction is the angle around the rim (N up,
 * E right — correct in both hemispheres); altitude is how far in from the rim
 * a marker sits, labelled 90° (centre) → 0° (edge). The target (blue) and Moon
 * (orange) are plotted by BOTH azimuth and altitude, with their dashed paths
 * across the sky tonight. Pairs with the altitude-vs-time chart's scrubber.
 *
 * The dial encodes bearing + height, NOT true angular separation, so the
 * numeric Moon separation is always shown in the readout.
 */
import Box from "@mui/material/Box";
import { useTheme } from "@mui/material/styles";
import { RIG_BLUE, RIG_ORANGE } from "@/lib/rigColors";
import type { SkyDialSample, SkyPathPoint } from "./skyDial";
import SkyDialReadout from "./SkyDialReadout";

interface Props extends SkyDialSample {
  targetPath?: SkyPathPoint[];
  moonPath?: SkyPathPoint[];
  size?: number;
}

/** Project (azimuth, altitude) onto the disk. Below-horizon altitudes clamp
 *  to the rim. N is up, E is right. */
function project(azDeg: number, altDeg: number, cx: number, cy: number, R: number) {
  const alt = Math.max(0, Math.min(90, altDeg));
  const r = ((90 - alt) / 90) * R;
  const a = (azDeg * Math.PI) / 180;
  return { x: cx + r * Math.sin(a), y: cy - r * Math.cos(a) };
}

export default function SkyDomeChart({
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
  const isDark = theme.palette.mode === "dark";
  const ringColor = isDark ? "rgba(255, 255, 255, 0.26)" : "rgba(0, 0, 0, 0.22)";
  const rimColor = isDark ? "rgba(255, 255, 255, 0.45)" : "rgba(0, 0, 0, 0.40)";
  const labelColor = theme.palette.text.secondary;

  const cx = size / 2;
  const cy = size / 2;
  const R = size / 2 - 18; // leave room for cardinal labels

  const targetUp = targetAlt > 0;
  const moonUp = moonAlt > 0;
  const tp = project(targetAz, targetAlt, cx, cy, R);
  const mp = project(moonAz, moonAlt, cx, cy, R);
  const moonOpacity = (moonUp ? 1 : 0.35) * (0.35 + 0.65 * (moonIllumPct / 100));

  // Above-horizon path runs → dashed polylines.
  function pathRuns(path: SkyPathPoint[] | undefined): string[] {
    if (!path || path.length < 2) return [];
    const runs: string[] = [];
    let run: SkyPathPoint[] = [];
    const flush = () => {
      if (run.length >= 2) {
        runs.push(
          "M" +
            run
              .map((p) => {
                const s = project(p.az, p.alt, cx, cy, R);
                return `${s.x.toFixed(1)} ${s.y.toFixed(1)}`;
              })
              .join("L"),
        );
      }
      run = [];
    };
    for (const p of path) {
      if (p.alt > 0) run.push(p);
      else flush();
    }
    flush();
    return runs;
  }
  const targetRuns = pathRuns(targetPath);
  const moonRuns = pathRuns(moonPath);

  const cardinals = [
    { label: "N", az: 0 },
    { label: "E", az: 90 },
    { label: "S", az: 180 },
    { label: "W", az: 270 },
  ];
  // Altitude rings + their labels (90° centre → 0° edge).
  const altRings = [0, 30, 60];

  return (
    <Box sx={{ display: "flex", alignItems: "center", gap: 3, flexWrap: "wrap" }}>
      <svg width={size} height={size} style={{ display: "block", flexShrink: 0 }}>
        {/* Altitude rings. */}
        {altRings.map((alt) => (
          <circle
            key={alt}
            cx={cx}
            cy={cy}
            r={((90 - alt) / 90) * R}
            fill={alt === 0 ? theme.palette.action.hover : "none"}
            fillOpacity={alt === 0 ? 0.4 : 1}
            stroke={alt === 0 ? rimColor : ringColor}
            strokeWidth={alt === 0 ? 1.25 : 0.75}
          />
        ))}
        {/* Cardinal cross-hairs. */}
        <line x1={cx} y1={cy - R} x2={cx} y2={cy + R} stroke={ringColor} strokeWidth={0.5} />
        <line x1={cx - R} y1={cy} x2={cx + R} y2={cy} stroke={ringColor} strokeWidth={0.5} />

        {/* Altitude labels along the upper vertical (90° centre → 0° edge),
            nudged left of the cross-hair and up off each ring line. */}
        {[90, 60, 30, 0].map((alt) => (
          <text
            key={`alt${alt}`}
            x={cx - 5}
            y={cy - ((90 - alt) / 90) * R - 4}
            fill={labelColor}
            fontSize={8.5}
            textAnchor="end"
            dominantBaseline="central"
          >
            {alt}°
          </text>
        ))}

        {/* Cardinal labels just outside the rim. */}
        {cardinals.map((c) => {
          const a = (c.az * Math.PI) / 180;
          return (
            <text
              key={c.label}
              x={cx + (R + 10) * Math.sin(a)}
              y={cy - (R + 10) * Math.cos(a)}
              fill={labelColor}
              fontSize={11}
              fontWeight={600}
              textAnchor="middle"
              dominantBaseline="central"
            >
              {c.label}
            </text>
          );
        })}

        {/* Body paths across the sky (dotted). */}
        {moonRuns.map((d, i) => (
          <path key={`mp${i}`} d={d} fill="none" stroke={RIG_ORANGE} strokeOpacity={0.75} strokeWidth={1.5} strokeDasharray="1,3.5" strokeLinecap="round" />
        ))}
        {targetRuns.map((d, i) => (
          <path key={`tp${i}`} d={d} fill="none" stroke={RIG_BLUE} strokeOpacity={0.8} strokeWidth={1.5} strokeDasharray="1,3.5" strokeLinecap="round" />
        ))}

        {/* Moon marker (drawn first so the target sits on top if they overlap). */}
        <circle
          cx={mp.x}
          cy={mp.y}
          r={6}
          fill={RIG_ORANGE}
          fillOpacity={moonOpacity}
          stroke={RIG_ORANGE}
          strokeOpacity={moonUp ? 1 : 0.4}
          strokeWidth={1.5}
          strokeDasharray={moonUp ? undefined : "2,2"}
        />
        {/* Target marker. */}
        <circle
          cx={tp.x}
          cy={tp.y}
          r={5}
          fill={RIG_BLUE}
          fillOpacity={targetUp ? 1 : 0.35}
          stroke={theme.palette.background.paper}
          strokeWidth={1.5}
        />
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
