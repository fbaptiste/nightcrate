import { useSyncExternalStore } from "react";

/**
 * Page zoom in the installed app (the desktop shell). A browser has its own
 * zoom and its own indicator, so this does nothing there.
 *
 * Cmd (macOS) or Ctrl with +, - and 0 step through the same levels browsers
 * use. The level is remembered on this computer, and the sidebar shows it
 * whenever it isn't 100% (Fred, 2026-11-15: "it would be nice to see what the
 * zoom level is, and a way to reset it to 100%").
 */

export const ZOOM_STEPS = [0.5, 0.67, 0.75, 0.8, 0.9, 1, 1.1, 1.25, 1.5, 1.75, 2, 2.5, 3];
const STORAGE_KEY = "nightcrate.zoom";

/** The next step above (+1) or below (-1) `zoom`, clamped to the steps. */
export function nextZoom(zoom: number, direction: 1 | -1): number {
  if (direction > 0) {
    return ZOOM_STEPS.find((step) => step > zoom + 0.001) ?? ZOOM_STEPS[ZOOM_STEPS.length - 1];
  }
  return [...ZOOM_STEPS].reverse().find((step) => step < zoom - 0.001) ?? ZOOM_STEPS[0];
}

let current = 1;
const listeners = new Set<() => void>();

function shellInvoke(): ((command: string, args?: Record<string, unknown>) => Promise<unknown>) | null {
  const invoke = window.__TAURI__?.core?.invoke;
  return typeof invoke === "function" ? invoke : null;
}

function setZoom(zoom: number): void {
  const invoke = shellInvoke();
  if (!invoke) return;
  current = zoom;
  try {
    localStorage.setItem(STORAGE_KEY, String(zoom));
  } catch {
    // Remembering the level is a convenience; zooming still works.
  }
  void invoke("plugin:webview|set_webview_zoom", { value: zoom }).catch(() => undefined);
  listeners.forEach((listener) => listener());
}

export function resetZoom(): void {
  setZoom(1);
}

/** Start handling the zoom keys, and restore the remembered level. */
export function installDesktopZoom(): void {
  if (!shellInvoke()) return;
  let stored = 1;
  try {
    stored = Number(localStorage.getItem(STORAGE_KEY) ?? "1");
  } catch {
    stored = 1;
  }
  if (ZOOM_STEPS.includes(stored) && stored !== 1) setZoom(stored);

  const isMac = /Mac/i.test(navigator.platform);
  window.addEventListener("keydown", (event) => {
    if (!(isMac ? event.metaKey : event.ctrlKey) || event.altKey) return;
    if (event.key === "=" || event.key === "+") setZoom(nextZoom(current, 1));
    else if (event.key === "-" || event.key === "_") setZoom(nextZoom(current, -1));
    else if (event.key === "0") setZoom(1);
    else return;
    event.preventDefault();
  });
}

/** The current zoom level (1 = 100%), for the sidebar's indicator. */
export function useDesktopZoom(): number {
  return useSyncExternalStore(
    (listener) => {
      listeners.add(listener);
      return () => listeners.delete(listener);
    },
    () => current,
  );
}

export function resetZoomShortcut(): string {
  return /Mac/i.test(navigator.platform) ? "⌘0" : "Ctrl+0";
}
