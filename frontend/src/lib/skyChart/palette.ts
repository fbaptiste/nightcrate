export interface SkyPalette {
  sky: string;
  stars: string;
  figures: string;
  figureHighlight: string;
  names: string;
  nameHighlight: string;
  starNames: string;
  grid: string;
  target: string;
  buttonBackground: string;
  buttonBorder: string;
  buttonText: string;
}

export const SKY_PALETTES: { night: SkyPalette; paper: SkyPalette } = {
  night: {
    sky: "#0e1628", stars: "#f4f1ea", figures: "#7d9ab8", figureHighlight: "#b6cbe0",
    names: "#a0b8d0", nameHighlight: "#e2e8f0", starNames: "#b3ad9f",
    grid: "rgba(160, 184, 208, 0.12)",
    target: "#e6b35e", buttonBackground: "rgba(14, 22, 40, 0.72)",
    buttonBorder: "rgba(255, 255, 255, 0.18)", buttonText: "#e2e0dd",
  },
  paper: {
    sky: "#fbfaf7", stars: "#1f2329", figures: "#5b7a9e", figureHighlight: "#2f4b6b",
    names: "#3f5c78", nameHighlight: "#1f3550", starNames: "#6b6559",
    grid: "rgba(63, 92, 120, 0.14)",
    target: "#b8661a", buttonBackground: "rgba(255, 255, 255, 0.86)",
    buttonBorder: "rgba(0, 0, 0, 0.14)", buttonText: "#2c2c2c",
  },
};
