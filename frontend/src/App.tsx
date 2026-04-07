import { useEffect } from "react";
import { createBrowserRouter, RouterProvider } from "react-router-dom";
import { ThemeProvider } from "@/components/ThemeProvider";
import { AppShell } from "@/components/AppShell";
import { HomePage } from "@/pages/HomePage";
import { ImageViewerPage } from "@/pages/ImageViewerPage";
import { SettingsPage } from "@/pages/SettingsPage";
import { ApiDocsPage } from "@/pages/ApiDocsPage";
import { EquipmentPage } from "@/pages/EquipmentPage";
import { useSettingsStore } from "@/stores/settingsStore";

const router = createBrowserRouter([
  {
    path: "/",
    element: <AppShell />,
    children: [
      { index: true, element: <HomePage /> },
      { path: "image-viewer", element: <ImageViewerPage /> },
      { path: "equipment", element: <EquipmentPage /> },
      { path: "equipment/:category", element: <EquipmentPage /> },
      { path: "settings", element: <SettingsPage /> },
      { path: "api-docs", element: <ApiDocsPage /> },
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
