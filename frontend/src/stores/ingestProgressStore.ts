import { create } from "zustand";

const STORAGE_KEY = "nightcrate-handled-ingest-scans";

function readHandledScanIds(): Set<string> {
  try {
    if (typeof window === "undefined") return new Set();
    const stored = JSON.parse(window.sessionStorage.getItem(STORAGE_KEY) ?? "[]");
    return new Set(
      Array.isArray(stored)
        ? stored.filter((value): value is string => typeof value === "string")
        : [],
    );
  } catch {
    return new Set();
  }
}

function writeHandledScanIds(ids: ReadonlySet<string>): void {
  try {
    if (typeof window === "undefined") return;
    window.sessionStorage.setItem(STORAGE_KEY, JSON.stringify([...ids]));
  } catch {
    // Browsers may disable storage. The in-memory set still prevents repeats
    // while this window remains open.
  }
}

interface IngestProgressState {
  handledScanIds: ReadonlySet<string>;
  markHandled: (scanId: string) => void;
}

export const useIngestProgressStore = create<IngestProgressState>((set) => ({
  handledScanIds: readHandledScanIds(),
  markHandled: (scanId) =>
    set((state) => {
      if (state.handledScanIds.has(scanId)) return state;
      const handledScanIds = new Set(state.handledScanIds);
      handledScanIds.add(scanId);
      writeHandledScanIds(handledScanIds);
      return { handledScanIds };
    }),
}));
