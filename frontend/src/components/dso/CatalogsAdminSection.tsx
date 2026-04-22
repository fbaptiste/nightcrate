/**
 * Admin → Catalogs section.
 *
 * Shows every registered DSO catalog source as a row with per-source
 * fetch controls. OpenNGC fetches from GitHub; VizieR sources (Sharpless,
 * Barnard / 50 MGC) fetch from vizier.cds.unistra.fr; NightCrate
 * sources are bundled in-repo and only expose a "Reload" action.
 */
import { useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import Alert from "@mui/material/Alert";
import Box from "@mui/material/Box";
import Button from "@mui/material/Button";
import CircularProgress from "@mui/material/CircularProgress";
import Paper from "@mui/material/Paper";
import Stack from "@mui/material/Stack";
import Tooltip from "@mui/material/Tooltip";
import Typography from "@mui/material/Typography";
import {
  fetch50mgcFromGitHub,
  fetch50mgcRemoteVersion,
  fetchCatalogSources,
  fetchCatalogsFromGitHub,
  fetchRemoteVersion,
  fetchVizierCatalog,
  fetchVizierRemoteVersion,
  reloadCatalogs,
  type CatalogSource,
  type VizierSourceShortId,
} from "@/api/dsos";

interface ActionButton {
  label: string;
  tooltip: string;
  variant: "contained" | "outlined";
  run: () => Promise<unknown>;
  refreshRemoteVersion?: boolean;
  refreshVizierId?: VizierSourceShortId;
}

interface SourceRowProps {
  displayName: string;
  version: string | null;
  rowCount: number | null;
  license: string | null;
  /** Subtitle shown under the display name — e.g., the upstream host. */
  subtitle?: string;
  /** Blocking message shown inline when the row's fetch fails. */
  error: string | null;
  onDismissError: () => void;
  /** In-flight marker to disable the buttons while the action runs. */
  busy: boolean;
  actions: ActionButton[];
  onAction: (button: ActionButton) => void;
}

function SourceRow(props: SourceRowProps) {
  const { displayName, version, rowCount, license, subtitle, actions, busy, error, onDismissError, onAction } =
    props;
  return (
    <Box
      sx={{
        display: "flex",
        flexDirection: { xs: "column", md: "row" },
        alignItems: { md: "center" },
        gap: 1.5,
        py: 1.5,
        borderBottom: 1,
        borderColor: "divider",
        "&:last-of-type": { borderBottom: 0 },
      }}
    >
      <Box sx={{ flex: 1, minWidth: 0 }}>
        <Typography variant="body2" fontWeight={600}>
          {displayName}
        </Typography>
        <Typography variant="caption" color="text.secondary">
          {version ?? "Not loaded"}
          {rowCount != null && ` · ${rowCount.toLocaleString()} rows`}
          {license && ` · ${license}`}
          {subtitle && ` · ${subtitle}`}
        </Typography>
      </Box>
      <Box sx={{ display: "flex", gap: 1, flexWrap: "wrap" }}>
        {actions.map((btn) => (
          <Tooltip key={btn.label} title={btn.tooltip} placement="top">
            <span>
              <Button
                size="small"
                variant={btn.variant}
                disabled={busy}
                onClick={() => onAction(btn)}
              >
                {busy ? (
                  <CircularProgress size={16} color="inherit" />
                ) : (
                  btn.label
                )}
              </Button>
            </span>
          </Tooltip>
        ))}
      </Box>
      {error && (
        <Alert
          severity="warning"
          onClose={onDismissError}
          sx={{ flexBasis: "100%" }}
        >
          {error} — try again in a moment.
        </Alert>
      )}
    </Box>
  );
}

type RowError = { [sourceId: string]: string | null };
type RowBusy = { [sourceId: string]: boolean };

export default function CatalogsAdminSection() {
  const queryClient = useQueryClient();
  const [busy, setBusy] = useState<RowBusy>({});
  const [errors, setErrors] = useState<RowError>({});

  const sourcesQuery = useQuery({
    queryKey: ["catalog-sources"],
    queryFn: fetchCatalogSources,
  });

  const openngcRemote = useQuery({
    queryKey: ["catalog-remote-version"],
    queryFn: fetchRemoteVersion,
    staleTime: Infinity,
    retry: false,
  });

  const sharplessRemote = useQuery({
    queryKey: ["catalog-remote-version", "sharpless"],
    queryFn: () => fetchVizierRemoteVersion("sharpless"),
    staleTime: Infinity,
    retry: false,
  });
  const barnardRemote = useQuery({
    queryKey: ["catalog-remote-version", "barnard"],
    queryFn: () => fetchVizierRemoteVersion("barnard"),
    staleTime: Infinity,
    retry: false,
  });
  const mgc50Remote = useQuery({
    queryKey: ["catalog-remote-version", "50mgc"],
    queryFn: fetch50mgcRemoteVersion,
    staleTime: Infinity,
    retry: false,
  });
  const sourcesById = new Map<string, CatalogSource>();
  (sourcesQuery.data ?? []).forEach((s) => sourcesById.set(s.source_id, s));

  const invalidateAll = async () => {
    await Promise.all([
      queryClient.invalidateQueries({ queryKey: ["dsos"] }),
      queryClient.invalidateQueries({ queryKey: ["dso-facets"] }),
      queryClient.invalidateQueries({ queryKey: ["catalog-sources"] }),
    ]);
  };

  async function runAction(sourceId: string, button: ActionButton) {
    setBusy((prev) => ({ ...prev, [sourceId]: true }));
    setErrors((prev) => ({ ...prev, [sourceId]: null }));
    try {
      await button.run();
      await invalidateAll();
      if (button.refreshRemoteVersion) {
        await queryClient.invalidateQueries({ queryKey: ["catalog-remote-version"] });
      }
      if (button.refreshVizierId) {
        await queryClient.invalidateQueries({
          queryKey: ["catalog-remote-version", button.refreshVizierId],
        });
      }
    } catch (err) {
      setErrors((prev) => ({
        ...prev,
        [sourceId]: err instanceof Error ? err.message : "Operation failed",
      }));
    } finally {
      setBusy((prev) => ({ ...prev, [sourceId]: false }));
    }
  }

  // Build row definitions in the same load order used by the backend loader.
  const openngcSrc = sourcesById.get("openngc");
  const openngcInstalled = openngcRemote.data?.installed_version;
  const openngcAction: ActionButton = {
    label:
      openngcInstalled == null
        ? "Fetch from GitHub"
        : openngcRemote.data?.has_update
        ? "Fetch update from GitHub"
        : "Re-fetch from GitHub",
    tooltip:
      openngcInstalled == null
        ? "Download the latest OpenNGC release from github.com/mattiaverga/OpenNGC into the local cache, then parse it into the database."
        : openngcRemote.data?.has_update
        ? "Download the newer OpenNGC release from GitHub over your existing local cache, then parse it into the database."
        : "Re-download the current OpenNGC release from GitHub, overwriting the local cache, then parse it into the database.",
    variant: "contained",
    run: fetchCatalogsFromGitHub,
    refreshRemoteVersion: true,
  };

  const buildVizierRow = (
    sourceId: string,
    shortId: VizierSourceShortId,
    remote: typeof sharplessRemote,
    displayName: string,
    catalogLabel: string,
  ) => {
    const backendSrc = sourcesById.get(sourceId);
    const installed = remote.data?.installed_version;
    const fetchBtn: ActionButton = {
      label: installed == null ? "Fetch from VizieR" : "Re-fetch from VizieR",
      tooltip: `${
        installed == null ? "Download" : "Re-download"
      } ${catalogLabel} over the network from vizier.cds.unistra.fr (with India + South Africa mirrors as fallback), replacing the local cache, then parse it into the database.`,
      variant: "contained",
      run: () => fetchVizierCatalog(shortId),
      refreshVizierId: shortId,
    };
    return (
      <SourceRow
        key={sourceId}
        displayName={displayName}
        version={
          installed
            ? `Fetched ${installed.slice(0, 10)}`
            : remote.isError
            ? "VizieR unreachable"
            : null
        }
        rowCount={backendSrc?.row_count ?? null}
        license={backendSrc?.license ?? "CDS public"}
        subtitle={remote.data?.catalog_id}
        error={errors[sourceId] ?? null}
        onDismissError={() => setErrors((prev) => ({ ...prev, [sourceId]: null }))}
        busy={busy[sourceId] ?? false}
        actions={[fetchBtn]}
        onAction={(btn) => runAction(sourceId, btn)}
      />
    );
  };

  return (
    <>
      <Typography variant="h6" sx={{ mb: 1, mt: 3 }}>
        Catalogs
      </Typography>
      <Paper sx={{ p: 2 }}>
        <Stack
          direction={{ xs: "column", sm: "row" }}
          alignItems={{ sm: "center" }}
          gap={2}
          sx={{ mb: 2 }}
        >
          <Typography variant="body2" color="text.secondary" sx={{ flex: 1 }}>
            NightCrate does not ship deep-sky object data. Catalogs are fetched
            on demand — OpenNGC from GitHub, Sharpless / Barnard / 50 MGC from
            the VizieR service at CDS Strasbourg. NightCrate editorial
            augmentation (common names, non-galaxy surface brightness, curated
            distances) is bundled in-repo.
          </Typography>
          <Tooltip
            title="Re-parse every catalog's cached local files into the database. Does NOT touch the network — useful after a schema change, or to restore rows if the database was wiped but the cached files under the app-data directory were kept. Covers OpenNGC, Sharpless, Barnard, 50 MGC, and the NightCrate augmentation in one pass."
            placement="top"
          >
            <span>
              <Button
                size="small"
                variant="outlined"
                disabled={busy["__all__"] ?? false}
                onClick={() =>
                  runAction("__all__", {
                    label: "Reload all from local",
                    tooltip: "",
                    variant: "outlined",
                    run: reloadCatalogs,
                  })
                }
              >
                {busy["__all__"] ? (
                  <CircularProgress size={16} color="inherit" />
                ) : (
                  "Reload all from local cache"
                )}
              </Button>
            </span>
          </Tooltip>
        </Stack>
        {errors["__all__"] && (
          <Alert
            severity="warning"
            onClose={() =>
              setErrors((prev) => ({ ...prev, __all__: null }))
            }
            sx={{ mb: 2 }}
          >
            {errors["__all__"]} — try again in a moment.
          </Alert>
        )}

        {/* OpenNGC */}
        <SourceRow
          displayName={openngcSrc?.display_name ?? "OpenNGC (NGC / IC / Messier)"}
          version={openngcInstalled ?? null}
          rowCount={openngcSrc?.row_count ?? null}
          license={openngcSrc?.license ?? "CC-BY-SA-4.0"}
          subtitle={
            openngcRemote.isError
              ? "GitHub unreachable"
              : openngcRemote.data
              ? `Latest on GitHub: ${openngcRemote.data.latest_tag}`
              : undefined
          }
          error={errors["openngc"] ?? null}
          onDismissError={() => setErrors((prev) => ({ ...prev, openngc: null }))}
          busy={busy["openngc"] ?? false}
          actions={[openngcAction]}
          onAction={(btn) => runAction("openngc", btn)}
        />

        {/* VizieR sources. */}
        {buildVizierRow(
          "vizier_sharpless",
          "sharpless",
          sharplessRemote,
          "Sharpless 2 (VizieR VII/20)",
          "the Sharpless 2 HII-region catalog",
        )}
        {buildVizierRow(
          "vizier_barnard",
          "barnard",
          barnardRemote,
          "Barnard (VizieR VII/220A)",
          "the Barnard dark-nebula catalog",
        )}

        {/* 50 MGC — GitHub fetch (VizieR origin, GitHub mirror for reliability). */}
        <SourceRow
          displayName="50 Mpc Galaxy Catalog (Ohlson+ 2024)"
          version={
            mgc50Remote.data?.installed_fetched_at
              ? `Fetched ${mgc50Remote.data.installed_fetched_at.slice(0, 10)}`
              : mgc50Remote.isError
              ? "Status unknown"
              : null
          }
          rowCount={sourcesById.get("github_50mgc")?.row_count ?? null}
          license={sourcesById.get("github_50mgc")?.license ?? "CDS public"}
          subtitle="github.com/davidohlson/50MGC"
          error={errors["github_50mgc"] ?? null}
          onDismissError={() => setErrors((prev) => ({ ...prev, github_50mgc: null }))}
          busy={busy["github_50mgc"] ?? false}
          actions={[
            {
              label:
                mgc50Remote.data?.installed_fetched_at == null
                  ? "Fetch from GitHub"
                  : "Re-fetch from GitHub",
              tooltip: `${
                mgc50Remote.data?.installed_fetched_at == null
                  ? "Download"
                  : "Re-download"
              } the 50 Mpc Galaxy Catalog FITS file from github.com/davidohlson/50MGC (the authors' mirror of the VizieR original, used for reliability), replacing the local cache, then parse it into the database.`,
              variant: "contained",
              run: fetch50mgcFromGitHub,
            },
          ]}
          onAction={(btn) => runAction("github_50mgc", btn)}
        />

        {/* NightCrate bundled — no separate reload button; covered by
            the "Reload all from local cache" action at the top. */}
        <SourceRow
          displayName="NightCrate editorial augmentation"
          version={sourcesById.has("nightcrate_augment") ? "Loaded" : "Not loaded"}
          rowCount={sourcesById.get("nightcrate_augment")?.row_count ?? null}
          license="MIT"
          subtitle="Bundled in-repo"
          error={errors["nightcrate"] ?? null}
          onDismissError={() => setErrors((prev) => ({ ...prev, nightcrate: null }))}
          busy={busy["nightcrate"] ?? false}
          actions={[]}
          onAction={(btn) => runAction("nightcrate", btn)}
        />
      </Paper>
    </>
  );
}
