import { createTheme } from "@mui/material/styles";

// Shared overrides applied to both light and dark themes
const sharedComponents = {
  MuiCssBaseline: {
    styleOverrides: {
      body: { margin: 0 },
    },
  },
} as const;

export const lightTheme = createTheme({
  palette: {
    mode: "light",
  },
  components: sharedComponents,
});

export const darkTheme = createTheme({
  palette: {
    mode: "dark",
    background: {
      default: "#121212",
      paper: "#1e1e1e",
    },
  },
  components: sharedComponents,
});
