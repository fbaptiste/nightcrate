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
      // Only apply the response if no newer save has been dispatched
      if (gen === saveGeneration) {
        set({ settings: saved });
      }
    } catch {
      // Only rollback if no newer save has superseded this one
      if (gen === saveGeneration) {
        set({ settings: current });
      }
    }
  },
}));
