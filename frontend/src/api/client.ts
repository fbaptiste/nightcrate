const BASE = "/api";

// ---------------------------------------------------------------------------
// Activity tagging — backend groups requests by this label
// ---------------------------------------------------------------------------

let _activity: string | null = null;

/** Set the current activity label (sent on every subsequent request). */
export function setActivity(label: string | null): void {
  _activity = label;
}

/** Read the current activity label (used by imageUrl for query-param tagging). */
export function getActivity(): string | null {
  return _activity;
}

// ---------------------------------------------------------------------------
// Fetch wrapper
// ---------------------------------------------------------------------------

/** HTTP headers can only contain ISO-8859-1 code points. Normalize common
 *  typographic characters to ASCII and strip anything still out of range so
 *  Headers.set() never throws on user-supplied names (rigs, locations, …). */
function sanitizeActivityLabel(label: string): string {
  return label
    .replace(/[\u2012-\u2015]/g, "-") // figure/en/em/horizontal-bar dashes
    .replace(/[\u2018\u2019]/g, "'") // curly single quotes
    .replace(/[\u201C\u201D]/g, '"') // curly double quotes
    .replace(/\u2026/g, "...") // ellipsis
    // eslint-disable-next-line no-control-regex
    .replace(/[^\x00-\xFF]/g, "");
}

export async function apiFetch<T>(path: string, options?: RequestInit): Promise<T> {
  const headers = new Headers(options?.headers);
  if (_activity) {
    headers.set("X-Activity", sanitizeActivityLabel(_activity));
  }
  const res = await fetch(`${BASE}${path}`, { ...options, headers });
  if (!res.ok) {
    const text = await res.text().catch(() => res.statusText);
    throw new Error(text || `HTTP ${res.status}`);
  }
  return res.json() as Promise<T>;
}
