/**
 * Recent-files history for the PHD2 Analyzer — localStorage-backed.
 *
 * Capped at ``MAX_ENTRIES``; entries are ordered most-recent-first,
 * deduped on ``path``. Corruption / parse failures silently reset the
 * store to empty so a bad payload doesn't lock the user out of
 * reopening previously-analysed logs.
 *
 * First SQLite-backed persistence lands in Pass H (v0.29.0). Until
 * then this lightweight client-side store matches the image viewer's
 * recent-files pattern.
 */

const STORAGE_KEY = "phd2.recentFiles";
const MAX_ENTRIES = 10;

export interface RecentFile {
  path: string;
  openedAt: string; // ISO timestamp
}

export function getRecentFiles(): RecentFile[] {
  try {
    const raw = window.localStorage.getItem(STORAGE_KEY);
    if (!raw) return [];
    const parsed = JSON.parse(raw);
    if (!Array.isArray(parsed)) return [];
    // Filter out malformed entries so one bad item doesn't poison
    // the whole list.
    return parsed.filter(
      (e): e is RecentFile =>
        typeof e === "object" &&
        e !== null &&
        typeof (e as RecentFile).path === "string" &&
        typeof (e as RecentFile).openedAt === "string",
    );
  } catch {
    return [];
  }
}

export function addRecentFile(path: string): RecentFile[] {
  const now = new Date().toISOString();
  const prev = getRecentFiles().filter((e) => e.path !== path);
  const next: RecentFile[] = [{ path, openedAt: now }, ...prev].slice(
    0,
    MAX_ENTRIES,
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
    // localStorage unavailable — swallow. The UI will continue to
    // function without persistence for this session.
  }
}

/**
 * Human-readable relative time ("2 min ago", "today", "yesterday",
 * "3 days ago"). Avoids a date-fns dependency; precision is tuned for
 * a 10-entry recent list where day-level granularity is sufficient.
 */
export function formatRelativeTime(isoString: string): string {
  const then = new Date(isoString).getTime();
  if (Number.isNaN(then)) return "";
  const now = Date.now();
  const diffSec = Math.floor((now - then) / 1000);
  if (diffSec < 60) return "just now";
  if (diffSec < 3600) return `${Math.floor(diffSec / 60)} min ago`;
  // Compare calendar days using local date boundaries.
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
