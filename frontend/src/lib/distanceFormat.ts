/**
 * Distance display helpers.
 *
 * Backend stores distances in parsecs (astronomy-canonical). The UI
 * auto-scales to pc / kpc / Mpc and ships both parsec and light-year
 * representations so beginner astronomers have something intuitive.
 */

const PC_TO_LY = 3.26156;

export interface FormattedDistance {
  primary: string; // compact, e.g., "1.25 kpc" — used in the grid column
  secondary: string; // matching ly, e.g., "4.08 kly" — used in the detail panel
  compact: string; // "1.25 kpc (4.08 kly)" — one-line combined form
}

/** Round to 3 significant figures. Always returns a number. */
function toThreeSigFigs(value: number): number {
  if (value === 0) return 0;
  const sign = Math.sign(value);
  const abs = Math.abs(value);
  const magnitude = Math.floor(Math.log10(abs));
  const factor = Math.pow(10, 2 - magnitude);
  return sign * Math.round(abs * factor) / factor;
}

function formatScaled(
  value: number,
  unitPc: "pc" | "kpc" | "Mpc",
  unitLy: "ly" | "kly" | "Mly",
): FormattedDistance {
  const pcValue = unitPc === "pc" ? value : unitPc === "kpc" ? value * 1000 : value * 1_000_000;
  const lyValue = pcValue * PC_TO_LY;
  const lyScaled =
    unitLy === "ly" ? lyValue : unitLy === "kly" ? lyValue / 1000 : lyValue / 1_000_000;

  const pcPrimary = `${toThreeSigFigs(value)} ${unitPc}`;
  const lySecondary = `${toThreeSigFigs(lyScaled)} ${unitLy}`;
  return {
    primary: pcPrimary,
    secondary: lySecondary,
    compact: `${pcPrimary} (${lySecondary})`,
  };
}

export function formatDistance(
  distancePc: number | null | undefined,
): FormattedDistance | null {
  if (distancePc == null) return null;
  if (distancePc < 1000) {
    return formatScaled(distancePc, "pc", "ly");
  }
  if (distancePc < 1_000_000) {
    return formatScaled(distancePc / 1000, "kpc", "kly");
  }
  return formatScaled(distancePc / 1_000_000, "Mpc", "Mly");
}

export function formatDistanceMethod(
  method: "50mgc" | "curated" | "redshift" | null | undefined,
): string {
  switch (method) {
    case "50mgc":
      return "50 MGC (Ohlson+ 2024)";
    case "curated":
      return "Curated (NightCrate)";
    case "redshift":
      return "Redshift-derived";
    default:
      return "";
  }
}
