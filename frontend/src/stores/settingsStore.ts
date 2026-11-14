import { create } from "zustand";
import { fetchSettings, saveSettingsPatch, type Settings } from "@/api/settings";

interface SettingsState {
  settings: Settings | null;
  loading: boolean;
  load: () => Promise<void>;
  update: (patch: Partial<Settings>) => Promise<boolean>;
}

type SettingsKey = keyof Settings;
type PendingResolution = (succeeded: boolean) => void;

let confirmed: Settings | null = null;
let pending: Partial<Settings> = {};
let pendingVersions: Partial<Record<SettingsKey, number>> = {};
let pendingResolutions: PendingResolution[] = [];
let requestInFlight = false;
let inFlightPatch: Partial<Settings> = {};
let saveCounter = 0;
let loadPromise: Promise<void> | null = null;
const fieldVersions: Partial<Record<SettingsKey, number>> = {};

function overlaySettings(base: Settings, patch: Partial<Settings>): Settings {
  return { ...base, ...patch };
}

function setPatchValue<K extends SettingsKey>(target: Partial<Settings>, key: K, value: Settings[K]) {
  target[key] = value;
}

function startNextRequest(
  set: (partial: Partial<SettingsState>) => void,
  get: () => SettingsState,
) {
  if (requestInFlight || Object.keys(pending).length === 0) return;

  const requestPatch = pending;
  const requestVersions = pendingVersions;
  const resolutions = pendingResolutions;
  pending = {};
  pendingVersions = {};
  pendingResolutions = [];
  requestInFlight = true;
  inFlightPatch = requestPatch;

  void saveSettingsPatch(requestPatch)
    .then((saved) => {
      confirmed = saved;
      set({ settings: overlaySettings(saved, pending) });
      for (const resolve of resolutions) resolve(true);
    })
    .catch(() => {
      const current = get().settings;
      if (current && confirmed) {
        const rolledBack = { ...current };
        for (const key of Object.keys(requestPatch) as SettingsKey[]) {
          if (fieldVersions[key] === requestVersions[key]) {
            setPatchValue(rolledBack, key, confirmed[key]);
          }
        }
        set({ settings: rolledBack });
      }
      for (const resolve of resolutions) resolve(false);
    })
    .finally(() => {
      inFlightPatch = {};
      requestInFlight = false;
      startNextRequest(set, get);
    });
}

export const useSettingsStore = create<SettingsState>((set, get) => ({
  settings: null,
  loading: false,

  load: () => {
    if (loadPromise) return loadPromise;
    const saveCounterAtStart = saveCounter;
    const saveActiveAtStart = requestInFlight || Object.keys(pending).length > 0;
    set({ loading: true });
    const request = fetchSettings()
      .then((settings) => {
        const saveRacedLoad = saveCounter !== saveCounterAtStart || saveActiveAtStart;
        const saveActive = requestInFlight || Object.keys(pending).length > 0;
        if (!saveRacedLoad && !saveActive) {
          confirmed = settings;
          set({ settings });
          return;
        }

        // A GET that raced a save is not authoritative for fields the user
        // changed. While a request is active, retain the GET's other fields and
        // overlay every unconfirmed choice. Once the queue has settled, its
        // full PATCH response is the newer confirmed baseline.
        const base = !requestInFlight && saveRacedLoad && confirmed
          ? confirmed
          : settings;
        set({
          settings: overlaySettings(
            overlaySettings(base, inFlightPatch),
            pending,
          ),
        });
      })
      .catch(() => undefined)
      .finally(() => {
        if (loadPromise === request) loadPromise = null;
        set({ loading: false });
      });
    loadPromise = request;
    return request;
  },

  update: async (patch) => {
    const current = get().settings;
    if (!current) return false;
    if (Object.keys(patch).length === 0) return true;
    saveCounter += 1;

    set({ settings: overlaySettings(current, patch) });
    for (const key of Object.keys(patch) as SettingsKey[]) {
      const version = (fieldVersions[key] ?? 0) + 1;
      fieldVersions[key] = version;
      pendingVersions[key] = version;
      const value = patch[key];
      if (value !== undefined) setPatchValue(pending, key, value);
    }

    const result = new Promise<boolean>((resolve) => {
      pendingResolutions.push(resolve);
    });
    startNextRequest(set, get);
    return result;
  },
}));
