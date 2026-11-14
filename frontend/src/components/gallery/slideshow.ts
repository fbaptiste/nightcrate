import type { SlideshowSeconds } from "@/api/settings";

export const SLIDESHOW_STEPS: readonly SlideshowSeconds[] = [
  2, 3, 4, 5, 6, 8, 10, 15, 20, 30,
];

export const DEFAULT_SLIDESHOW_SECONDS: SlideshowSeconds = 5;

export function stepInterval(
  current: SlideshowSeconds,
  delta: 1 | -1,
): { seconds: SlideshowSeconds; atEnd: boolean } {
  const index = SLIDESHOW_STEPS.indexOf(current);
  const nextIndex = Math.max(0, Math.min(SLIDESHOW_STEPS.length - 1, index + delta));
  return {
    seconds: SLIDESHOW_STEPS[nextIndex],
    atEnd: nextIndex === index,
  };
}

export function intervalNote(
  seconds: SlideshowSeconds,
  atEnd: boolean,
  delta: 1 | -1,
): string {
  const end = atEnd ? ` (${delta < 0 ? "shortest" : "longest"})` : "";
  return `${seconds} s per picture${end}`;
}

export function nextIndex(
  index: number,
  delta: 1 | -1,
  length: number,
  playing: boolean,
): number | null {
  if (length <= 0 || index < 0 || index >= length) return null;
  const next = index + delta;
  if (next >= 0 && next < length) return next;
  if (!playing) return null;
  return (next + length) % length;
}
