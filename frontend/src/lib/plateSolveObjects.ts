export interface PlateSolveListObject {
  dso_id: number;
  primary_designation: string;
  common_name: string | null;
  obj_type: string;
  catalogs: string[];
  maj_axis_arcmin: number | null;
  min_axis_arcmin: number | null;
}

export interface PlateSolveFilters {
  catalogs: ReadonlySet<string>;
  types: ReadonlySet<string>;
  minSizeArcmin: number;
}

export interface FacetCounts {
  catalogs: Map<string, number>;
  types: Map<string, number>;
}

export type ObjectSortKey = "name" | "type" | "catalogs" | "size";
export type SortDirection = "asc" | "desc";

const natural = new Intl.Collator(undefined, { numeric: true, sensitivity: "base" });

function passesCatalogs(object: PlateSolveListObject, selected: ReadonlySet<string>): boolean {
  return selected.size === 0 || object.catalogs.some((catalog) => selected.has(catalog));
}

function passesTypes(object: PlateSolveListObject, selected: ReadonlySet<string>): boolean {
  return selected.size === 0 || selected.has(object.obj_type);
}

function passesSize(object: PlateSolveListObject, minimum: number): boolean {
  return minimum <= 0 || (object.maj_axis_arcmin != null && object.maj_axis_arcmin >= minimum);
}

export function filterObjects<T extends PlateSolveListObject>(
  objects: readonly T[],
  filters: PlateSolveFilters,
  mainIds: ReadonlySet<number>,
): T[] {
  return objects.filter(
    (object) =>
      mainIds.has(object.dso_id) ||
      (passesCatalogs(object, filters.catalogs) &&
        passesTypes(object, filters.types) &&
        passesSize(object, filters.minSizeArcmin)),
  );
}

function increment(map: Map<string, number>, key: string): void {
  map.set(key, (map.get(key) ?? 0) + 1);
}

export function facetCounts<T extends PlateSolveListObject>(
  objects: readonly T[],
  filters: PlateSolveFilters,
  mainIds: ReadonlySet<number>,
): FacetCounts {
  const catalogs = new Map<string, number>();
  const types = new Map<string, number>();
  for (const object of objects) {
    if (mainIds.has(object.dso_id)) continue;
    if (passesTypes(object, filters.types) && passesSize(object, filters.minSizeArcmin)) {
      for (const catalog of object.catalogs) increment(catalogs, catalog);
    }
    if (passesCatalogs(object, filters.catalogs) && passesSize(object, filters.minSizeArcmin)) {
      increment(types, object.obj_type);
    }
  }
  return { catalogs, types };
}

function primaryTie(a: PlateSolveListObject, b: PlateSolveListObject): number {
  return natural.compare(a.primary_designation, b.primary_designation) || a.dso_id - b.dso_id;
}

function nullableCompare(
  left: string | number | null,
  right: string | number | null,
  direction: SortDirection,
): number {
  if (left == null) return right == null ? 0 : 1;
  if (right == null) return -1;
  const result =
    typeof left === "number" && typeof right === "number"
      ? left - right
      : natural.compare(String(left), String(right));
  return direction === "asc" ? result : -result;
}

export function sortObjects<T extends PlateSolveListObject>(
  objects: readonly T[],
  key: ObjectSortKey,
  direction: SortDirection,
): T[] {
  return [...objects].sort((a, b) => {
    let compared: number;
    switch (key) {
      case "type":
        compared = nullableCompare(a.obj_type || null, b.obj_type || null, direction);
        break;
      case "catalogs":
        compared = nullableCompare(a.catalogs.join(", ") || null, b.catalogs.join(", ") || null, direction);
        break;
      case "size":
        compared = nullableCompare(a.maj_axis_arcmin, b.maj_axis_arcmin, direction);
        break;
      default:
        compared = nullableCompare(a.primary_designation || null, b.primary_designation || null, direction);
        break;
    }
    return compared || primaryTie(a, b);
  });
}

function sliderMinimum(maxArcmin: number): number {
  return Math.min(0.1, maxArcmin / 10);
}

export function sliderToSize(position: number, maxArcmin: number): number {
  if (position <= 0 || maxArcmin <= 0) return 0;
  if (position >= 100) return maxArcmin;
  const minimum = sliderMinimum(maxArcmin);
  return minimum * (maxArcmin / minimum) ** ((position - 1) / 99);
}

export function sizeToSlider(size: number, maxArcmin: number): number {
  if (size <= 0 || maxArcmin <= 0) return 0;
  if (size >= maxArcmin) return 100;
  const minimum = sliderMinimum(maxArcmin);
  if (size <= minimum) return 1;
  return 1 + (99 * Math.log(size / minimum)) / Math.log(maxArcmin / minimum);
}

export interface ViewState {
  scale: number;
  x: number;
  y: number;
}

export interface ViewPoint {
  x: number;
  y: number;
}

export interface ViewSize {
  width: number;
  height: number;
}

export interface ViewBounds {
  imageWidth: number;
  imageHeight: number;
  viewportWidth: number;
  viewportHeight: number;
  minScale: number;
  maxScale: number;
}

export function fitScale(
  imageWidth: number,
  imageHeight: number,
  viewportWidth: number,
  viewportHeight: number,
): number {
  if (imageWidth <= 0 || imageHeight <= 0 || viewportWidth <= 0 || viewportHeight <= 0) return 1;
  return Math.min(viewportWidth / imageWidth, viewportHeight / imageHeight);
}

function centredOffset(viewport: number, content: number): number {
  return (viewport - content) / 2;
}

export function clampView(view: ViewState, bounds: ViewBounds): ViewState {
  const scale = Math.min(bounds.maxScale, Math.max(bounds.minScale, view.scale));
  const scaledWidth = bounds.imageWidth * scale;
  const scaledHeight = bounds.imageHeight * scale;
  const x =
    scaledWidth <= bounds.viewportWidth
      ? centredOffset(bounds.viewportWidth, scaledWidth)
      : Math.min(0, Math.max(bounds.viewportWidth - scaledWidth, view.x));
  const y =
    scaledHeight <= bounds.viewportHeight
      ? centredOffset(bounds.viewportHeight, scaledHeight)
      : Math.min(0, Math.max(bounds.viewportHeight - scaledHeight, view.y));
  return { scale, x, y };
}

export function zoomAt(
  view: ViewState,
  point: ViewPoint,
  factor: number,
  bounds: ViewBounds,
): ViewState {
  const scale = Math.min(bounds.maxScale, Math.max(bounds.minScale, view.scale * factor));
  const ratio = scale / view.scale;
  return clampView(
    {
      scale,
      x: point.x - (point.x - view.x) * ratio,
      y: point.y - (point.y - view.y) * ratio,
    },
    bounds,
  );
}

export function keepCentre(
  view: ViewState,
  oldSize: ViewSize,
  newSize: ViewSize,
  bounds: ViewBounds,
): ViewState {
  const sourceX = (oldSize.width / 2 - view.x) / view.scale;
  const sourceY = (oldSize.height / 2 - view.y) / view.scale;
  return clampView(
    {
      scale: view.scale,
      x: newSize.width / 2 - sourceX * view.scale,
      y: newSize.height / 2 - sourceY * view.scale,
    },
    bounds,
  );
}
