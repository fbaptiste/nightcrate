export type PatternName = "RGGB" | "GRBG" | "GBRG" | "BGGR";
export type PatternChoice = "" | PatternName;

export interface PatternOption {
  value: PatternChoice;
  label: string;
}

const PATTERNS: readonly PatternName[] = ["RGGB", "GRBG", "GBRG", "BGGR"];

export function analyzerImageKey(path: string, hdu: number): string {
  return `${path}::${hdu}`;
}

export function shouldResetPatternChoice(
  previousKey: string,
  path: string,
  hdu: number,
): boolean {
  return previousKey !== analyzerImageKey(path, hdu);
}

export function patternOptions(suggested?: string | null): PatternOption[] {
  const rigPattern = PATTERNS.find((pattern) => pattern === suggested) ?? null;
  const options: PatternOption[] = [];
  if (rigPattern) {
    options.push({ value: rigPattern, label: `${rigPattern} (this rig's camera)` });
  }
  options.push({ value: "", label: "None (mono)" });
  for (const pattern of PATTERNS) {
    if (pattern !== rigPattern) options.push({ value: pattern, label: pattern });
  }
  return options;
}

export interface InspectorValue {
  K: number;
  units: string;
  site_colour?: string | null;
}

export function pixelPlaceholderData<T>(
  previousData: T | undefined,
  previousQueryKey: readonly unknown[] | undefined,
  path: string,
  hdu: number,
  pattern: PatternName | undefined,
): T | undefined {
  return previousQueryKey?.[0] === "image-pixel"
    && previousQueryKey[1] === path
    && previousQueryKey[2] === hdu
    && previousQueryKey[5] === pattern
    ? previousData
    : undefined;
}

export function inspectorLabel(pixel: InspectorValue | null | undefined): string {
  if (!pixel) return "Move over the image to inspect a pixel";
  const value = pixel.units === "adu"
    ? `${Math.round(pixel.K).toLocaleString("en-US")} ADU`
    : pixel.K.toFixed(3);
  const colour = pixel.site_colour?.toLowerCase();
  return colour === "r" || colour === "red"
    ? `${value}, under a red filter`
    : colour === "g" || colour === "green"
      ? `${value}, under a green filter`
      : colour === "b" || colour === "blue"
        ? `${value}, under a blue filter`
        : value;
}

export interface MetadataCardLike {
  group?: string;
  key: string;
  value: string;
  comment?: string;
  description?: string | null;
}

export interface MetadataRow {
  name: string;
  value: string;
  description: string;
  inferred?: { label: "estimated"; title: string };
}

export interface MetadataGroup {
  name: "Capture" | "Camera and lens" | "Colour data" | "EXIF" | "Maker notes";
  rows: MetadataRow[];
}

export type ImageInfoField = readonly [key: string, label: string];

const FITS_IMAGE_INFO_FIELDS: readonly ImageInfoField[] = [
  ["object_name", "Object"],
  ["filter_name", "Filter"],
  ["exposure_time", "Exposure"],
  ["gain", "Gain"],
  ["sensor_temp", "Sensor"],
  ["camera_name", "Camera"],
  ["telescope_name", "Telescope"],
  ["focal_length", "Focal Len"],
  ["frame_type", "Type"],
];

const RAW_IMAGE_INFO_FIELDS: readonly ImageInfoField[] = [
  ["exposure_time", "Exposure"],
  ["iso", "ISO"],
  ["model", "Camera"],
  ["focal_length_mm", "Focal length"],
  ["lens", "Lens"],
];

export function imageInfoFields(
  metadata: Readonly<Record<string, string | number | null>>,
  raw: boolean,
): ImageInfoField[] {
  return (raw ? RAW_IMAGE_INFO_FIELDS : FITS_IMAGE_INFO_FIELDS)
    .filter(([key]) => metadata[key] != null && String(metadata[key]).trim() !== "");
}

export function showPatternChoicePill(choice: PatternChoice | null): boolean {
  return choice !== null && choice !== "";
}

const GROUP_ORDER: MetadataGroup["name"][] = [
  "Capture",
  "Camera and lens",
  "Colour data",
  "EXIF",
  "Maker notes",
];

export function metadataGroups(cards: readonly MetadataCardLike[]): MetadataGroup[] {
  const groups = new Map<MetadataGroup["name"], MetadataRow[]>(
    GROUP_ORDER.map((name) => [name, []]),
  );
  const patternSource = cards.find(
    (card) => card.group === "Colour data" && card.key === "Pattern source",
  )?.value;
  for (const card of cards) {
    if (!GROUP_ORDER.includes(card.group as MetadataGroup["name"])) continue;
    const group = card.group as MetadataGroup["name"];
    if (group === "Colour data" && card.key === "Pattern source") continue;
    const row: MetadataRow = {
      name: group === "Colour data" && card.key === "Pattern" ? "Colour pattern" : card.key,
      value:
        group === "Colour data" && card.key === "Pattern"
          ? `${patternDisplayName(card.value)}${patternSource ? `, from ${patternSource}` : ""}`
          : card.value,
      description: card.comment || card.description || "",
    };
    groups.get(group)!.push(row);
  }

  return GROUP_ORDER.map((name) => ({ name, rows: groups.get(name)! }))
    .filter((group) => group.rows.length > 0);
}

function patternDisplayName(value: string): string {
  const rows = value.split("/");
  return rows.length === 6 && rows.every((row) => row.length === 6)
    ? "X-Trans (6×6)"
    : value.replaceAll("/", "");
}
