import { useEffect, useState, type RefObject } from "react";

export type TileView = "small" | "medium" | "large";

export const tileMinimums: Record<TileView, number> = {
  small: 180,
  medium: 300,
  large: 480,
};

export function useTrackWidth(view: TileView, ref: RefObject<HTMLElement | null>): number {
  const [trackWidth, setTrackWidth] = useState(tileMinimums[view]);

  useEffect(() => {
    const element = ref.current;
    if (!element) return;
    const update = () => {
      const width = element.clientWidth;
      const minimum = tileMinimums[view];
      const columns = Math.max(1, Math.floor((width + 16) / (minimum + 16)));
      setTrackWidth((width - 16 * (columns - 1)) / columns);
    };
    update();
    const observer = new ResizeObserver(update);
    observer.observe(element);
    return () => observer.disconnect();
  }, [ref, view]);

  return trackWidth;
}
