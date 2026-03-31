import { create } from "zustand";
import { fetchSettings, saveSettings, type Settings } from "@/api/settings";

interface SettingsState {
  settings: Settings | null;
  loading: boolean;
  load: () => Promise<void>;
  update: (patch: Partial<Settings>) => Promise<void>;
}

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
    try {
      const saved = await saveSettings(updated);
      set({ settings: saved });
    } catch {
      set({ settings: current }); // rollback on failure
    }
  },
}));
