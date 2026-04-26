import { create } from "zustand";
import type { ParseResponse } from "@/api/phd2";

interface Phd2State {
  activePath: string;
  pathInput: string;
  selectedIndex: number;
  parsed: ParseResponse | null;
  tab: number;
  setActivePath: (path: string) => void;
  setPathInput: (path: string) => void;
  setSelectedIndex: (i: number) => void;
  setParsed: (p: ParseResponse | null) => void;
  setTab: (t: number) => void;
}

export const usePhd2Store = create<Phd2State>()((set) => ({
  activePath: "",
  pathInput: "",
  selectedIndex: 0,
  parsed: null,
  tab: 1,
  setActivePath: (path) => set({ activePath: path }),
  setPathInput: (path) => set({ pathInput: path }),
  setSelectedIndex: (i) => set({ selectedIndex: i }),
  setParsed: (p) => set({ parsed: p }),
  setTab: (t) => set({ tab: t }),
}));
