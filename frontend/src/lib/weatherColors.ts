/**
 * Score-to-color mapping for imaging quality scores.
 * Sequential blue palette: darker = better (good imaging = dark sky).
 */

export function scoreToBackground(score: number): string {
  const clamped = Math.max(0, Math.min(100, score));
  const saturation = 15 + (clamped / 100) * 50;
  const lightness = 75 - (clamped / 100) * 57;
  return `hsl(215, ${saturation.toFixed(1)}%, ${lightness.toFixed(1)}%)`;
}

export function scoreToTextColor(score: number): string {
  return score >= 45 ? "#e2e0dd" : "#1a1c20";
}

export function scoreToLabel(score: number): string {
  if (score >= 80) return "Excellent";
  if (score >= 55) return "Good";
  if (score >= 30) return "Marginal";
  return "Poor";
}
