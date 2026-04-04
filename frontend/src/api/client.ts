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

export async function apiFetch<T>(path: string, options?: RequestInit): Promise<T> {
  const headers = new Headers(options?.headers);
  if (_activity) {
    headers.set("X-Activity", _activity);
  }
  const res = await fetch(`${BASE}${path}`, { ...options, headers });
  if (!res.ok) {
    const text = await res.text().catch(() => res.statusText);
    throw new Error(text || `HTTP ${res.status}`);
  }
  return res.json() as Promise<T>;
}
