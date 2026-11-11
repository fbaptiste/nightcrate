export interface FovGeometry {
  scale: number;
  boxWidthPct: number;
  boxHeightPct: number;
}

export interface RigViewGeometry {
  boxWidthPct: number;
  boxHeightPct: number;
}

export function rigViewGeometry(
  fieldDeg: number,
  rig: { majorDeg: number; minorDeg: number },
): RigViewGeometry {
  return {
    boxWidthPct: (rig.majorDeg / fieldDeg) * 100,
    boxHeightPct: (rig.minorDeg / (fieldDeg * 0.75)) * 100,
  };
}

export function fovGeometry(
  picture: { widthDeg: number; heightDeg: number },
  rig: { majorDeg: number; minorDeg: number },
): FovGeometry {
  const aspect = picture.widthDeg / picture.heightDeg;
  const [tileWidth, tileHeight] =
    aspect >= 4 / 3
      ? [picture.widthDeg, picture.widthDeg * 0.75]
      : [picture.heightDeg * (4 / 3), picture.heightDeg];
  const scale = Math.max(
    1,
    rig.majorDeg / (tileWidth * 0.92),
    rig.minorDeg / (tileHeight * 0.92),
  );
  return {
    scale,
    boxWidthPct: (rig.majorDeg / (tileWidth * scale)) * 100,
    boxHeightPct: (rig.minorDeg / (tileHeight * scale)) * 100,
  };
}
