import { create } from "zustand";
import { persist, createJSONStorage } from "zustand/middleware";

/** Thumbnail cache-generation counter.
 *
 *  The backend persists a monotonic counter in its ``settings`` table
 *  and increments it whenever the thumbnail cache is cleared. Every
 *  thumbnail URL appends ``&_g=N`` sourced from this value so the
 *  user's browser HTTP cache treats pre-clear and post-clear URLs as
 *  distinct resources — otherwise a browser-cached 200 from before the
 *  clear would keep serving forever (up to its max-age).
 *
 *  Persisted so a page refresh doesn't drop the latest seen generation
 *  before the next stats query lands. The ``AppLayout`` hydrates from
 *  the stats endpoint on mount and keeps the store in sync.
 */
interface ThumbnailCacheState {
  generation: number;
  setGeneration: (gen: number) => void;
}

export const useThumbnailCacheStore = create<ThumbnailCacheState>()(
  persist(
    (set) => ({
      generation: 0,
      setGeneration: (gen) => set({ generation: gen }),
    }),
    {
      name: "nightcrate-thumbnail-cache",
      storage: createJSONStorage(() => localStorage),
    },
  ),
);
