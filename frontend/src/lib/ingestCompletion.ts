export type IngestCompletionAction = "observe" | "show" | "dismiss" | "none";

interface IngestCompletionState {
  running: boolean;
  handled: boolean;
  observed: boolean;
  startPending: boolean;
  startedHere: boolean;
}

/** Decide how this browser tab should treat a polled ingest record. */
export function ingestCompletionAction({
  running,
  handled,
  observed,
  startPending,
  startedHere,
}: IngestCompletionState): IngestCompletionAction {
  if (handled) return "none";
  if (running) return "observe";
  if (observed || startedHere) return "show";
  return startPending ? "none" : "dismiss";
}
