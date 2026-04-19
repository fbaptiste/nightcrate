import { createTheme } from "@mui/material/styles";

// NightCrate palette — professional asset management for astrophotography
// Accent: warm amber (cataloging/archival tone, colorblind-safe)
// Surfaces: cool slate grays (neutral, easy on the eyes for long sessions)

const fontFamily = '"DM Sans", sans-serif';
export const monoFontFamily = '"JetBrains Mono", monospace';

const sharedTypography = {
  fontFamily,
  h4: { fontWeight: 600 },
  h5: { fontWeight: 600 },
  h6: { fontWeight: 600 },
  body1: { fontSize: "0.9rem" },
  body2: { fontSize: "0.825rem" },
  caption: { fontSize: "0.75rem" },
};

const makeCssBaseline = (colorScheme: "light" | "dark") => ({
  MuiCssBaseline: {
    styleOverrides: {
      body: { margin: 0, colorScheme },
    },
  },
});

const sharedComponents = {
  MuiButton: {
    styleOverrides: {
      root: {
        textTransform: "none" as const,
        fontWeight: 500,
        borderRadius: 6,
      },
    },
  },
  MuiListItemButton: {
    styleOverrides: {
      root: {
        borderRadius: 6,
        marginLeft: 8,
        marginRight: 8,
      },
    },
  },
  MuiDrawer: {
    styleOverrides: {
      paper: {
        borderRight: "none",
      },
    },
  },
  MuiTab: {
    styleOverrides: {
      root: {
        textTransform: "none" as const,
        fontWeight: 500,
      },
    },
  },
} as const;

export const lightTheme = createTheme({
  typography: sharedTypography,
  palette: {
    mode: "light",
    primary: {
      main: "#c07b2b",     // warm amber
      light: "#d4993f",
      dark: "#9a6220",
      contrastText: "#fff",
    },
    secondary: {
      main: "#5b7a9e",     // slate blue
      light: "#7d9ab8",
      dark: "#3f5c78",
    },
    background: {
      default: "#f5f4f2",  // warm off-white
      paper: "#ffffff",
    },
    divider: "rgba(0, 0, 0, 0.08)",
    text: {
      primary: "#2c2c2c",
      secondary: "#6b6b6b",
    },
  },
  components: {
    ...makeCssBaseline("light"),
    ...sharedComponents,
    MuiDrawer: {
      styleOverrides: {
        paper: {
          borderRight: "none",
          backgroundColor: "#eeecea",
        },
      },
    },
  },
});

export const darkTheme = createTheme({
  typography: sharedTypography,
  palette: {
    mode: "dark",
    primary: {
      main: "#d4993f",     // warm amber (brighter for dark bg)
      light: "#e6b35e",
      dark: "#b07a28",
      contrastText: "#1a1a1a",
    },
    secondary: {
      main: "#7d9ab8",     // slate blue
      light: "#a0b8d0",
      dark: "#5b7a9e",
    },
    background: {
      default: "#1a1c20",  // cool dark slate
      paper: "#24272c",    // slightly lighter
    },
    divider: "rgba(255, 255, 255, 0.08)",
    text: {
      primary: "#e2e0dd",
      secondary: "#8e8c88",
    },
  },
  components: {
    ...makeCssBaseline("dark"),
    ...sharedComponents,
    MuiDrawer: {
      styleOverrides: {
        paper: {
          borderRight: "none",
          backgroundColor: "#16181c",
        },
      },
    },
  },
});
