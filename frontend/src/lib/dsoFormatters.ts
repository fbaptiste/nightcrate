/**
 * Coordinate and size formatters specific to DSO rendering.
 */

function pad2(n: number): string {
  return n < 10 ? `0${n}` : String(n);
}

export function formatRa(deg: number | null): string {
  if (deg == null) return "—";
  const hours = deg / 15;
  const h = Math.floor(hours);
  const minF = (hours - h) * 60;
  const m = Math.floor(minF);
  const s = (minF - m) * 60;
  return `${pad2(h)}h ${pad2(m)}m ${s.toFixed(1).padStart(4, "0")}s`;
}

export function formatDec(deg: number | null): string {
  if (deg == null) return "—";
  const sign = deg < 0 ? "-" : "+";
  const abs = Math.abs(deg);
  const d = Math.floor(abs);
  const minF = (abs - d) * 60;
  const m = Math.floor(minF);
  const s = Math.round((minF - m) * 60);
  return `${sign}${pad2(d)}\u00B0 ${pad2(m)}\u2032 ${pad2(s)}\u2033`;
}

export function formatSize(
  majAxis: number | null,
  minAxis: number | null,
): string {
  if (majAxis == null) return "—";
  const maj = majAxis >= 60 ? `${(majAxis / 60).toFixed(1)}°` : `${majAxis.toFixed(1)}'`;
  if (minAxis == null) return maj;
  const min =
    minAxis >= 60 ? `${(minAxis / 60).toFixed(1)}°` : `${minAxis.toFixed(1)}'`;
  return `${maj} × ${min}`;
}

export function formatMagnitude(mag: number | null, digits = 1): string {
  if (mag == null) return "—";
  return mag.toFixed(digits);
}
