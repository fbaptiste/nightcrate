/**
 * Recent-files history for the PHD2 Analyzer — localStorage-backed,
 * capped at MAX_ENTRIES, deduped on path. Corruption silently resets.
 */

const STORAGE_KEY = "phd2.recentFiles";
const MAX_ENTRIES = 10;

export interface RecentFile {
  path: string;
  openedAt: string;
  /** Rig the user picked for this log; undefined on entries written
   *  before v0.26.0 — treated as null. */
  selectedRigId?: number | null;
}

export function getRecentFiles(): RecentFile[] {
  try {
    const raw = window.localStorage.getItem(STORAGE_KEY);
    if (!raw) return [];
    const parsed = JSON.parse(raw);
    if (!Array.isArray(parsed)) return [];
    return parsed
      .filter(
        (e): e is RecentFile =>
          typeof e === "object" &&
          e !== null &&
          typeof (e as RecentFile).path === "string" &&
          typeof (e as RecentFile).openedAt === "string",
      )
      .map((e) => {
        const rigId = e.selectedRigId;
        return {
          ...e,
          selectedRigId:
            typeof rigId === "number" && Number.isInteger(rigId) && rigId > 0
              ? rigId
              : null,
        };
      });
  } catch {
    return [];
  }
}

export function addRecentFile(path: string): RecentFile[] {
  const now = new Date().toISOString();
  const prev = getRecentFiles();
  // Carry forward an existing entry's rig so re-opening preserves the choice.
  const existing = prev.find((e) => e.path === path);
  const filtered = prev.filter((e) => e.path !== path);
  const next: RecentFile[] = [
    {
      path,
      openedAt: now,
      selectedRigId: existing?.selectedRigId ?? null,
    },
    ...filtered,
  ].slice(0, MAX_ENTRIES);
  saveRecentFiles(next);
  return next;
}

export function setRecentFileRig(
  path: string,
  rigId: number | null,
): RecentFile[] {
  const prev = getRecentFiles();
  const existing = prev.find((e) => e.path === path);
  if (!existing) {
    // Pre-record so the rig sticks even if the parse later fails.
    const next: RecentFile[] = [
      { path, openedAt: new Date().toISOString(), selectedRigId: rigId },
      ...prev,
    ].slice(0, MAX_ENTRIES);
    saveRecentFiles(next);
    return next;
  }
  const next = prev.map((e) =>
    e.path === path ? { ...e, selectedRigId: rigId } : e,
  );
  saveRecentFiles(next);
  return next;
}

export function removeRecentFile(path: string): RecentFile[] {
  const next = getRecentFiles().filter((e) => e.path !== path);
  saveRecentFiles(next);
  return next;
}

export function clearRecentFiles(): void {
  try {
    window.localStorage.removeItem(STORAGE_KEY);
  } catch {
    // localStorage unavailable (private mode, quota) — swallow.
  }
}

function saveRecentFiles(entries: RecentFile[]): void {
  try {
    window.localStorage.setItem(STORAGE_KEY, JSON.stringify(entries));
  } catch {
    // localStorage unavailable — swallow.
  }
}

export function formatRelativeTime(isoString: string): string {
  const then = new Date(isoString).getTime();
  if (Number.isNaN(then)) return "";
  const now = Date.now();
  const diffSec = Math.floor((now - then) / 1000);
  if (diffSec < 60) return "just now";
  if (diffSec < 3600) return `${Math.floor(diffSec / 60)} min ago`;
  const thenDate = new Date(isoString);
  const nowDate = new Date();
  const msPerDay = 86_400_000;
  const thenMid = new Date(thenDate.getFullYear(), thenDate.getMonth(), thenDate.getDate()).getTime();
  const nowMid = new Date(nowDate.getFullYear(), nowDate.getMonth(), nowDate.getDate()).getTime();
  const dayDiff = Math.round((nowMid - thenMid) / msPerDay);
  if (dayDiff === 0) {
    return `today ${thenDate.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" })}`;
  }
  if (dayDiff === 1) return "yesterday";
  if (dayDiff < 7) return `${dayDiff} days ago`;
  return thenDate.toLocaleDateString([], { month: "short", day: "numeric" });
}
