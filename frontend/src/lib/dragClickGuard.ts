/**
 * Cancel the click that ends a drag of a sortable item that is a link.
 *
 * Once a drag starts, dnd-kit's pointer sensor adds a document listener that
 * stops click propagation, and removes it 50 ms after release; it never
 * cancels the click. React Router's link handler, which would cancel it and
 * route in-app, never runs, so the browser follows the link itself: a full
 * page load. In the installed Mac app every sidebar drop reloaded the app
 * with a white flash (v0.54.0 Mac check; diagnosed by Codex). This listener
 * runs alongside dnd-kit's (stopPropagation doesn't stop other listeners on
 * the same node) for a slightly longer window.
 */
export function createDragClickGuard(target: Document = document) {
  let cancel: ((event: Event) => void) | null = null;
  return {
    start(): void {
      if (cancel) return;
      cancel = (event: Event) => event.preventDefault();
      target.addEventListener("click", cancel, true);
    },
    stop(): void {
      const listener = cancel;
      cancel = null;
      if (listener) {
        window.setTimeout(() => target.removeEventListener("click", listener, true), 60);
      }
    },
  };
}
