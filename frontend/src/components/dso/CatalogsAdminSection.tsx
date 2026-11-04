/**
 * Admin → Catalogs section.
 *
 * Shows every registered DSO catalog source as a row with per-source
 * fetch controls, followed by the optional catalogs available to add.
 */
import { useEffect, useRef, useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import Alert from "@mui/material/Alert";
import Box from "@mui/material/Box";
import Button from "@mui/material/Button";
import Chip from "@mui/material/Chip";
import CircularProgress from "@mui/material/CircularProgress";
import Dialog from "@mui/material/Dialog";
import DialogActions from "@mui/material/DialogActions";
import DialogContent from "@mui/material/DialogContent";
import DialogContentText from "@mui/material/DialogContentText";
import DialogTitle from "@mui/material/DialogTitle";
import Paper from "@mui/material/Paper";
import Stack from "@mui/material/Stack";
import Tooltip from "@mui/material/Tooltip";
import Typography from "@mui/material/Typography";
import {
  addOptionalCatalog,
  fetch50mgcFromGitHub,
  fetch50mgcRemoteVersion,
  fetchCatalogSources,
  fetchCatalogStatus,
  fetchCatalogsFromGitHub,
  fetchOptionalCatalogs,
  fetchRemovalPreview,
  fetchRemoteVersion,
  fetchWikidataExternalRefs,
  fetchWikidataRemoteVersion,
  reloadCatalogs,
  removeOptionalCatalog,
  type CatalogSource,
  type CatalogFetchStatus,
  type OptionalCatalogStatus,
  type RemovalPreview,
} from "@/api/dsos";
import { formatLocalDate } from "@/lib/localDate";

interface ActionButton {
  label: string;
  tooltip: string;
  variant: "contained" | "outlined";
  run: () => Promise<unknown>;
}

interface SourceRowProps {
  displayName: string;
  version: string | null;
  rowCount: number | null;
  license: string | null;
  /** Subtitle shown under the display name — e.g., the upstream host. */
  subtitle?: string;
  credit?: string;
  /** When truthy, an inline "Update available" chip renders next to the
   *  display name so users notice without hunting for a bumped version
   *  string. Sources that don't have a remote-version semantic (e.g.,
   *  in-repo bundled augment / external-refs CSV) simply never set
   *  this. ``tooltip`` lets the caller explain WHY an update is offered
   *  (new data upstream, query_version bump, first-run download, …). */
  updateAvailable?: boolean;
  updateTooltip?: string;
  /** Blocking message shown inline when the row's fetch fails. */
  error: string | null;
  onDismissError: () => void;
  /** In-flight marker to disable the buttons while the action runs. */
  busy: boolean;
  conflict: boolean;
  progress: string | null;
  actions: ActionButton[];
  onAction: (button: ActionButton) => void;
}

function SourceRow(props: SourceRowProps) {
  const {
    displayName,
    version,
    rowCount,
    license,
    subtitle,
    credit,
    updateAvailable,
    updateTooltip,
    actions,
    busy,
    conflict,
    progress,
    error,
    onDismissError,
    onAction,
  } = props;
  return (
    <Box
      sx={{
        display: "flex",
        flexDirection: { xs: "column", md: "row" },
        flexWrap: "wrap",
        alignItems: { md: "center" },
        gap: 1.5,
        py: 1.5,
        borderBottom: 1,
        borderColor: "divider",
        "&:last-of-type": { borderBottom: 0 },
      }}
    >
      <Box sx={{ flex: 1, minWidth: 0 }}>
        <Stack direction="row" alignItems="center" gap={1} flexWrap="wrap">
          <Typography variant="body2" fontWeight={600}>
            {displayName}
          </Typography>
          {updateAvailable && (
            <Tooltip
              title={updateTooltip ?? "A newer version is available upstream."}
              placement="top"
              arrow
            >
              <Chip
                label="Update available"
                size="small"
                color="primary"
                variant="outlined"
                sx={{
                  height: 20,
                  fontWeight: 500,
                  "& .MuiChip-label": { px: 0.85, fontSize: "0.7rem" },
                }}
              />
            </Tooltip>
          )}
        </Stack>
        {credit && (
          <Typography variant="caption" color="text.secondary" display="block">
            {credit}
          </Typography>
        )}
        <Typography variant="caption" color="text.secondary">
          {version ?? "Not loaded"}
          {rowCount != null && ` · ${rowCount.toLocaleString()} rows`}
          {license && ` · ${license}`}
          {subtitle && ` · ${subtitle}`}
        </Typography>
        {progress && (
          <Typography variant="caption" color="text.secondary" display="block">
            {progress}
          </Typography>
        )}
      </Box>
      <Box sx={{ display: "flex", gap: 1, flexWrap: "wrap" }}>
        {actions.map((btn) => (
          <Tooltip
            key={btn.label}
            title={conflict && !busy ? "Another catalog update is running." : btn.tooltip}
            placement="top"
          >
            <span>
              <Button
                size="small"
                variant={btn.variant}
                disabled={busy || conflict}
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
          {withRetryLater(error)}
        </Alert>
      )}
    </Box>
  );
}

type RowError = { [sourceId: string]: string | null };
type RowBusy = { [sourceId: string]: boolean };

interface RemovalDialogState {
  catalog: OptionalCatalogStatus;
  preview: RemovalPreview;
}

function formatMegabytes(bytes: number): string {
  return `${(bytes / 1_000_000).toFixed(1)} MB`;
}

function withRetryLater(message: string): string {
  const trimmed = message.trimEnd();
  return `${trimmed}${trimmed.endsWith(".") ? "" : "."} Try again later.`;
}

function formatProgress(status: CatalogFetchStatus): string {
  if (status.phase === "downloading" && status.bytes_received > 0) {
    const bytes = status.bytes_total != null
      ? `${(status.bytes_received / 1_000_000).toFixed(1)} of ${formatMegabytes(status.bytes_total)}`
      : `${formatMegabytes(status.bytes_received)} received`;
    return `${status.message} ${bytes}`;
  }
  if (
    status.outcome == null &&
    [
      "checking_release",
      "trying_source",
      "moving_source",
      "contacting",
      "waiting",
      "downloading",
    ].includes(status.phase)
  ) {
    return `${status.message} ${Math.floor(status.phase_elapsed_s)} s`;
  }
  return status.message;
}

function formatFetchedAt(value: string | null | undefined): string | null {
  const date = formatLocalDate(value);
  return date ? `Fetched ${date}` : null;
}

export default function CatalogsAdminSection() {
  const queryClient = useQueryClient();
  const [busy, setBusy] = useState<RowBusy>({});
  const [errors, setErrors] = useState<RowError>({});
  const [visibleStatus, setVisibleStatus] = useState<CatalogFetchStatus | null>(null);
  const [removalDialog, setRemovalDialog] = useState<RemovalDialogState | null>(null);
  const ignoredOperationIds = useRef(new Set<string>());
  const anyPending = Object.values(busy).some(Boolean);
  const operationActive = visibleStatus?.outcome == null && visibleStatus != null;

  const statusQuery = useQuery({
    queryKey: ["catalog-fetch-status"],
    queryFn: fetchCatalogStatus,
    retry: false,
    staleTime: 0,
    refetchOnMount: "always",
    refetchInterval: operationActive ? 1_000 : false,
  });

  useEffect(() => {
    if (statusQuery.isError) return;
    const incoming = statusQuery.data;
    if (incoming === undefined) return;
    if (incoming === null) {
      if (!anyPending) setVisibleStatus(null);
      return;
    }
    if (ignoredOperationIds.current.has(incoming.operation_id)) return;
    setVisibleStatus(incoming);
  }, [anyPending, statusQuery.data, statusQuery.isError]);

  useEffect(() => {
    if (!visibleStatus?.outcome) return;
    const remainingMs = Math.max(0, 300 - visibleStatus.phase_elapsed_s) * 1_000;
    const operationId = visibleStatus.operation_id;
    const timeout = window.setTimeout(() => {
      setVisibleStatus((current) =>
        current?.operation_id === operationId ? null : current,
      );
    }, remainingMs);
    return () => window.clearTimeout(timeout);
  }, [visibleStatus]);

  useEffect(() => {
    if (!visibleStatus?.outcome || !visibleStatus.detail) return;
    const sourceId =
      visibleStatus.action === "reload_all"
        ? "__all__"
        : visibleStatus.source ?? "__all__";
    setErrors((previous) => ({ ...previous, [sourceId]: visibleStatus.detail }));
  }, [visibleStatus]);

  const sourcesQuery = useQuery({
    queryKey: ["catalog-sources"],
    queryFn: fetchCatalogSources,
  });

  const optionalCatalogsQuery = useQuery({
    queryKey: ["optional-catalogs"],
    queryFn: fetchOptionalCatalogs,
  });

  const openngcRemote = useQuery({
    queryKey: ["catalog-remote-version"],
    queryFn: fetchRemoteVersion,
    staleTime: Infinity,
    retry: false,
  });

  const mgc50Remote = useQuery({
    queryKey: ["catalog-remote-version", "50mgc"],
    queryFn: fetch50mgcRemoteVersion,
    staleTime: Infinity,
    retry: false,
  });
  const wikidataRemote = useQuery({
    queryKey: ["catalog-remote-version", "wikidata"],
    queryFn: fetchWikidataRemoteVersion,
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
      queryClient.invalidateQueries({ queryKey: ["optional-catalogs"] }),
      // Blanket-invalidate the remote-version prefix so every source's
      // "Fetched <date>" label refreshes after any fetch.
      queryClient.invalidateQueries({ queryKey: ["catalog-remote-version"] }),
    ]);
  };

  async function runAction(sourceId: string, button: ActionButton) {
    if (visibleStatus && !visibleStatus.operation_id.startsWith("pending:")) {
      ignoredOperationIds.current.add(visibleStatus.operation_id);
    }
    const isReloadAll = sourceId === "__all__";
    setVisibleStatus({
      operation_id: `pending:${sourceId}:${Date.now()}`,
      action: isReloadAll ? "reload_all" : "pending",
      source: isReloadAll ? null : sourceId,
      phase: isReloadAll ? "reloading" : "starting",
      message: isReloadAll ? "Reloading cached catalogs…" : "Starting catalog update…",
      bytes_received: 0,
      bytes_total: null,
      phase_elapsed_s: 0,
      outcome: null,
      detail: null,
    });
    setBusy((prev) => ({ ...prev, [sourceId]: true }));
    setErrors((prev) => ({ ...prev, [sourceId]: null }));
    try {
      await button.run();
    } catch (err) {
      setErrors((prev) => ({
        ...prev,
        [sourceId]: err instanceof Error ? err.message : "Operation failed",
      }));
    } finally {
      setBusy((prev) => ({ ...prev, [sourceId]: false }));
      void statusQuery.refetch();
      void invalidateAll();
    }
  }

  async function previewRemoval(catalog: OptionalCatalogStatus) {
    const sourceId = catalog.catalog_id;
    setBusy((previous) => ({ ...previous, [sourceId]: true }));
    setErrors((previous) => ({ ...previous, [sourceId]: null }));
    try {
      const preview = await fetchRemovalPreview(sourceId);
      if (preview.blocked_reason) {
        setErrors((previous) => ({
          ...previous,
          [sourceId]: preview.blocked_reason,
        }));
        return;
      }
      setRemovalDialog({ catalog, preview });
    } catch (error) {
      setErrors((previous) => ({
        ...previous,
        [sourceId]: error instanceof Error ? error.message : "Operation failed",
      }));
    } finally {
      setBusy((previous) => ({ ...previous, [sourceId]: false }));
    }
  }

  const matchesOperation = (sourceId: string) => {
    if (!visibleStatus) return false;
    if (sourceId === "__all__") return visibleStatus.action === "reload_all";
    return visibleStatus.source === sourceId;
  };
  const isRowBusy = (sourceId: string) =>
    (busy[sourceId] ?? false) || (operationActive && matchesOperation(sourceId));
  const hasConflict = (sourceId: string) =>
    (anyPending || operationActive) && !isRowBusy(sourceId);
  const rowProgress = (sourceId: string) =>
    visibleStatus && matchesOperation(sourceId) ? formatProgress(visibleStatus) : null;

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
  };

  const optionalStatus = (catalog: OptionalCatalogStatus) => {
    if (catalog.state !== "on") return "Not added";
    if (!catalog.installed) return "Files missing — download again or remove";
    const added = catalog.kind === "nightcrate"
      ? "Ships with NightCrate"
      : `Added ${formatLocalDate(catalog.version) ?? catalog.version ?? "unknown date"}`;
    return `${added} · ${catalog.object_count.toLocaleString()} objects`;
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
          <Box sx={{ flex: 1 }}>
            <Typography variant="body2" color="text.secondary">
              OpenNGC and 50 MGC are downloaded from GitHub. The optional catalogs
              below come from VizieR when you add them: from CDS Strasbourg, or from
              its mirrors at Harvard, South Africa, Tokyo, Beijing and India. The
              Tokyo, Beijing and India mirrors use unencrypted connections.
              NightCrate&apos;s own lists, such as common names, distances and reviewed
              matches, come with the app.
            </Typography>
            {rowProgress("__all__") && (
              <Typography variant="caption" color="text.secondary" display="block">
                {rowProgress("__all__")}
              </Typography>
            )}
          </Box>
          <Tooltip
            title={
              hasConflict("__all__")
                ? "Another catalog update is running."
                : "Re-parse every catalog's cached local files into the database. Does NOT touch the network — useful after a schema change, or to restore rows if the database was wiped but the cached files under the app-data directory were kept. Covers OpenNGC, Sharpless, Barnard, 50 MGC, and the NightCrate augmentation in one pass."
            }
            placement="top"
          >
            <span>
              <Button
                size="small"
                variant="outlined"
                disabled={isRowBusy("__all__") || hasConflict("__all__")}
                onClick={() =>
                  runAction("__all__", {
                    label: "Reload all from local",
                    tooltip: "",
                    variant: "outlined",
                    run: reloadCatalogs,
                  })
                }
              >
                {isRowBusy("__all__") ? (
                  <CircularProgress size={16} color="inherit" />
                ) : (
                  "Reload all from local cache"
                )}
              </Button>
            </span>
          </Tooltip>
        </Stack>
        <Box
          aria-live="polite"
          sx={{
            position: "absolute",
            width: "1px",
            height: "1px",
            p: 0,
            m: -1,
            overflow: "hidden",
            clip: "rect(0 0 0 0)",
            whiteSpace: "nowrap",
            border: 0,
          }}
        >
          {visibleStatus?.message ?? ""}
        </Box>
        {errors["__all__"] && (
          <Alert
            severity="warning"
            onClose={() =>
              setErrors((prev) => ({ ...prev, __all__: null }))
            }
            sx={{ mb: 2 }}
          >
            {withRetryLater(errors["__all__"])}
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
          updateAvailable={openngcRemote.data?.has_update ?? false}
          updateTooltip={
            openngcInstalled == null
              ? "OpenNGC hasn't been fetched yet — the GitHub release is available to download."
              : `OpenNGC release ${openngcRemote.data?.latest_tag ?? ""} is newer than your installed ${openngcInstalled}. Click Fetch to update.`
          }
          error={errors["openngc"] ?? null}
          onDismissError={() => setErrors((prev) => ({ ...prev, openngc: null }))}
          busy={isRowBusy("openngc")}
          conflict={hasConflict("openngc")}
          progress={rowProgress("openngc")}
          actions={[openngcAction]}
          onAction={(btn) => runAction("openngc", btn)}
        />

        {/* 50 MGC — GitHub fetch (VizieR origin, GitHub mirror for reliability). */}
        <SourceRow
          displayName="50 Mpc Galaxy Catalog (Ohlson+ 2024)"
          version={
            formatFetchedAt(mgc50Remote.data?.installed_fetched_at) ??
            (mgc50Remote.isError ? "Status unknown" : null)
          }
          rowCount={sourcesById.get("github_50mgc")?.row_count ?? null}
          license={sourcesById.get("github_50mgc")?.license ?? "CDS public"}
          subtitle="github.com/davidohlson/50MGC"
          updateAvailable={mgc50Remote.data?.has_update ?? false}
          updateTooltip="50 MGC hasn't been fetched yet — click Fetch to download from GitHub."
          error={errors["github_50mgc"] ?? null}
          onDismissError={() => setErrors((prev) => ({ ...prev, github_50mgc: null }))}
          busy={isRowBusy("github_50mgc")}
          conflict={hasConflict("github_50mgc")}
          progress={rowProgress("github_50mgc")}
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

        {/* Wikidata — SPARQL fetch for DSO external references (v0.20.0,
            extended in v0.21.1 with SIMBAD + NED columns). */}
        <SourceRow
          displayName="Wikidata (external references)"
          version={
            formatFetchedAt(wikidataRemote.data?.installed_fetched_at) ??
            (wikidataRemote.isError ? "Status unknown" : null)
          }
          rowCount={sourcesById.get("wikidata_external_refs")?.row_count ?? null}
          license={sourcesById.get("wikidata_external_refs")?.license ?? "CC0-1.0"}
          subtitle="query.wikidata.org/sparql"
          updateAvailable={wikidataRemote.data?.has_update ?? false}
          updateTooltip={
            wikidataRemote.data?.installed_fetched_at == null
              ? "Wikidata hasn't been fetched yet — click Fetch to run the SPARQL query."
              : wikidataRemote.data?.installed_query_version !==
                wikidataRemote.data?.current_query_version
              ? `The SPARQL query has been extended since your last fetch (installed ${wikidataRemote.data?.installed_query_version ?? "?"} → current ${wikidataRemote.data?.current_query_version ?? "?"}). Fetching will pull the new columns (v0.21.1: SIMBAD + NED identifiers).`
              : "A fresh fetch will pull any new Wikidata entities added upstream since your last run."
          }
          error={errors["wikidata_external_refs"] ?? null}
          onDismissError={() =>
            setErrors((prev) => ({ ...prev, wikidata_external_refs: null }))
          }
          busy={isRowBusy("wikidata_external_refs")}
          conflict={hasConflict("wikidata_external_refs")}
          progress={rowProgress("wikidata_external_refs")}
          actions={[
            {
              label:
                wikidataRemote.data?.installed_fetched_at == null
                  ? "Fetch from Wikidata"
                  : "Re-fetch from Wikidata",
              tooltip: `${
                wikidataRemote.data?.installed_fetched_at == null
                  ? "Run"
                  : "Re-run"
              } the SPARQL query against query.wikidata.org to pull Wikipedia article links for every DSO with a matching catalog identifier (NGC / Messier / Sharpless 2 / Barnard / PGC / UGC). Takes ~30–60 s on first run. Wikidata data is CC0 (public domain); Wikipedia article content stays on wikipedia.org — only URLs are stored.`,
              variant: "contained",
              run: fetchWikidataExternalRefs,
            },
          ]}
          onAction={(btn) => runAction("wikidata_external_refs", btn)}
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
          busy={isRowBusy("nightcrate")}
          conflict={hasConflict("nightcrate")}
          progress={rowProgress("nightcrate")}
          actions={[]}
          onAction={(btn) => runAction("nightcrate", btn)}
        />

        {/* NightCrate external-refs override CSV (v0.20.0) — editorial
            overrides for Wikidata/Wikipedia matches. */}
        <SourceRow
          displayName="NightCrate external refs (editorial overrides)"
          version={
            sourcesById.has("nightcrate_external_refs") ? "Loaded" : "Not loaded"
          }
          rowCount={sourcesById.get("nightcrate_external_refs")?.row_count ?? null}
          license="MIT"
          subtitle="Bundled in-repo — overrides Wikidata"
          error={errors["nightcrate_external_refs"] ?? null}
          onDismissError={() =>
            setErrors((prev) => ({ ...prev, nightcrate_external_refs: null }))
          }
          busy={isRowBusy("nightcrate_external_refs")}
          conflict={hasConflict("nightcrate_external_refs")}
          progress={rowProgress("nightcrate_external_refs")}
          actions={[]}
          onAction={(btn) => runAction("nightcrate_external_refs", btn)}
        />

        <Box sx={{ mt: 1.5, pt: 2, borderTop: 1, borderColor: "divider" }}>
          <Typography
            variant="body2"
            color="text.secondary"
            fontWeight={500}
            sx={{ mb: 1, textTransform: "uppercase", letterSpacing: "0.05em", fontSize: "0.7rem" }}
          >
            Optional catalogs
          </Typography>
          {optionalCatalogsQuery.isError && (
            <Alert severity="warning" sx={{ mb: 1.5 }}>
              Optional catalogs could not be loaded. Try again in a moment.
            </Alert>
          )}
          {(optionalCatalogsQuery.data ?? []).map((catalog) => {
            const sourceId = catalog.catalog_id;
            const actions: ActionButton[] = catalog.state === "on"
              ? [
                  ...(catalog.kind === "vizier"
                    ? [{
                        label: "Download again",
                        tooltip: `Download ${catalog.display_name} again and replace its local files.`,
                        variant: "contained" as const,
                        run: () => addOptionalCatalog(sourceId),
                      }]
                    : []),
                  {
                    label: "Remove",
                    tooltip: `Remove ${catalog.display_name} from NightCrate.`,
                    variant: "outlined" as const,
                    run: async () => undefined,
                  },
                ]
              : [{
                  label: "Add",
                  tooltip: catalog.kind === "vizier"
                    ? `Download ${catalog.display_name} and add it to NightCrate.`
                    : `Add the ${catalog.display_name} list that ships with NightCrate.`,
                  variant: "contained" as const,
                  run: () => addOptionalCatalog(sourceId),
                }];
            return (
              <SourceRow
                key={sourceId}
                displayName={catalog.display_name}
                credit={catalog.credit}
                version={optionalStatus(catalog)}
                rowCount={null}
                license={null}
                error={errors[sourceId] ?? null}
                onDismissError={() =>
                  setErrors((previous) => ({ ...previous, [sourceId]: null }))
                }
                busy={isRowBusy(sourceId)}
                conflict={hasConflict(sourceId)}
                progress={rowProgress(sourceId)}
                actions={actions}
                onAction={(button) => {
                  if (button.label === "Remove") {
                    void previewRemoval(catalog);
                  } else {
                    void runAction(sourceId, button);
                  }
                }}
              />
            );
          })}
        </Box>
      </Paper>
      <Dialog
        open={removalDialog !== null}
        onClose={() => setRemovalDialog(null)}
        aria-labelledby="remove-catalog-title"
      >
        <DialogTitle id="remove-catalog-title">
          Remove {removalDialog?.catalog.display_name}?
        </DialogTitle>
        <DialogContent>
          <DialogContentText>
            {removalDialog?.preview.objects_removed ?? 0} objects will be removed.
            {(removalDialog?.preview.objects_kept ?? 0) > 0 && (
              <>
                {" "}
                {removalDialog?.preview.objects_kept} objects you linked to a project
                or the wishlist will stay, marked as no longer listed.
              </>
            )}
          </DialogContentText>
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setRemovalDialog(null)}>Cancel</Button>
          <Button
            variant="contained"
            onClick={() => {
              if (!removalDialog) return;
              const catalogId = removalDialog.catalog.catalog_id;
              setRemovalDialog(null);
              void runAction(catalogId, {
                label: "Remove",
                tooltip: "",
                variant: "contained",
                run: () => removeOptionalCatalog(catalogId),
              });
            }}
          >
            Remove
          </Button>
        </DialogActions>
      </Dialog>
    </>
  );
}
