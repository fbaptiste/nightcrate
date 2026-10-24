import { useEffect, useState } from "react";

/** A browser clock that also updates immediately when the page becomes active. */
export function useNow(intervalMs: number): number {
  const [now, setNow] = useState(() => Date.now());

  useEffect(() => {
    const update = () => setNow(Date.now());
    const onVisibilityChange = () => {
      if (document.visibilityState === "visible") update();
    };
    const interval = window.setInterval(update, intervalMs);
    window.addEventListener("focus", update);
    document.addEventListener("visibilitychange", onVisibilityChange);
    return () => {
      window.clearInterval(interval);
      window.removeEventListener("focus", update);
      document.removeEventListener("visibilitychange", onVisibilityChange);
    };
  }, [intervalMs]);

  return now;
}
