import { useQuery } from "@tanstack/react-query";
import skyDataUrl from "@/data/sky/sky.json?url";
import type { SkyCoord } from "./geometry";

export interface SkyData {
  source: { inputs: Record<string, { sha256: string; origin: string }> };
  stars: [ra: number, dec: number, magnitude: number][];
  figures: Record<string, number[][]>;
  boundaries: Record<string, SkyCoord[][]>;
  labels: Record<string, { rank: number; points: { at: SkyCoord; name?: string }[] }>;
  names: [starIndex: number, name: string][];
}

let skyDataPromise: Promise<SkyData> | null = null;

export function loadSkyData(): Promise<SkyData> {
  if (!skyDataPromise) {
    skyDataPromise = fetch(skyDataUrl).then((response) => {
      if (!response.ok) throw new Error(`Sky data request failed: ${response.status}`);
      return response.json() as Promise<SkyData>;
    }).catch((error: unknown) => {
      skyDataPromise = null;
      throw error;
    });
  }
  return skyDataPromise;
}

export function useSkyData() {
  return useQuery({
    queryKey: ["sky-data"],
    queryFn: loadSkyData,
    staleTime: Infinity,
    gcTime: Infinity,
    retry: 1,
  });
}
