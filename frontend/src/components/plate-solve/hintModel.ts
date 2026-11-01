import type { HeaderCard } from "@/api/images";
import type { PlateSolveRequest, PlateSolver } from "@/api/plateSolve";
import { headerNumber, parseHeaderCoord } from "@/components/analyzer/analyzerHelpers";

export interface HeaderHints {
  ra: number | null;
  dec: number | null;
  scaleArcsec: number | null;
  focalLengthMm: number | null;
  physicalPixelUm: number | null;
  effectivePixelUm: number | null;
  binning: number;
}

export type PositionHint =
  | { kind: "header" }
  | { kind: "target"; id: number; label: string; ra: number; dec: number }
  | { kind: "none" };

export type ScaleHint =
  | { kind: "header" }
  | { kind: "rig"; rigId: number; rigName: string; focalLengthMm: number; pixelSizeUm: number; binning: number }
  | { kind: "calc"; focalLengthMm: number; pixelSizeUm: number; binning: number }
  | { kind: "enter"; scaleArcsec: number }
  | { kind: "none" };

export interface AppliedHints {
  position: PositionHint;
  scale: ScaleHint;
  solver: PlateSolver;
}

export function headerHints(cards: HeaderCard[]): HeaderHints {
  const focalLengthMm = headerNumber(cards, "FOCALLEN");
  const effectivePixelUm = headerNumber(cards, "YPIXSZ") ?? headerNumber(cards, "XPIXSZ");
  const rawBinning = headerNumber(cards, "YBINNING") ?? headerNumber(cards, "XBINNING") ?? 1;
  const binning = Number.isFinite(rawBinning) && rawBinning > 0 ? rawBinning : 1;
  return {
    ra: parseHeaderCoord(cards, true, "RA", "OBJCTRA", "CRVAL1"),
    dec: parseHeaderCoord(cards, false, "DEC", "OBJCTDEC", "CRVAL2"),
    scaleArcsec:
      focalLengthMm != null && focalLengthMm > 0 && effectivePixelUm != null && effectivePixelUm > 0
        ? (effectivePixelUm / focalLengthMm) * 206.265
        : null,
    focalLengthMm,
    physicalPixelUm: effectivePixelUm != null ? effectivePixelUm / binning : null,
    effectivePixelUm,
    binning,
  };
}

export function scaleFrom(scale: Exclude<ScaleHint, { kind: "header" } | { kind: "none" }>): number {
  if (scale.kind === "enter") return scale.scaleArcsec;
  return (scale.pixelSizeUm * scale.binning * 206.265) / scale.focalLengthMm;
}

export function buildRequest(
  image: { path: string; hdu: number },
  state: AppliedHints,
): PlateSolveRequest {
  const request: PlateSolveRequest = {
    image_path: image.path,
    hdu: image.hdu,
    operation_id: crypto.randomUUID(),
    solver: state.solver,
  };
  if (state.position.kind === "target") {
    request.ra_hint = state.position.ra;
    request.dec_hint = state.position.dec;
  } else if (state.position.kind === "none") {
    request.position = "none";
  }
  if (state.scale.kind === "none") {
    request.scale = "none";
  } else if (state.scale.kind !== "header") {
    request.scale_hint_arcsec = scaleFrom(state.scale);
  }
  return request;
}
