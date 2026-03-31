import { apiFetch } from "./client";

export interface HduInfo {
  index: number;
  name: string;
  type: string;
  has_image: boolean;
}

export interface HeaderCard {
  key: string;
  value: string;
  comment: string;
}

export function fetchHdus(path: string): Promise<HduInfo[]> {
  return apiFetch<HduInfo[]>(`/fits/hdus?path=${encodeURIComponent(path)}`);
}

export function fetchHeader(path: string, hdu: number): Promise<HeaderCard[]> {
  return apiFetch<HeaderCard[]>(`/fits/header?path=${encodeURIComponent(path)}&hdu=${hdu}`);
}

export function fitsImageUrl(path: string, hdu: number): string {
  return `/api/fits/image?path=${encodeURIComponent(path)}&hdu=${hdu}`;
}
