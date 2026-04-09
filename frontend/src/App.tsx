import { useEffect } from "react";
import { createBrowserRouter, RouterProvider } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { ThemeProvider } from "@/components/ThemeProvider";
import { AppShell } from "@/components/AppShell";
import { HomePage } from "@/pages/HomePage";
import { ImageViewerPage } from "@/pages/ImageViewerPage";
import { SettingsPage } from "@/pages/SettingsPage";
import { ApiDocsPage } from "@/pages/ApiDocsPage";
import { EquipmentPage } from "@/pages/EquipmentPage";
import { useSettingsStore } from "@/stores/settingsStore";
import { fetchHealth } from "@/api/admin";
import { SetupWizard } from "@/components/SetupWizard";

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

function AppContent() {
  const load = useSettingsStore((s) => s.load);
  const { data: health, isLoading } = useQuery({
    queryKey: ["health"],
    queryFn: fetchHealth,
  });

  useEffect(() => {
    if (health?.db_configured) {
      load();
    }
  }, [health?.db_configured, load]);

  if (isLoading) return null;
  if (!health?.db_configured) return <SetupWizard />;

  return <RouterProvider router={router} />;
}

export default function App() {
  return (
    <ThemeProvider>
      <AppContent />
    </ThemeProvider>
  );
}
