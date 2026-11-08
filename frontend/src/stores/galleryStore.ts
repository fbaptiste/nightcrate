import { create } from "zustand";

export type GallerySort = "latest" | "first" | "name";

export interface GalleryFilters {
  search: string;
  searchImages: boolean;
  catalogs: string[];
  typeGroups: string[];
  constellations: string[];
  statuses: string[];
  rigs: string[];
  dateFrom: string;
  dateTo: string;
  includeUndated: boolean;
  includeRetired: boolean;
}

const initialFilters: GalleryFilters = {
  search: "",
  searchImages: false,
  catalogs: [],
  typeGroups: [],
  constellations: [],
  statuses: [],
  rigs: [],
  dateFrom: "",
  dateTo: "",
  includeUndated: false,
  includeRetired: false,
};

interface GalleryState extends GalleryFilters {
  sort: GallerySort;
  desc: boolean;
  set: (patch: Partial<GalleryFilters & { sort: GallerySort; desc: boolean }>) => void;
  reset: () => void;
}

export const useGalleryStore = create<GalleryState>((set) => ({
  ...initialFilters,
  sort: "latest",
  desc: true,
  set,
  reset: () => set(initialFilters),
}));
