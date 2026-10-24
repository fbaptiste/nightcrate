import { alpha, type Theme } from "@mui/material/styles";

/**
 * Colours for the weather verdict, taken from the mockups Fred approved
 * (blue = within your limits, orange = rain over your limit, grey hatch = too
 * cloudy). The app theme's slate/amber accents are too muted to separate these
 * states at a glance, especially for red-green colour blindness, so the weather
 * views use this palette instead. Every state also carries a pattern or text.
 */
export type DarknessLevel = "day" | "civil" | "nautical" | "astro";

export interface WeatherPalette {
  /** Hour-strip cell grounds (option B): icons carry the reason, not colour. */
  /** Clear hour cells and the Go pill share this ground (Fred, 2026-10-17). */
  clearCell: string;
  onClearCell: string;
  limitCell: string;
  modelsCell: string;
  iconLit: string;
  clear: string;
  cloudStripe: string;
  cloudGround: string;
  rainDot: string;
  rainGround: string;
  otherStripe: string;
  otherGround: string;
  modelsStripe: string;
  unknownBorder: string;
  twilightGround: string;
  twilightBorder: string;
  uncertain: string;
  noGround: string;
  onNo: string;
  neutralText: string;
  passGround: string;
  onPass: string;
  failStrong: string;
  failWeak: string;
  onFail: string;
  infoGround: string;
  onInfo: string;
  dimGround: string;
  onDim: string;
  /** Darkness band: lighter to darker grounds, so luminance and the label carry it. */
  darkness: Record<DarknessLevel, { ground: string; text: string; border?: string }>;
}

const DARK: WeatherPalette = {
  clearCell: "#2c4a6e",
  onClearCell: "#ffffff",
  limitCell: "#2e3238",
  modelsCell: "#4a4f57",
  iconLit: "#f0a23a",
  clear: "#3f7fd0",
  cloudStripe: "#5b616b",
  cloudGround: "#3d4148",
  rainDot: "#e08a2e",
  rainGround: "#7a4a17",
  otherStripe: "#8e8c88",
  otherGround: "#3d4148",
  modelsStripe: "#5b616b",
  unknownBorder: "#8e8c88",
  twilightGround: "#24272c",
  twilightBorder: "#3a3f46",
  uncertain: "#e08a2e",
  noGround: "#4a4f57",
  onNo: "#e2e0dd",
  neutralText: "#8e8c88",
  passGround: alpha("#3f7fd0", 0.32),
  onPass: "#ffffff",
  failStrong: alpha("#e08a2e", 0.55),
  failWeak: alpha("#e08a2e", 0.22),
  onFail: "#ffffff",
  infoGround: "#2a2e34",
  onInfo: "#d6d3ce",
  dimGround: "#23262b",
  onDim: "#8e8c88",
  darkness: {
    day: { ground: "#8e959e", text: "#1a1c20" },
    civil: { ground: "#5b616b", text: "#f1f0ee" },
    nautical: { ground: "#3a3f46", text: "#d6d3ce" },
    astro: { ground: "#16181b", text: "#b9b6b0", border: "#3a3f46" },
  },
};

const LIGHT: WeatherPalette = {
  clearCell: "#c9dcf3",
  onClearCell: "#1d3f6b",
  limitCell: "#e6e8eb",
  modelsCell: "#c3c8ce",
  iconLit: "#c2620c",
  clear: "#2f6fc0",
  cloudStripe: "#9aa1aa",
  cloudGround: "#dfe2e6",
  rainDot: "#c2620c",
  rainGround: "#f5d5b0",
  otherStripe: "#6b7280",
  otherGround: "#e5e7ea",
  modelsStripe: "#9aa1aa",
  unknownBorder: "#6b6b6b",
  twilightGround: "#f1f0ee",
  twilightBorder: "#dddad5",
  uncertain: "#b85c0a",
  noGround: "#dfe1e5",
  onNo: "#2c2c2c",
  neutralText: "#6b6b6b",
  passGround: alpha("#2f6fc0", 0.18),
  onPass: "#1a1c20",
  failStrong: alpha("#c2620c", 0.42),
  failWeak: alpha("#c2620c", 0.14),
  onFail: "#1a1c20",
  infoGround: "#f3f2f0",
  onInfo: "#2c2c2c",
  dimGround: "#f7f6f4",
  onDim: "#7a7770",
  darkness: {
    day: { ground: "#f3f2f0", text: "#3a3f46", border: "#dddad5" },
    civil: { ground: "#c3c8ce", text: "#1a1c20" },
    nautical: { ground: "#7a818b", text: "#ffffff" },
    astro: { ground: "#3d4148", text: "#ffffff" },
  },
};

export function weatherPalette(theme: Theme): WeatherPalette {
  const base = theme.palette.mode === "dark" ? DARK : LIGHT;
  const white = theme.palette.common.white;
  if (theme.palette.mode === "dark") return { ...base, onClearCell: white, onPass: white, onFail: white };
  return {
    ...base,
    darkness: {
      ...base.darkness,
      nautical: { ...base.darkness.nautical, text: white },
      astro: { ...base.darkness.astro, text: white },
    },
  };
}

export function cloudHatch(p: WeatherPalette): string {
  return `repeating-linear-gradient(135deg, ${p.cloudStripe} 0 3px, ${p.cloudGround} 3px 6px)`;
}

export function rainDots(p: WeatherPalette): string {
  return `repeating-radial-gradient(circle at 3px 3px, ${p.rainDot} 0 1.6px, ${p.rainGround} 1.7px 6px)`;
}

export function failHatch(p: WeatherPalette): string {
  return `repeating-linear-gradient(135deg, ${p.failStrong} 0 3px, ${p.failWeak} 3px 6px)`;
}
