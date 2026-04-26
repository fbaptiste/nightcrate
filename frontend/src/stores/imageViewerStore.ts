import { create } from "zustand";
import { DEFAULT_STRETCH, type StretchParams } from "@/api/images";
import type { WcsParams } from "@/api/plateSolve";

const DEFAULT_PER_CHANNEL: [StretchParams, StretchParams, StretchParams] = [
  { ...DEFAULT_STRETCH },
  { ...DEFAULT_STRETCH },
  { ...DEFAULT_STRETCH },
];

interface ImageViewerState {
  activePath: string;
  inputPath: string;
  selectedHdu: number;
  tab: number;
  linked: StretchParams;
  perChannel: [StretchParams, StretchParams, StretchParams];
  appliedLinked: StretchParams;
  appliedPerChannel: [StretchParams, StretchParams, StretchParams];
  isLinked: boolean;
  solvedWcs: WcsParams | null;
  imageActivity: string;
  appliedDefaultsFor: string;
  selectedAnnotationId: number | null;
  setActivePath: (path: string) => void;
  setInputPath: (path: string) => void;
  setSelectedHdu: (hdu: number) => void;
  setTab: (tab: number) => void;
  setLinked: (p: StretchParams) => void;
  setPerChannel: (p: [StretchParams, StretchParams, StretchParams]) => void;
  setAppliedLinked: (p: StretchParams) => void;
  setAppliedPerChannel: (p: [StretchParams, StretchParams, StretchParams]) => void;
  setIsLinked: (v: boolean) => void;
  setSolvedWcs: (wcs: WcsParams | null) => void;
  setImageActivity: (a: string) => void;
  setAppliedDefaultsFor: (key: string) => void;
  setSelectedAnnotationId: (id: number | null) => void;
  resetForNewFile: (path: string, inputPath: string) => void;
}

export const useImageViewerStore = create<ImageViewerState>()((set) => ({
  activePath: "",
  inputPath: "",
  selectedHdu: 0,
  tab: 0,
  linked: { ...DEFAULT_STRETCH },
  perChannel: [...DEFAULT_PER_CHANNEL] as [StretchParams, StretchParams, StretchParams],
  appliedLinked: { ...DEFAULT_STRETCH },
  appliedPerChannel: [...DEFAULT_PER_CHANNEL] as [StretchParams, StretchParams, StretchParams],
  isLinked: true,
  solvedWcs: null,
  imageActivity: "",
  appliedDefaultsFor: "",
  selectedAnnotationId: null,
  setActivePath: (path) => set({ activePath: path }),
  setInputPath: (path) => set({ inputPath: path }),
  setSelectedHdu: (hdu) => set({ selectedHdu: hdu }),
  setTab: (tab) => set({ tab }),
  setLinked: (p) => set({ linked: p }),
  setPerChannel: (p) => set({ perChannel: p }),
  setAppliedLinked: (p) => set({ appliedLinked: p }),
  setAppliedPerChannel: (p) => set({ appliedPerChannel: p }),
  setIsLinked: (v) => set({ isLinked: v }),
  setSolvedWcs: (wcs) => set({ solvedWcs: wcs }),
  setImageActivity: (a) => set({ imageActivity: a }),
  setAppliedDefaultsFor: (key) => set({ appliedDefaultsFor: key }),
  setSelectedAnnotationId: (id) => set({ selectedAnnotationId: id }),
  resetForNewFile: (path, inputPath) =>
    set({
      activePath: path,
      inputPath,
      selectedHdu: 0,
      tab: 0,
      linked: { ...DEFAULT_STRETCH },
      perChannel: [...DEFAULT_PER_CHANNEL] as [StretchParams, StretchParams, StretchParams],
      appliedLinked: { ...DEFAULT_STRETCH },
      appliedPerChannel: [...DEFAULT_PER_CHANNEL] as [StretchParams, StretchParams, StretchParams],
      isLinked: true,
      solvedWcs: null,
      appliedDefaultsFor: "",
      selectedAnnotationId: null,
    }),
}));
