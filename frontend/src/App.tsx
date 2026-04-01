import { useEffect } from "react";
import { createBrowserRouter, RouterProvider } from "react-router-dom";
import { ThemeProvider } from "@/components/ThemeProvider";
import { AppShell } from "@/components/AppShell";
import { HomePage } from "@/pages/HomePage";
import { ImageViewerPage } from "@/pages/ImageViewerPage";
import { SettingsPage } from "@/pages/SettingsPage";
import { useSettingsStore } from "@/stores/settingsStore";

const router = createBrowserRouter([
  {
    path: "/",
    element: <AppShell />,
    children: [
      { index: true, element: <HomePage /> },
      { path: "image-viewer", element: <ImageViewerPage /> },
      { path: "settings", element: <SettingsPage /> },
    ],
  },
]);

export default function App() {
  const load = useSettingsStore((s) => s.load);

  useEffect(() => {
    load();
  }, [load]);

  return (
    <ThemeProvider>
      <RouterProvider router={router} />
    </ThemeProvider>
  );
}
