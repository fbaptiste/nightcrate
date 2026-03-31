import CssBaseline from "@mui/material/CssBaseline";
import { ThemeProvider as MuiThemeProvider, useMediaQuery } from "@mui/material";
import { useMemo } from "react";
import { darkTheme, lightTheme } from "@/theme/theme";
import { useSettingsStore } from "@/stores/settingsStore";

export function ThemeProvider({ children }: { children: React.ReactNode }) {
  const settings = useSettingsStore((s) => s.settings);
  const prefersDark = useMediaQuery("(prefers-color-scheme: dark)");

  const theme = useMemo(() => {
    const mode = settings?.theme ?? "browser";
    if (mode === "dark") return darkTheme;
    if (mode === "light") return lightTheme;
    return prefersDark ? darkTheme : lightTheme; // "browser"
  }, [settings?.theme, prefersDark]);

  return (
    <MuiThemeProvider theme={theme}>
      <CssBaseline />
      {children}
    </MuiThemeProvider>
  );
}
