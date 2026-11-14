import * as d3 from "d3";
import { displayConstellation } from "../constellations";
import type { SolveWcs } from "../../api/projectInfo";
import type { SkyData } from "./data";
import {
  adaptiveMesh,
  densifyRing,
  growTriangle,
  magnitudeLimit,
  makeProjection,
  pictureOutline,
  placeStarName,
  rectsOverlap,
  segmentTouchesRect,
  showsAllNames,
  sourceRect,
  starNameMagnitudeLimit,
  starRadius,
  triangleAffine,
  trimSegment,
  visibleLineRuns,
  visibleRadiusDeg,
  visibleSkyGrid,
  type SkyCoord,
  type Rect,
  type SkyView,
} from "./geometry";
import type { SkyPalette } from "./palette";
import { pictureLabel } from "./text";

export interface SkyScene {
  data: SkyData;
  view: SkyView;
  palette: SkyPalette;
  fontFamily: string;
  targetCode: string;
  wcs: SolveWcs;
  pictureCentre: SkyCoord;
  image: CanvasImageSource | null;
  imageSize: { width: number; height: number } | null;
  label: string;
  mode: "compact" | "full";
  /** Areas covered by controls over the canvas, in CSS pixels; names avoid them. */
  reserved?: readonly Rect[];
}

const DEG = Math.PI / 180;
const boundaryCache = new Map<string, SkyCoord[][]>();

function onCanvas(point: [number, number], width: number, height: number, margin = 0): boolean {
  return point[0] >= -margin && point[0] <= width + margin && point[1] >= -margin && point[1] <= height + margin;
}

function strokeGeoJson(
  ctx: CanvasRenderingContext2D,
  path: d3.GeoPath<unknown, d3.GeoPermissibleObjects>,
  object: d3.GeoPermissibleObjects,
) {
  ctx.beginPath();
  path(object);
  ctx.stroke();
}

export function drawSkyChart(
  ctx: CanvasRenderingContext2D,
  scene: SkyScene,
  size: { width: number; height: number; dpr: number },
): { outlineLongerEdgePx: number; pictureDrawnWidthDevicePx: number } {
  const { width, height, dpr } = size;
  const { data, view, palette } = scene;
  ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
  ctx.clearRect(0, 0, width, height);
  ctx.fillStyle = palette.sky;
  ctx.fillRect(0, 0, width, height);
  const projection = makeProjection(view, width, height);
  const path = d3.geoPath(projection, ctx);
  const isFar = (coord: SkyCoord, degrees: number) => d3.geoDistance(view.centre, coord) > degrees * DEG;
  const visibleRadius = visibleRadiusDeg(view, width, height);

  ctx.save();
  ctx.strokeStyle = palette.grid;
  ctx.lineWidth = 0.8;
  const grid = visibleSkyGrid(view, width, height);
  for (const line of [...grid.parallels, ...grid.meridians]) {
    for (const run of visibleLineRuns(line.coordinates, view.centre, visibleRadius)) {
      strokeGeoJson(ctx, path, { type: "LineString", coordinates: run } as d3.GeoPermissibleObjects);
    }
  }
  ctx.restore();

  const rawRings = data.boundaries[scene.targetCode] ?? [];
  let rings = boundaryCache.get(scene.targetCode);
  if (!rings) {
    rings = rawRings.map((ring) => densifyRing(ring));
    boundaryCache.set(scene.targetCode, rings);
  }
  ctx.save();
  ctx.strokeStyle = palette.figureHighlight;
  ctx.lineWidth = 1.6;
  ctx.setLineDash([5, 3]);
  for (const ring of rings) {
    for (const run of visibleLineRuns(ring, view.centre, visibleRadius)) {
      strokeGeoJson(ctx, path, { type: "LineString", coordinates: run } as d3.GeoPermissibleObjects);
    }
  }
  ctx.restore();

  for (const [code, lines] of Object.entries(data.figures)) {
    ctx.save();
    const highlighted = code === scene.targetCode;
    ctx.strokeStyle = highlighted ? palette.figureHighlight : palette.figures;
    ctx.globalAlpha = highlighted ? 0.95 : 0.6;
    ctx.lineWidth = highlighted ? 1.6 : 1;
    ctx.lineCap = "round";
    for (const line of lines) {
      for (let index = 1; index < line.length; index += 1) {
        const starA = data.stars[line[index - 1]];
        const starB = data.stars[line[index]];
        const coordA: SkyCoord = [starA[0], starA[1]];
        const coordB: SkyCoord = [starB[0], starB[1]];
        if (isFar(coordA, 150) || isFar(coordB, 150)) continue;
        const projectedA = projection(coordA);
        const projectedB = projection(coordB);
        if (!projectedA || !projectedB || !segmentTouchesRect(projectedA, projectedB, width, height, 20)) continue;
        const [start, end] = trimSegment(
          projectedA,
          projectedB,
          starRadius(starA[2], view.spanDeg) + 3,
          starRadius(starB[2], view.spanDeg) + 3,
        );
        ctx.beginPath();
        ctx.moveTo(...start);
        ctx.lineTo(...end);
        ctx.stroke();
      }
    }
    ctx.restore();
  }

  const limit = magnitudeLimit(view.spanDeg);
  ctx.fillStyle = palette.stars;
  for (const [ra, dec, magnitude] of data.stars) {
    const coord: SkyCoord = [ra, dec];
    if (magnitude > limit || isFar(coord, 150)) continue;
    const projected = projection(coord);
    if (!projected || !onCanvas(projected, width, height, 5)) continue;
    ctx.beginPath();
    ctx.arc(projected[0], projected[1], starRadius(magnitude, view.spanDeg), 0, 2 * Math.PI);
    ctx.fill();
  }

  const outline = pictureOutline(scene.wcs);
  const projectedOutline = outline.map((coord) => projection(coord));
  const corners = [0, 8, 16, 24].map((index) => projectedOutline[index]);
  const edgeLengths = corners.map((corner, index) => {
    const next = corners[(index + 1) % corners.length];
    return corner && next ? Math.hypot(next[0] - corner[0], next[1] - corner[1]) : 0;
  });
  const outlineLongerEdgePx = Math.max(...edgeLengths);
  const pictureCentre = projection(scene.pictureCentre) ?? [width / 2, height / 2];
  let pictureDrawnWidthDevicePx = 0;

  if (scene.image && scene.imageSize && outlineLongerEdgePx >= 46) {
    const mesh = adaptiveMesh({
      wcs: scene.wcs,
      imageW: scene.imageSize.width,
      imageH: scene.imageSize.height,
      project: (coord) => projection(coord),
      isFar: (coord) => isFar(coord, 120),
      isWide: (coord) => isFar(coord, 90),
      viewport: { width, height },
    });
    for (const triangle of mesh) {
      const affine = triangleAffine(triangle.src, triangle.dst);
      const grown = growTriangle(triangle.dst, 0.6);
      const rect = sourceRect(grown, affine, scene.imageSize.width, scene.imageSize.height);
      if (!rect) continue;
      ctx.save();
      ctx.beginPath();
      ctx.moveTo(...grown[0]);
      ctx.lineTo(...grown[1]);
      ctx.lineTo(...grown[2]);
      ctx.closePath();
      ctx.clip();
      ctx.setTransform(
        dpr * affine[0], dpr * affine[1], dpr * affine[2],
        dpr * affine[3], dpr * affine[4], dpr * affine[5],
      );
      ctx.drawImage(scene.image, rect.sx, rect.sy, rect.sw, rect.sh, rect.sx, rect.sy, rect.sw, rect.sh);
      ctx.restore();
    }
    pictureDrawnWidthDevicePx = outlineLongerEdgePx * dpr;
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
  }

  ctx.save();
  ctx.strokeStyle = palette.target;
  ctx.lineWidth = 1.6;
  if (outlineLongerEdgePx >= 10 && projectedOutline.every(Boolean)) {
    ctx.beginPath();
    projectedOutline.forEach((point, index) => {
      if (!point) return;
      if (index === 0) ctx.moveTo(...point);
      else ctx.lineTo(...point);
    });
    ctx.closePath();
    ctx.stroke();
  } else {
    const radius = scene.mode === "compact" ? 7 : 12;
    ctx.lineWidth = 1.8;
    ctx.beginPath();
    ctx.arc(pictureCentre[0], pictureCentre[1], radius, 0, 2 * Math.PI);
    ctx.stroke();
    for (const [dx, dy] of [[0, -1], [0, 1], [-1, 0], [1, 0]]) {
      ctx.beginPath();
      ctx.moveTo(pictureCentre[0] + dx * (radius + 2), pictureCentre[1] + dy * (radius + 2));
      ctx.lineTo(pictureCentre[0] + dx * (radius + 7), pictureCentre[1] + dy * (radius + 7));
      ctx.stroke();
    }
  }
  ctx.restore();

  const shortenedLabel = pictureLabel(scene.label);
  ctx.font = `600 12.5px ${scene.fontFamily}`;
  const pictureTextWidth = ctx.measureText(shortenedLabel).width;
  const hasOutline = outlineLongerEdgePx >= 10 && projectedOutline.every(Boolean);
  const pictureMarkerBox: Rect = hasOutline
    ? (() => {
      const points = projectedOutline as [number, number][];
      const minX = Math.min(...points.map((point) => point[0]));
      const maxX = Math.max(...points.map((point) => point[0]));
      const minY = Math.min(...points.map((point) => point[1]));
      const maxY = Math.max(...points.map((point) => point[1]));
      return { x: minX - 3, y: minY - 3, width: maxX - minX + 6, height: maxY - minY + 6 };
    })()
    : (() => {
      const radius = (scene.mode === "compact" ? 7 : 12) + 7 + 1;
      return {
        x: pictureCentre[0] - radius,
        y: pictureCentre[1] - radius,
        width: radius * 2,
        height: radius * 2,
      };
    })();
  // To the right of everything the picture's marker covers, so a rotated outline's corner never
  // runs into the label.
  const labelX = pictureMarkerBox.x + pictureMarkerBox.width + 7;
  const labelY = pictureCentre[1] + 4;
  const pictureLabelBox: Rect = { x: labelX - 2, y: labelY - 13, width: pictureTextWidth + 4, height: 17 };
  const occupied: Rect[] = [pictureMarkerBox, pictureLabelBox, ...(scene.reserved ?? [])];

  const labelEntries = Object.entries(data.labels).flatMap(([code, label]) => label.points.map((point) => ({
    code,
    rank: label.rank,
    at: point.at,
    name: point.name ?? displayConstellation(code),
  })));
  const visibleLabels = labelEntries.filter((entry) => {
    if (scene.mode === "compact") return entry.code === scene.targetCode;
    return entry.code === scene.targetCode || showsAllNames(view.spanDeg) || entry.rank === 1;
  }).sort((left, right) => Number(right.code === scene.targetCode) - Number(left.code === scene.targetCode));

  for (const entry of visibleLabels) {
    if (isFar(entry.at, 150)) continue;
    const projected = projection(entry.at);
    if (!projected || !onCanvas(projected, width, height, 30)) continue;
    const highlighted = entry.code === scene.targetCode;
    const fontSize = highlighted ? 13 : 11;
    ctx.font = `${highlighted ? 500 : 400} italic ${fontSize}px ${scene.fontFamily}`;
    const textWidth = ctx.measureText(entry.name).width;
    const offsets = highlighted ? [0, 18, -18] : [0];
    let placement: { x: number; y: number; box: Rect } | null = null;
    for (const offset of offsets) {
      const y = projected[1] + offset;
      const box: Rect = { x: projected[0] - textWidth / 2 - 2, y: y - fontSize, width: textWidth + 4, height: fontSize + 4 };
      if (!occupied.some((item) => rectsOverlap(item, box))) {
        placement = { x: projected[0], y, box };
        break;
      }
    }
    if (!placement && highlighted) {
      // Below, then above, the picture's reserved box, so a large picture never sits under its own
      // name. If neither fits on the canvas clear of the controls, the name is left out.
      const x = pictureCentre[0];
      for (const y of [
        pictureMarkerBox.y + pictureMarkerBox.height + fontSize + 2,
        pictureMarkerBox.y - 6,
      ]) {
        const box: Rect = { x: x - textWidth / 2 - 2, y: y - fontSize, width: textWidth + 4, height: fontSize + 4 };
        const inside = box.x >= 0 && box.y >= 0 && box.x + box.width <= width && box.y + box.height <= height;
        if (inside && !occupied.some((item) => rectsOverlap(item, box))) {
          placement = { x, y, box };
          break;
        }
      }
    }
    if (!placement) continue;
    ctx.fillStyle = highlighted ? palette.nameHighlight : palette.names;
    ctx.textAlign = "center";
    ctx.fillText(entry.name, placement.x, placement.y);
    occupied.push(placement.box);
  }

  if (scene.mode === "full") {
    ctx.save();
    const fontSize = 10.5;
    ctx.font = `400 ${fontSize}px ${scene.fontFamily}`;
    ctx.lineWidth = 3;
    ctx.lineJoin = "round";
    ctx.strokeStyle = palette.sky;
    ctx.fillStyle = palette.starNames;
    const nameLimit = starNameMagnitudeLimit(view.spanDeg);
    for (const [index, name] of data.names) {
      const star = data.stars[index];
      if (!star || star[2] > nameLimit) continue;
      const coord: SkyCoord = [star[0], star[1]];
      if (isFar(coord, 150)) continue;
      const projected = projection(coord);
      if (!projected || !onCanvas(projected, width, height)) continue;
      const placement = placeStarName(
        projected,
        starRadius(star[2], view.spanDeg),
        ctx.measureText(name).width,
        fontSize,
        occupied,
        { width, height },
      );
      if (!placement) continue;
      ctx.textAlign = placement.align;
      ctx.strokeText(name, placement.x, placement.y);
      ctx.fillText(name, placement.x, placement.y);
      occupied.push(placement.box);
    }
    ctx.restore();
  }

  ctx.font = `600 12.5px ${scene.fontFamily}`;
  ctx.textAlign = "left";
  ctx.lineWidth = 6;
  ctx.lineJoin = "round";
  ctx.strokeStyle = palette.sky;
  ctx.strokeText(shortenedLabel, labelX, labelY);
  ctx.fillStyle = palette.target;
  ctx.fillText(shortenedLabel, labelX, labelY);
  ctx.globalAlpha = 1;
  ctx.setLineDash([]);
  return { outlineLongerEdgePx, pictureDrawnWidthDevicePx };
}
