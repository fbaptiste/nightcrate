export type CatalogSelectionKind = "sub_frame" | "processed_image" | "file";
export type CatalogSelectionKey = `${CatalogSelectionKind}:${number}`;

export function subFrameSelectionKey(id: number): CatalogSelectionKey {
  return `sub_frame:${id}`;
}

export function processedImageSelectionKey(id: number): CatalogSelectionKey {
  return `processed_image:${id}`;
}

export function fileSelectionKey(id: number): CatalogSelectionKey {
  return `file:${id}`;
}

export function selectionKind(key: CatalogSelectionKey): CatalogSelectionKind {
  return key.slice(0, key.lastIndexOf(":")) as CatalogSelectionKind;
}

export function selectionId(key: CatalogSelectionKey): number {
  return Number(key.slice(key.lastIndexOf(":") + 1));
}
