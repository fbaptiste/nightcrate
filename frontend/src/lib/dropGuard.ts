/**
 * Swallow native drag-and-drop drops that no part of the page handles.
 *
 * NightCrate's reordering (sidebar, gallery, planner) uses dnd-kit's pointer
 * events, not native drops, and nothing accepts dropped files. Left alone, the
 * installed app's web view treats a dropped link as "go there": dropping a
 * sidebar item reloaded the whole app on that page, with a white flash
 * (v0.54.0 Mac check). A browser tab can do the same with a dropped file.
 *
 * A handler that does accept a drop calls `preventDefault()` itself, before
 * the event reaches the window, so this guard leaves it alone.
 */
export function installDropGuard(target: Window = window): () => void {
  // Accept the drag here and ignore the drop below. Declining it (drop effect
  // "none") is not enough: WebKit then falls back to loading a dropped link
  // itself, which is the reload this guard exists to stop.
  const refuseDragOver = (event: DragEvent) => {
    if (!event.defaultPrevented) event.preventDefault();
  };
  const refuseDrop = (event: DragEvent) => {
    if (!event.defaultPrevented) event.preventDefault();
  };
  target.addEventListener("dragover", refuseDragOver);
  target.addEventListener("drop", refuseDrop);
  return () => {
    target.removeEventListener("dragover", refuseDragOver);
    target.removeEventListener("drop", refuseDrop);
  };
}
