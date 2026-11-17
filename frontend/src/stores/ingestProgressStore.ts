import { create } from "zustand";

const STORAGE_KEY = "nightcrate-handled-ingest-scans";

interface StoredScanIds {
  handled: string[];
  observed: string[];
}

function stringIds(value: unknown): string[] {
  return Array.isArray(value)
    ? value.filter((item): item is string => typeof item === "string")
    : [];
}

function readScanIds(): { handledScanIds: Set<string>; observedScanIds: Set<string> } {
  try {
    if (typeof window === "undefined") {
      return { handledScanIds: new Set(), observedScanIds: new Set() };
    }
    const stored = JSON.parse(window.sessionStorage.getItem(STORAGE_KEY) ?? "[]");
    if (Array.isArray(stored)) {
      return { handledScanIds: new Set(stringIds(stored)), observedScanIds: new Set() };
    }
    return {
      handledScanIds: new Set(stringIds(stored?.handled)),
      observedScanIds: new Set(stringIds(stored?.observed)),
    };
  } catch {
    return { handledScanIds: new Set(), observedScanIds: new Set() };
  }
}

function writeScanIds(handled: ReadonlySet<string>, observed: ReadonlySet<string>): void {
  try {
    if (typeof window === "undefined") return;
    const stored: StoredScanIds = {
      handled: [...handled],
      observed: [...observed],
    };
    window.sessionStorage.setItem(STORAGE_KEY, JSON.stringify(stored));
  } catch {
    // Browsers may disable storage. The in-memory set still prevents repeats
    // while this window remains open.
  }
}

interface IngestProgressState {
  handledScanIds: ReadonlySet<string>;
  observedScanIds: ReadonlySet<string>;
  markHandled: (scanId: string) => void;
  markObserved: (scanId: string) => void;
}

const initialScanIds = readScanIds();

export const useIngestProgressStore = create<IngestProgressState>((set) => ({
  ...initialScanIds,
  markHandled: (scanId) =>
    set((state) => {
      if (state.handledScanIds.has(scanId)) return state;
      const handledScanIds = new Set(state.handledScanIds);
      handledScanIds.add(scanId);
      writeScanIds(handledScanIds, state.observedScanIds);
      return { handledScanIds };
    }),
  markObserved: (scanId) =>
    set((state) => {
      if (state.observedScanIds.has(scanId)) return state;
      const observedScanIds = new Set(state.observedScanIds);
      observedScanIds.add(scanId);
      writeScanIds(state.handledScanIds, observedScanIds);
      return { observedScanIds };
    }),
}));
