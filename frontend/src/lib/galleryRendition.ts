import type { GalleryItem } from "@/api/gallery";
import {
  projectThumbnailUrl,
  renderedImageUrl,
  type CropSize,
} from "@/api/projects";
import type { GalleryView } from "@/api/settings";

export type GalleryRendition = "thumb_sm" | "thumb_md" | "thumb_lg";

/**
 * | slot | DPR | result |
 * | 180  | 1   | sm     |
 * | 180  | 2   | md     |
 * | 300  | 1   | md     |
 * | 346  | 2   | lg     |
 * | 522  | 2   | lg     |
 */
export function pickRendition(slotCssPx: number, dpr: number): GalleryRendition {
  const needed = slotCssPx * dpr;
  if (needed <= 180) return "thumb_sm";
  if (needed <= 400) return "thumb_md";
  return "thumb_lg";
}

/**
 * | view   | crop size |
 * | list   | small     |
 * | small  | small     |
 * | medium | medium    |
 * | large  | large     |
 */
export function cropSizeForView(view: GalleryView): CropSize {
  return view === "list" ? "small" : view;
}

/**
 * | item state        | result URL source                         |
 * | small crop id 12  | project thumbnail, small, version 12      |
 * | main image id 34  | measured thumb_sm/thumb_md/thumb_lg URL   |
 * | no crop or image  | null                                      |
 */
export function tileImageUrl(
  item: GalleryItem,
  size: CropSize,
  slotCssPx: number,
  dpr: number,
  ws: string,
): string | null {
  const crop = item.crops[size];
  if (crop) {
    return projectThumbnailUrl(item.project_id, size, String(crop.id), ws);
  }
  if (item.main_image_id == null) return null;
  return renderedImageUrl(
    item.project_id,
    item.main_image_id,
    pickRendition(slotCssPx, dpr),
    ws,
  );
}

/**
 * | main image | crop image | result |
 * | 10         | 20         | 20     |
 * | 10         | (none)     | 10     |
 * | (none)     | (none)     | null   |
 */
export function viewerImageId(item: GalleryItem, size: CropSize): number | null {
  return item.crops[size]?.image_id ?? item.main_image_id;
}

const MONTH = new Intl.DateTimeFormat("en-US", { month: "short" });

function localDate(value: string): Date {
  const [year, month, day = 1] = value.split("-").map(Number);
  return new Date(year, month - 1, day, 12);
}

function monthName(value: string): string {
  return MONTH.format(localDate(value));
}

/**
 * | input months/dates                    | output                 |
 * | Oct 3–21, 2025 (one run)             | Oct 3 – 21, 2025       |
 * | Oct 3, 2025 (one night)              | Oct 3, 2025            |
 * | Jan–Feb 2025; Jan 2026               | Jan–Feb 2025; Jan 2026 |
 * | Dec 2023–Jan 2024                    | Dec 2023–Jan 2024      |
 */
export function formatImagingRuns(item: GalleryItem): string[] {
  if (item.imaging_runs.length === 0) return [];

  const only = item.imaging_runs.length === 1 ? item.imaging_runs[0] : null;
  if (only && only.start === only.end && item.first_date && item.last_date) {
    const first = localDate(item.first_date);
    const last = localDate(item.last_date);
    const prefix = `${monthName(item.first_date)} ${first.getDate()}`;
    if (first.getTime() === last.getTime()) {
      return [`${prefix}, ${first.getFullYear()}`];
    }
    return [`${prefix} – ${last.getDate()}, ${last.getFullYear()}`];
  }

  return item.imaging_runs.map((run) => {
    const start = localDate(run.start);
    const end = localDate(run.end);
    if (run.start === run.end) {
      return `${monthName(run.start)} ${start.getFullYear()}`;
    }
    if (start.getFullYear() === end.getFullYear()) {
      return `${monthName(run.start)}–${monthName(run.end)} ${start.getFullYear()}`;
    }
    return (
      `${monthName(run.start)} ${start.getFullYear()}–` +
      `${monthName(run.end)} ${end.getFullYear()}`
    );
  });
}

/**
 * | project ids / image ids | result ids |
 * | 1/10, 2/null, 3/30      | 1, 3       |
 * | 1/null                  | (empty)    |
 */
export function viewerSequence(items: GalleryItem[]): GalleryItem[] {
  return items.filter((item) => item.main_image_id != null);
}
