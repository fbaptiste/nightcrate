import { create } from "zustand";
import { fetchSettings, saveSettings, type Settings } from "@/api/settings";

interface SettingsState {
  settings: Settings | null;
  loading: boolean;
  load: () => Promise<void>;
  update: (patch: Partial<Settings>) => Promise<void>;
}

/** Monotonic counter — only the latest save's response updates the store. */
let saveGeneration = 0;

export const useSettingsStore = create<SettingsState>((set, get) => ({
  settings: null,
  loading: false,

  load: async () => {
    set({ loading: true });
    try {
      const settings = await fetchSettings();
      set({ settings, loading: false });
    } catch {
      set({ loading: false });
    }
  },

  update: async (patch) => {
    const current = get().settings;
    if (!current) return;
    const updated = { ...current, ...patch };
    set({ settings: updated }); // optimistic
    const gen = ++saveGeneration;
    try {
      const saved = await saveSettings(updated);
      // Only apply the response if no newer save has been dispatched.
      // Merge response over the optimistic state instead of replacing
      // outright — when the running backend is older than the
      // frontend (mid-deploy, or a stale --reload), its response can
      // omit fields the frontend just set. Replacing wholesale would
      // collapse those fields to ``undefined`` and snap UI controls
      // back to defaults the moment the user changed them. Spreading
      // ``saved`` last keeps the server's authoritative values for
      // every field it returned, while preserving the optimistic
      // values for fields the server didn't echo back.
      if (gen === saveGeneration) {
        set({ settings: { ...updated, ...saved } });
      }
    } catch {
      // Only rollback if no newer save has superseded this one
      if (gen === saveGeneration) {
        set({ settings: current });
      }
    }
  },
}));
