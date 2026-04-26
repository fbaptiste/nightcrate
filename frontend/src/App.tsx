import { useEffect } from "react";
import { createBrowserRouter, RouterProvider } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { ThemeProvider } from "@/components/ThemeProvider";
import { AppShell } from "@/components/AppShell";
import { HomePage } from "@/pages/HomePage";
import { SettingsPage } from "@/pages/SettingsPage";
import { ApiDocsPage } from "@/pages/ApiDocsPage";
import { EquipmentPage } from "@/pages/EquipmentPage";
import { AdminPage } from "@/pages/AdminPage";
import LocationsPage from "@/pages/LocationsPage";
import RigsPage from "@/pages/RigsPage";
import CalculatorsPage from "@/pages/CalculatorsPage";
import TonightPage from "@/pages/TonightPage";
import { useSettingsStore } from "@/stores/settingsStore";
import { useThumbnailCacheStore } from "@/stores/thumbnailCacheStore";
import { fetchHealth } from "@/api/admin";
import { fetchThumbnailCacheStats } from "@/api/planner";
import { SetupWizard } from "@/components/SetupWizard";

const router = createBrowserRouter([
  {
    path: "/",
    element: <AppShell />,
    children: [
      { index: true, element: <HomePage /> },
      { path: "image-viewer", element: null },
      { path: "equipment", element: <EquipmentPage /> },
      { path: "equipment/:category", element: <EquipmentPage /> },
      { path: "locations", element: <LocationsPage /> },
      { path: "rigs", element: <RigsPage /> },
      { path: "weather", element: null },
      { path: "calculators", element: <CalculatorsPage /> },
      { path: "calculators/:calcId", element: <CalculatorsPage /> },
      { path: "tonight", element: <TonightPage /> },
      { path: "catalog/dso", element: null },
      { path: "planner", element: null },
      { path: "phd2-analyzer", element: null },
      { path: "settings", element: <SettingsPage /> },
      { path: "admin", element: <AdminPage /> },
      { path: "api-docs", element: <ApiDocsPage /> },
    ],
  },
]);

function AppContent() {
  const load = useSettingsStore((s) => s.load);
  const setGeneration = useThumbnailCacheStore((s) => s.setGeneration);
  // Retry forever with exponential backoff capped at 3 s. In ``make
  // dev`` the frontend comes up before the backend (backend boots in
  // ~5 s while Vite is ready in <200 ms); without this the 3-default-
  // retries burn through during the first second and the page
  // permanently renders the SetupWizard because ``health`` is
  // ``undefined``. Gating the wizard on ``isSuccess`` below means the
  // wizard only shows when the backend has explicitly told us the
  // DB isn't configured.
  const healthQuery = useQuery({
    queryKey: ["health"],
    queryFn: fetchHealth,
    retry: Infinity,
    retryDelay: (attempt) => Math.min(250 * 2 ** attempt, 3000),
  });
  const health = healthQuery.data;

  const { data: thumbnailStats } = useQuery({
    queryKey: ["thumbnail-cache-stats"],
    queryFn: fetchThumbnailCacheStats,
    enabled: health?.db_configured === true,
    staleTime: Infinity,
  });
  useEffect(() => {
    if (thumbnailStats?.generation != null) {
      setGeneration(thumbnailStats.generation);
    }
  }, [thumbnailStats?.generation, setGeneration]);

  useEffect(() => {
    if (health?.db_configured) {
      load();
    }
  }, [health?.db_configured, load]);

  if (!healthQuery.isSuccess) return null;
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
