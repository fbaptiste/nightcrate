import { create } from "zustand";

interface DsoCatalogState {
  query: string;
  typeFilter: string[];
  constellationFilter: string[];
  hasDistance: boolean;
  catalogFilter: string[];
  page: number;
  pageSize: number;
  sortField: string;
  sortDir: "asc" | "desc";
  detailId: number | null;
  setQuery: (q: string) => void;
  setTypeFilter: (f: string[]) => void;
  setConstellationFilter: (f: string[]) => void;
  setHasDistance: (v: boolean) => void;
  setCatalogFilter: (f: string[]) => void;
  setPage: (p: number) => void;
  setPageSize: (s: number) => void;
  setSort: (field: string, direction: "asc" | "desc") => void;
  setDetailId: (id: number | null) => void;
}

export const useDsoCatalogStore = create<DsoCatalogState>()((set) => ({
  query: "",
  typeFilter: [],
  constellationFilter: [],
  hasDistance: false,
  catalogFilter: [],
  page: 0,
  pageSize: 100,
  sortField: "primary_designation",
  sortDir: "asc",
  detailId: null,
  setQuery: (q) => set({ query: q, page: 0 }),
  setTypeFilter: (f) => set({ typeFilter: f, page: 0 }),
  setConstellationFilter: (f) => set({ constellationFilter: f, page: 0 }),
  setHasDistance: (v) => set({ hasDistance: v, page: 0 }),
  setCatalogFilter: (f) => set({ catalogFilter: f, page: 0 }),
  setPage: (p) => set({ page: p }),
  setPageSize: (s) => set({ pageSize: s }),
  // Only a real sort change returns to the first page; an unchanged one
  // leaves the store untouched.
  setSort: (sortField, sortDir) =>
    set((state) =>
      state.sortField === sortField && state.sortDir === sortDir
        ? state
        : { sortField, sortDir, page: 0 },
    ),
  setDetailId: (id) => set({ detailId: id }),
}));
