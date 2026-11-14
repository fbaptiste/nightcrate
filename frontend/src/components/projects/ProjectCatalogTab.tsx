import { useCallback, useMemo, useRef, useState } from "react";
import {
  useInfiniteQuery,
  useMutation,
  useQuery,
  useQueryClient,
} from "@tanstack/react-query";
import Alert from "@mui/material/Alert";
import Dialog from "@mui/material/Dialog";
import DialogActions from "@mui/material/DialogActions";
import DialogContent from "@mui/material/DialogContent";
import DialogTitle from "@mui/material/DialogTitle";
import Box from "@mui/material/Box";
import Button from "@mui/material/Button";
import Checkbox from "@mui/material/Checkbox";
import FormControlLabel from "@mui/material/FormControlLabel";
import Chip from "@mui/material/Chip";
import MenuItem from "@mui/material/MenuItem";
import TextField from "@mui/material/TextField";
import CircularProgress from "@mui/material/CircularProgress";
import { fetchRigs } from "@/api/rigs";
import { invalidateProjectInfo } from "@/api/projectInfo";
import { fetchProject, fetchProjectRigSetups } from "@/api/projects";
import { listProjectTargets } from "@/api/projectTargets";
import Snackbar from "@mui/material/Snackbar";
import Stack from "@mui/material/Stack";
import Tab from "@mui/material/Tab";
import Tabs from "@mui/material/Tabs";
import Tooltip from "@mui/material/Tooltip";
import Typography from "@mui/material/Typography";
import LinearProgress from "@mui/material/LinearProgress";
import DeleteIcon from "@mui/icons-material/Delete";
import RefreshIcon from "@mui/icons-material/Refresh";
import AutoAwesomeIcon from "@mui/icons-material/AutoAwesome";
import ViewListIcon from "@mui/icons-material/ViewList";
import GridViewIcon from "@mui/icons-material/GridView";
import ToggleButton from "@mui/material/ToggleButton";
import ToggleButtonGroup from "@mui/material/ToggleButtonGroup";
import { FileBrowser } from "@/components/fits/FileBrowser";
import AnalyzerOverlay, { type AnalyzerItem } from "./AnalyzerOverlay";
import FrameCorrectionsDialog from "./FrameCorrectionsDialog";
import { formatExposure } from "./CatalogCards";
import FilterSwatch from "./FilterSwatch";
import CatalogFrameTable from "./CatalogFrameTable";
import CatalogThumbnailSheet from "./CatalogThumbnailSheet";
import CatalogMasterTable from "./CatalogMasterTable";
import CatalogOtherTable from "./CatalogOtherTable";
import UncatalogedFileTable from "./UncatalogedFileTable";
import {
  fileSelectionKey,
  processedImageSelectionKey,
  selectionId,
  selectionKind,
  subFrameSelectionKey,
  type CatalogSelectionKey,
} from "./catalogSelection";
import {
  addFolder,
  deleteCatalogItems,
  fetchCatalogFilterSummary,
  fetchCatalogFrames,
  fetchCatalogMasters,
  fetchCatalogOthers,
  fetchCatalogSummary,
  fetchUncatalogedFiles,
  fetchQualityCounts,
  isMaster,
  isSubFrame,
  listFolders,
  removeFolder,
  setFolderRig,
  setFolderTarget,
  startIngest,
  type CatalogFrame,
  type FramePill,
  type CatalogItem,
  type CatalogMaster,
  type CatalogOther,
  type CatalogSort,
} from "@/api/projectCatalog";
import { useAnalyzeRun } from "@/lib/useAnalyzeRun";
import { RIG_BLUE } from "@/lib/rigColors";
import {
  compareFilters,
  notRecordedFilter,
  resolveFilterLabel,
} from "./filterColors";

interface Props {
  projectId: number;
}

const PAGE_SIZE = 60;

function framePillKey(pill: FramePill | null): string {
  if (!pill) return "";
  return pill.kind === "name" ? `name:${pill.name}` : "not-recorded";
}

function framePillsEqual(left: FramePill | null, right: FramePill | null): boolean {
  return framePillKey(left) === framePillKey(right);
}

/** Coarse "time left" for the analyze run — seconds under a minute, else minutes. */
function formatEta(seconds: number): string {
  if (seconds < 60) return `${Math.max(1, seconds)}s`;
  return `${Math.round(seconds / 60)} min`;
}

function folderName(path: string): string {
  const parts = path.split(/[\\/]/).filter(Boolean);
  return parts[parts.length - 1] ?? path;
}

type TabKey =
  | "light"
  | "dark"
  | "flat"
  | "dark_flat"
  | "bias"
  | "masters"
  | "others"
  | "uncataloged";

/** Singular and plural nouns per tab, for scope-stating Analyze labels.
 *  Exhaustive on purpose — adding a TabKey must not silently fall through. */
const TAB_NOUNS: Record<TabKey, { singular: string; plural: string }> = {
  light: { singular: "light", plural: "lights" },
  dark: { singular: "dark", plural: "darks" },
  flat: { singular: "flat", plural: "flats" },
  dark_flat: { singular: "dark flat", plural: "dark flats" },
  bias: { singular: "bias frame", plural: "bias frames" },
  masters: { singular: "master", plural: "masters" },
  others: { singular: "file", plural: "files" },
  uncataloged: { singular: "file not cataloged", plural: "files not cataloged" },
};

interface CatalogPage {
  rows: CatalogItem[];
  total: number;
  timezone: string;
}

function itemSelectionKey(item: CatalogItem): CatalogSelectionKey {
  if (isMaster(item)) return processedImageSelectionKey(item.id);
  if (isSubFrame(item)) return subFrameSelectionKey(item.id);
  return fileSelectionKey(item.id);
}

export default function ProjectCatalogTab({ projectId }: Props) {
  const queryClient = useQueryClient();
  const [snack, setSnack] = useState<string | null>(null);
  const [pickerOpen, setPickerOpen] = useState(false);
  // A folder chosen in the browser, held until its rig is declared.
  const [pendingPath, setPendingPath] = useState<string | null>(null);
  const [pendingRigId, setPendingRigId] = useState<number | "">("");
  const [pendingTargetId, setPendingTargetId] = useState<number | "">("");
  const [tab, setTab] = useState<TabKey>("light");
  const [lightView, setLightView] = useState<"table" | "thumbnails">("table");
  // Active filter-pill scope on the Lights / Flats lists (null = show all).
  const [filterPill, setFilterPill] = useState<FramePill | null>(null);
  // Server-side ordering (null = the per-tab default). Client-side sorting would
  // only order the pages already loaded, which is wrong for "worst first".
  const [sort, setSort] = useState<CatalogSort>("date_desc");
  // Others tab: hide the non-frame files (PixInsight .xnml/.xdrz sidecars, logs)
  // so the handful of unclassified frames is actually findable.
  const [unclassifiedOnly, setUnclassifiedOnly] = useState(false);

  // Multi-select for bulk corrections. Cleared whenever the visible set changes,
  // so a hidden selection can never be acted on by mistake.
  const [selected, setSelected] = useState<Set<CatalogSelectionKey>>(new Set());
  const itemsRef = useRef<CatalogItem[]>([]);
  const lastSelectedRef = useRef<CatalogSelectionKey | null>(null);

  const clearSelection = useCallback(() => {
    setSelected(new Set());
    lastSelectedRef.current = null;
  }, []);

  const changeTab = (next: TabKey, opts?: { unclassifiedOnly?: boolean }) => {
    setTab(next);
    setFilterPill(null);
    setSort("date_desc");
    setUnclassifiedOnly(opts?.unclassifiedOnly ?? false);
    clearSelection();
  };

  const changeFilterPill = (next: FramePill | null) => {
    setFilterPill(next);
    clearSelection();
  };

  // Read through refs so this callback's identity never changes: it is passed to
  // every memoized row, which should not all re-render on one selection change.
  /** Toggle one row, or with shift extend from the last one clicked.
   *
   *  The range spans the rows currently LOADED — scroll far enough to load the
   *  far end first, which is what the gesture implies anyway. Shift always adds
   *  rather than replacing, so several ranges can be built up. */
  const toggleSelect = useCallback((key: CatalogSelectionKey, shift = false) => {
    setSelected((prev) => {
      const next = new Set(prev);
      const anchor = lastSelectedRef.current;
      if (shift && anchor != null && anchor !== key) {
        const keys = itemsRef.current.map(itemSelectionKey);
        const from = keys.indexOf(anchor);
        const to = keys.indexOf(key);
        if (from >= 0 && to >= 0) {
          for (const rangeKey of keys.slice(Math.min(from, to), Math.max(from, to) + 1)) {
            next.add(rangeKey);
          }
          return next;
        }
      }
      if (next.has(key)) next.delete(key);
      else next.add(key);
      return next;
    });
    lastSelectedRef.current = key;
  }, []);

  const { data: folders = [] } = useQuery({
    queryKey: ["project-folders", projectId],
    queryFn: () => listFolders(projectId),
  });
  const { data: summary } = useQuery({
    queryKey: ["project-catalog-summary", projectId],
    queryFn: () => fetchCatalogSummary(projectId),
  });
  const uncatalogedQuery = useQuery({
    queryKey: ["project-catalog-uncataloged", projectId],
    queryFn: () => fetchUncatalogedFiles(projectId),
    enabled: tab === "uncataloged",
  });
  // The project's targets are the only values a folder's target tag may take.
  const { data: projectTargets = [] } = useQuery({
    queryKey: ["project-targets", projectId],
    queryFn: () => listProjectTargets(projectId),
  });
  const { data: project } = useQuery({
    queryKey: ["project", projectId],
    queryFn: () => fetchProject(projectId),
  });
  const { data: projectRigSetups = [] } = useQuery({
    queryKey: ["project-rig-setups", projectId],
    queryFn: () => fetchProjectRigSetups(projectId),
  });
  const targetLabel = (t: { common_name: string | null; primary_designation: string }) =>
    t.common_name ?? t.primary_designation;

  const {
    data,
    isLoading,
    fetchNextPage,
    hasNextPage,
    isFetchingNextPage,
  } = useInfiniteQuery({
    queryKey: ["project-catalog", projectId, tab, filterPill, sort, unclassifiedOnly],
    initialPageParam: 0,
    queryFn: async ({ pageParam }): Promise<CatalogPage> => {
      const off = pageParam;
      if (tab === "masters") return fetchCatalogMasters(projectId, PAGE_SIZE, off);
      if (tab === "others")
        return fetchCatalogOthers(projectId, PAGE_SIZE, off, unclassifiedOnly);
      if (tab === "uncataloged") {
        return { rows: [], total: 0, timezone: "UTC" };
      }
      return fetchCatalogFrames(projectId, PAGE_SIZE, off, tab, filterPill, sort);
    },
    getNextPageParam: (_last, allPages) => {
      const loaded = allPages.reduce((n, p) => n + p.rows.length, 0);
      return loaded < (allPages[0]?.total ?? 0) ? loaded : undefined;
    },
    enabled: tab !== "uncataloged",
  });
  // Memoized: `items` feeds `analyzerItems` -> `openInAnalyzer` -> every row's
  // `onOpen`. A fresh array each render would change that prop's identity and
  // defeat row memoization on every checkbox tick and analyzer step.
  const items: CatalogItem[] = useMemo(() => data?.pages.flatMap((p) => p.rows) ?? [], [data]);
  // Kept current for `toggleSelect`, which reads it through the ref so its own
  // identity can stay stable across renders.
  itemsRef.current = items;
  const tz = tab === "uncataloged"
    ? uncatalogedQuery.data?.timezone ?? "UTC"
    : data?.pages[0]?.timezone ?? "UTC";

  // Per-filter pills (count + total exposure) for the Lights & Flats tabs.
  const showFilterPills = tab === "light" || tab === "flat";
  const { data: filterStats = [] } = useQuery({
    queryKey: ["project-catalog-filters", projectId, tab],
    queryFn: () => fetchCatalogFilterSummary(projectId, tab as "light" | "flat"),
    enabled: showFilterPills,
  });
  const orderedFilterStats = useMemo(
    () =>
      [...filterStats].sort((a, b) => {
        const aFilter = a.filter_name ? resolveFilterLabel(a.filter_name) : notRecordedFilter();
        const bFilter = b.filter_name ? resolveFilterLabel(b.filter_name) : notRecordedFilter();
        return compareFilters(aFilter, bFilter);
      }),
    [filterStats],
  );

  /** Counts only — the row itself is patched in place by `patchFrameRow`.
   *
   * The analyze button's label is driven by the counts query, so it has to move
   * with the others: a frame_type correction shifts a frame between tabs, and
   * missing this left "Re-analyze 2,548 lights" on screen after every frame had
   * been removed with its source folder.
   */
  const invalidateCounts = () => {
    queryClient.invalidateQueries({
      queryKey: ["project-catalog-summary", projectId],
    });
    queryClient.invalidateQueries({
      queryKey: ["project-catalog-filters", projectId],
    });
    queryClient.invalidateQueries({ queryKey: ["quality-counts", projectId] });
    queryClient.invalidateQueries({
      queryKey: ["project-catalog-uncataloged", projectId],
    });
  };

  /** The counts above, plus the row data itself. */
  const invalidateCatalog = () => {
    invalidateCounts();
    queryClient.invalidateQueries({ queryKey: ["project-catalog", projectId] });
  };

  const invalidateRigDependent = () => {
    queryClient.invalidateQueries({ queryKey: ["rigs"] });
    queryClient.invalidateQueries({ queryKey: ["rig-setups"] });
    queryClient.invalidateQueries({ queryKey: ["project-rig-setups", projectId] });
    queryClient.invalidateQueries({ queryKey: ["project", projectId] });
    invalidateCatalog();
    queryClient.invalidateQueries({ queryKey: ["project-sessions", projectId] });
    queryClient.invalidateQueries({ queryKey: ["project-integration", projectId] });
    queryClient.invalidateQueries({ queryKey: ["project-solve", projectId] });
    void invalidateProjectInfo(queryClient, projectId);
    queryClient.invalidateQueries({ queryKey: ["equipment-usage"] });
  };

  /** Replace one row in the loaded pages instead of refetching the whole
   *  infinite query. A full invalidate refetches EVERY page already loaded, so
   *  editing one row after scrolling 20 pages cost 20 round-trips. */
  const patchFrameRow = (updated: CatalogFrame) => {
    queryClient.setQueryData<{ pages: CatalogPage[]; pageParams: unknown[] }>(
      ["project-catalog", projectId, tab, filterPill, sort, unclassifiedOnly],
      (old) =>
        old
          ? {
              ...old,
              pages: old.pages.map((p) => ({
                ...p,
                rows: p.rows.map((r) =>
                  isSubFrame(r) && r.id === updated.id
                    ? updated
                    : r,
                ),
              })),
            }
          : old,
    );
    invalidateCounts();
  };

  const invalidateFolders = () =>
    queryClient.invalidateQueries({ queryKey: ["project-folders", projectId] });

  // Which folder row is currently (re-)scanning, for its inline spinner.
  const [scanningFolderId, setScanningFolderId] = useState<number | null>(null);
  const ingestMut = useMutation({
    mutationFn: (folderId: number) => startIngest(projectId, folderId),
    onMutate: (folderId: number) => setScanningFolderId(folderId),
    onSuccess: (s) => {
      invalidateRigDependent();
      setSnack(
        `Scan ${s.status}: ${s.subs_inserted} new, ${s.subs_updated} updated` +
          (s.errors_count ? `, ${s.errors_count} errors` : "") +
          (s.first_error ? ` — ${s.first_error}` : ""),
      );
    },
    onError: (e: Error) => setSnack(e.message),
    onSettled: () => setScanningFolderId(null),
  });
  // ── Frame quality analysis (v0.41.3) ────────────────────────────────────────
  // Scope is whatever the list is showing: the active sub-tab plus the filter
  // pill, so the button label states exactly what it will do.
  const isFrameTab = tab !== "masters" && tab !== "others" && tab !== "uncataloged";
  const { data: qCounts } = useQuery({
    queryKey: ["quality-counts", projectId, tab, filterPill],
    queryFn: () => fetchQualityCounts(projectId, tab, filterPill),
    enabled: isFrameTab,
  });

  /** "276 Blue lights" — states the scope so the button needs no explanation. */
  const scopeNoun = (count: number) => {
    const noun = TAB_NOUNS[tab][count === 1 ? "singular" : "plural"];
    return filterPill?.kind === "notRecorded"
      ? `${noun} with no filter recorded`
      : `${filterPill?.kind === "name" ? `${filterPill.name} ` : ""}${noun}`;
  };

  const onAnalyzeFinished = useCallback(
    (p: { analyzed: number; noStars: number; unreadable: number; errors: string[] }) => {
      invalidateCatalog();
      if (p.errors.length && p.analyzed === 0) {
        setSnack(p.errors[0]);
        return;
      }
      setSnack(
        `Analyzed ${p.analyzed.toLocaleString()} frames` +
          (p.noStars ? `, ${p.noStars} with no stars` : "") +
          (p.unreadable ? `, ${p.unreadable} unreadable` : ""),
      );
    },
    // invalidateCatalog is stable in practice (queryClient + projectId).
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [projectId],
  );
  const { progress: analyzeProgress, start: startAnalyze, cancel: cancelAnalyze } =
    useAnalyzeRun(projectId, onAnalyzeFinished);

  // Delete is deliberately plain: it removes catalog rows and nothing else, so a
  // re-scan of a still-bound folder brings the files back. The confirm dialog
  // says so rather than the behaviour being a surprise.
  const [confirmDelete, setConfirmDelete] = useState(false);
  const deleteMut = useMutation({
    mutationFn: () => {
      const selectedIds = (kind: ReturnType<typeof selectionKind>) =>
        [...selected]
          .filter((key) => selectionKind(key) === kind)
          .map(selectionId);
      if (tab === "masters") {
        return deleteCatalogItems(projectId, {
          processed_image_ids: selectedIds("processed_image"),
        });
      }
      if (tab === "others") {
        return deleteCatalogItems(projectId, {
          sub_frame_ids: selectedIds("sub_frame"),
          file_ids: selectedIds("file"),
        });
      }
      return deleteCatalogItems(projectId, { sub_frame_ids: selectedIds("sub_frame") });
    },
    onSuccess: (r) => {
      const n = r.sub_frames + r.processed_images + r.files;
      clearSelection();
      setConfirmDelete(false);
      invalidateCatalog();
      setSnack(`Removed ${n.toLocaleString()} item${n === 1 ? "" : "s"} from the catalog`);
    },
    onError: (e: Error) => {
      setConfirmDelete(false);
      setSnack(e.message);
    },
  });

  const folderTargetMut = useMutation({
    mutationFn: ({ folderId, targetId }: { folderId: number; targetId: number | null }) =>
      setFolderTarget(projectId, folderId, targetId),
    onSuccess: () => {
      invalidateFolders();
      // Re-tagging re-assigns already-cataloged lights, so the rows move too.
      invalidateCatalog();
      setSnack("Folder target updated");
    },
    onError: (e: Error) => setSnack(e.message),
  });

  const addMut = useMutation({
    mutationFn: ({
      path,
      rigId,
      targetId,
    }: {
      path: string;
      rigId: number | null;
      targetId: number | null;
    }) => addFolder(projectId, path, false, rigId, targetId),
    onSuccess: (folder) => {
      invalidateFolders();
      setSnack("Folder added — scanning…");
      ingestMut.mutate(folder.id); // newly added folders scan automatically
    },
    onError: (e: Error) => setSnack(e.message),
  });
  const removeMut = useMutation({
    mutationFn: (id: number) => removeFolder(projectId, id),
    onSuccess: () => {
      invalidateFolders();
      invalidateRigDependent();
      setSnack("Folder removed");
    },
    onError: (e: Error) => setSnack(e.message),
  });

  // Classification corrections: a frame for single-frame mode, or "bulk".
  // Rigs available to tag a source folder with. The user declares which rig shot a
  // folder; nothing infers it from a header.
  const { data: allRigs = [] } = useQuery({
    queryKey: ["rigs", "all"],
    queryFn: () => fetchRigs(false),
  });
  const rigs = useMemo(() => {
    const usedIds = new Set<number>([
      ...(project?.rigs.map((rig) => rig.id) ?? []),
      ...projectRigSetups.map((rig) => rig.rig_id),
      ...folders.flatMap((folder) => folder.rig_id == null ? [] : [folder.rig_id]),
    ]);
    return allRigs.filter((rig) => (rig.active && rig.is_mine) || usedIds.has(rig.id));
  }, [allRigs, folders, project, projectRigSetups]);
  const folderRigMut = useMutation({
    mutationFn: ({ folderId, rigId }: { folderId: number; rigId: number | null }) =>
      setFolderRig(projectId, folderId, rigId),
    onSuccess: (f) => {
      queryClient.invalidateQueries({ queryKey: ["project-folders", projectId] });
      invalidateRigDependent();
      setSnack(
        f.rig_name
          ? `Folder tagged ${f.rig_name} — its frames and sessions were re-keyed`
          : "Folder rig cleared",
      );
    },
    onError: (e: Error) => setSnack(e.message),
  });

  const [correctTarget, setCorrectTarget] = useState<CatalogFrame | "bulk" | null>(null);

  // Embedded analyzer overlay. Stepping walks this list, so it inherits the
  // active tab + filter pill for free.
  const [analyzerIndex, setAnalyzerIndex] = useState<number | null>(null);
  // Anything in the active list with a real path can be opened, masters and
  // not-cataloged files included. Plain files in Others stay excluded. Only one
  // source list contributes at a time, so ids from different tables cannot collide.
  const analyzerItems: AnalyzerItem[] = useMemo(
    () => {
      if (tab === "uncataloged") {
        return (uncatalogedQuery.data?.files ?? []).map((file) => ({
          id: file.id,
          path: file.path,
          name: folderName(file.path),
        }));
      }
      return items
        .filter((i): i is CatalogItem & { id: number; path: string } => {
          // Frames and masters are openable in the analyzer; plain files are not.
          if (!isSubFrame(i) && !isMaster(i)) return false;
          return Boolean(i.path);
        })
        .map((f) => ({
          id: f.id,
          path: f.path,
          name: f.path.split("/").pop() ?? String(f.id),
        }));
    },
    [items, tab, uncatalogedQuery.data?.files],
  );

  const openInAnalyzer = useCallback(
    (row: { id: number }) => {
      const at = analyzerItems.findIndex((i) => i.id === row.id);
      if (at >= 0) setAnalyzerIndex(at);
    },
    [analyzerItems],
  );

  const othersCount = summary
    ? summary.pxiprojects + summary.logs + summary.other + summary.unknown_frames
    : 0;
  const tabs: { key: TabKey; label: string; count: number }[] = [
    { key: "light", label: "Lights", count: summary?.lights ?? 0 },
    { key: "dark", label: "Darks", count: summary?.darks ?? 0 },
    { key: "flat", label: "Flats", count: summary?.flats ?? 0 },
    { key: "dark_flat", label: "Dark Flats", count: summary?.dark_flats ?? 0 },
    { key: "bias", label: "Bias", count: summary?.bias ?? 0 },
    { key: "masters", label: "Masters", count: summary?.processed ?? 0 },
    { key: "others", label: "Others", count: othersCount },
    { key: "uncataloged", label: "Not cataloged", count: summary?.uncataloged ?? 0 },
  ];
  const showRigColumn = new Set(
    folders.flatMap((folder) => folder.rig_id == null ? [] : [folder.rig_id]),
  ).size > 1;
  const showTargetColumn = projectTargets.length > 1;

  /** Edit one unclassified frame from the Others tab.
   *
   *  Routes through the bulk dialog with a single id rather than the per-frame
   *  path: an Others row is a `CatalogOther` (id / label / path), not the full
   *  `CatalogFrame` the single-frame dialog wants, and the bulk path needs only
   *  ids. */
  const correctOther = useCallback((row: CatalogOther) => {
    const key = subFrameSelectionKey(row.id);
    setSelected(new Set([key]));
    lastSelectedRef.current = key;
    setCorrectTarget("bulk");
  }, []);

  // Rows a classification correction can act on: any sub_frame. On the frame
  // tabs that's everything; in Others it's only the unknown-type frames, not the
  // PixInsight sidecars and logs, which have no frame type to set.
  const correctableKeys = useMemo(
    () =>
      items
        .filter(isSubFrame)
        .map((item) => subFrameSelectionKey(item.id)),
    [items],
  );
  // Everything in the regular catalog lists can be removed, so their selection
  // bar shows on every view; the not-cataloged list has no selection controls.
  // Correction actions are gated on there being sub frames to correct.
  const selectableKeys = useMemo(() => items.map(itemSelectionKey), [items]);
  const selectedFrameIds = useMemo(
    () =>
      [...selected]
        .filter((key) => selectionKind(key) === "sub_frame")
        .map(selectionId),
    [selected],
  );
  const canCorrect = tab !== "masters" && correctableKeys.length > 0;
  const showSelectionBar = tab !== "uncataloged" && items.length > 0 && !(tab === "light" && lightView === "thumbnails");
  const allSelected =
    showSelectionBar &&
    selectableKeys.length > 0 &&
    selectableKeys.every((key) => selected.has(key));

  return (
    <Box
      sx={{
        display: "flex",
        flexDirection: "column",
        height: "calc(100dvh - 150px)",
      }}
    >
      {/* Source folders */}
      <Box sx={{ display: "flex", alignItems: "center", justifyContent: "space-between", mb: 1 }}>
        <Typography variant="h6">Source folders</Typography>
        <Button
          variant="outlined"
          size="small"
          onClick={() => setPickerOpen(true)}
          sx={{ minHeight: 32 }}
        >
          + Add folder
        </Button>
      </Box>
      <Box
        sx={(theme) => ({
          mb: 2,
          border: folders.length > 0 ? 1 : 0,
          borderColor: theme.palette.mode === "dark" ? "#34373d" : "#dcd9d4",
          borderRadius: "8px",
          bgcolor: folders.length > 0 ? "background.paper" : undefined,
          overflow: "hidden",
          containerType: "inline-size",
        })}
      >
        {folders.length === 0 && (
          <Typography variant="body2" color="text.secondary">
            No folders yet. Add a folder — its contents are cataloged
            automatically.
          </Typography>
        )}
        {folders.map((f) => {
          const scanning = scanningFolderId === f.id;
          const rigValue =
            f.rig_id != null && rigs.some((rig) => rig.id === f.rig_id) ? f.rig_id : "";
          const targetValue =
            f.project_target_id != null &&
            projectTargets.some((target) => target.id === f.project_target_id)
              ? f.project_target_id
              : "";
          return (
            <Box
              key={f.id}
              sx={(theme) => ({
                display: "grid",
                gridTemplateColumns: "minmax(180px, 1fr) auto auto auto auto",
                gap: "12px",
                alignItems: "center",
                px: "14px",
                py: "10px",
                borderBottom: 1,
                borderColor: theme.palette.mode === "dark" ? "#34373d" : "#dcd9d4",
                "&:last-child": { borderBottom: 0 },
                "@container (max-width: 899px)": {
                  gridTemplateColumns: "minmax(130px, 160px) minmax(130px, 170px) auto auto",
                  gap: "8px",
                  alignItems: "center",
                  justifyContent: "start",
                },
              })}
            >
              <Box
                sx={{
                  minWidth: 0,
                  "@container (max-width: 899px)": { gridColumn: "1 / -1" },
                }}
              >
                <Typography sx={{ fontSize: "13px", fontWeight: 600 }}>
                  {folderName(f.path)}
                </Typography>
                <Typography
                  title={f.path}
                  sx={{ color: "text.secondary", fontSize: "12.5px", overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}
                >
                  {f.path}
                </Typography>
              </Box>
              <TextField
                select
                size="small"
                value={rigValue}
                onChange={(e) =>
                  folderRigMut.mutate({
                    folderId: f.id,
                    rigId: e.target.value === "" ? null : Number(e.target.value),
                  })
                }
                disabled={folderRigMut.isPending}
                inputProps={{ "aria-label": `Rig for ${folderName(f.path)}` }}
                SelectProps={{ displayEmpty: true }}
                sx={{ minWidth: 160, "& .MuiOutlinedInput-root": { height: 32 }, "& em": { color: "text.secondary", fontStyle: "normal" } }}
              >
                <MenuItem value="">
                  <em>Rig</em>
                </MenuItem>
                {rigs.map((r) => (
                  <MenuItem key={r.id} value={r.id}>
                    {r.name}{r.active ? "" : " (retired)"}
                  </MenuItem>
                ))}
              </TextField>
              {/* No Tooltip wrapper here, unlike elsewhere: an open tooltip sits
                  over this select's own menu and swallows the click on the
                  option beneath it. The Rig select next to it is bare for the
                  same reason, and the add-folder dialog carries the explanation. */}
              {projectTargets.length > 0 && (
                <TextField
                  select
                  size="small"
                  value={targetValue}
                  onChange={(e) =>
                    folderTargetMut.mutate({
                      folderId: f.id,
                      targetId: e.target.value === "" ? null : Number(e.target.value),
                    })
                  }
                  disabled={folderTargetMut.isPending}
                  inputProps={{ "aria-label": `Target for ${folderName(f.path)}` }}
                  SelectProps={{ displayEmpty: true }}
                  sx={{ minWidth: 170, "& .MuiOutlinedInput-root": { height: 32 }, "& em": { color: "text.secondary", fontStyle: "normal" } }}
                >
                  <MenuItem value="">
                    <em>Target</em>
                  </MenuItem>
                  {projectTargets.map((t) => (
                    <MenuItem key={t.id} value={t.id}>
                      {targetLabel(t)}
                  </MenuItem>
                ))}
                </TextField>
              )}
              <Button
                size="small"
                onClick={() => ingestMut.mutate(f.id)}
                disabled={ingestMut.isPending}
                startIcon={scanning ? <CircularProgress size={14} /> : undefined}
                sx={{ minHeight: 32, whiteSpace: "nowrap" }}
              >
                {scanning ? "Scanning…" : "Re-scan"}
              </Button>
              <Button
                size="small"
                onClick={() => removeMut.mutate(f.id)}
                sx={{ minHeight: 32, color: "text.secondary", whiteSpace: "nowrap" }}
              >
                Remove
              </Button>
            </Box>
          );
        })}
      </Box>

      {/* Unclassified frames would otherwise vanish into Others with no signal:
          the frame-type tabs all read (0) and the scan looks like it found
          nothing. Capture software that writes no IMAGETYP is the usual cause. */}
      {summary && summary.unknown_frames > 0 && tab !== "others" && (
        <Alert
          severity="info"
          sx={{ mb: 2, maxWidth: 900 }}
          action={
            <Button
              color="inherit"
              size="small"
              onClick={() => changeTab("others", { unclassifiedOnly: true })}
            >
              Review
            </Button>
          }
        >
          {summary.unknown_frames === 1
            ? "1 frame could not be classified"
            : `${summary.unknown_frames} frames could not be classified`}{" "}
          — their headers don't say what kind of frame they are. Review opens
          Others filtered to just these; select them and set the frame type.
        </Alert>
      )}

      {summary && summary.uncataloged > 0 && tab !== "uncataloged" && (
        <Alert
          severity="info"
          sx={{ mb: 2, maxWidth: 900 }}
          action={
            <Button color="inherit" size="small" onClick={() => changeTab("uncataloged")}>
              Review
            </Button>
          }
        >
          {summary.uncataloged === 1
            ? "1 file wasn't cataloged — a scan couldn't read it."
            : `${summary.uncataloged} files weren't cataloged — a scan couldn't read them.`}
        </Alert>
      )}

      {/* Category sub-tabs */}
      <Box sx={{ borderBottom: 1, borderColor: "divider", mb: 1 }}>
        <Tabs
          value={tab}
          onChange={(_, v: TabKey) => changeTab(v)}
          variant="scrollable"
          scrollButtons="auto"
          aria-label="file category tabs"
        >
          {tabs.map((t) => (
            <Tab key={t.key} value={t.key} label={`${t.label} ${t.count}`} />
          ))}
        </Tabs>
      </Box>

      {/* Quality analysis for the frames this tab is showing. Lives here rather
          than in the folder toolbar because its scope IS the list: the active
          sub-tab plus the filter pill. */}
      {isFrameTab && (items.length > 0 || (qCounts?.total ?? 0) > 0) && (
        <Box sx={{ mb: 1.5 }}>
          {/* Plain flex rather than <Stack>: Stack zeroes its children's margins,
              which silently swallowed the separation between the sort control and
              the analyze actions. */}
          <Box
            sx={{
              display: "flex",
              alignItems: "center",
              gap: 1.5,
              flexWrap: "wrap",
              rowGap: 1.5,
            }}
          >
            {tab === "light" && (
              <ToggleButtonGroup
                exclusive
                size="small"
                value={lightView}
                onChange={(_, value: "table" | "thumbnails" | null) => {
                  if (!value) return;
                  setLightView(value);
                  clearSelection();
                }}
                aria-label="View"
                sx={{ ml: "auto", "& .MuiToggleButton-root": { height: 32, px: 1.25, textTransform: "none", fontSize: "13px" } }}
              >
                <ToggleButton value="table" aria-label="Table view"><ViewListIcon fontSize="small" sx={{ mr: 0.5 }} />Table</ToggleButton>
                <ToggleButton value="thumbnails" aria-label="Thumbnails view"><GridViewIcon fontSize="small" sx={{ mr: 0.5 }} />Thumbnails</ToggleButton>
              </ToggleButtonGroup>
            )}

            {/* Never analyzed, or newly-scanned frames since the last run. */}
            {(qCounts?.pending ?? 0) > 0 && (
              <Tooltip
                title={
                  tab === "light"
                    ? "Measure HFR, star count, star SNR and sky level. Reads every file at full resolution, so a large project takes a few minutes — you can cancel and pick up where it stopped."
                    : "Measure median and sky-background level — the exposure check for flats, the pedestal check for darks and bias. Star metrics apply to lights only."
                }
              >
                <span>
                  <Button
                    variant="outlined"
                    size="small"
                    startIcon={
                      analyzeProgress.running ? <CircularProgress size={14} /> : <AutoAwesomeIcon />
                    }
                    disabled={analyzeProgress.running}
                    onClick={() => startAnalyze({ frameType: tab, pill: filterPill })}
                  >
                    {analyzeProgress.running
                      ? "Analyzing\u2026"
                      : (qCounts?.analyzed ?? 0) > 0
                        ? `Analyze ${(qCounts?.pending ?? 0).toLocaleString()} new ${scopeNoun(qCounts?.pending ?? 0)}`
                        : `Analyze ${(qCounts?.total ?? 0).toLocaleString()} ${scopeNoun(qCounts?.total ?? 0)}`}
                  </Button>
                </span>
              </Tooltip>
            )}

            {/* Everything in scope has been measured — offer a recompute. */}
            {(qCounts?.analyzed ?? 0) > 0 && (
              <Tooltip title="Measure every frame in this view again, discarding the stored values. Worth doing after re-processing the files, or to retry frames that were unreadable because a volume was offline.">
                <span>
                  <Button
                    variant={(qCounts?.pending ?? 0) > 0 ? "text" : "outlined"}
                    size="small"
                    startIcon={
                      analyzeProgress.running ? <CircularProgress size={14} /> : <RefreshIcon />
                    }
                    disabled={analyzeProgress.running}
                    onClick={() => startAnalyze({ frameType: tab, pill: filterPill }, true)}
                  >
                    {`Re-analyze ${
                      (qCounts?.pending ?? 0) > 0 ? "all " : ""
                    }${(qCounts?.total ?? 0).toLocaleString()} ${scopeNoun(qCounts?.total ?? 0)}`}
                  </Button>
                </span>
              </Tooltip>
            )}

            {(qCounts?.unreadable ?? 0) > 0 && !analyzeProgress.running && (
              <Tooltip title="These files could not be read when they were last measured — most often a volume that was offline. Re-analyze to try them again.">
                <Typography sx={{ fontSize: 12.5, color: "text.disabled" }}>
                  {qCounts?.unreadable} unreadable
                </Typography>
              </Tooltip>
            )}
          </Box>

          {/* Live progress. Cancel lands between batches, so within a few seconds. */}
          {analyzeProgress.running && (
            <Box sx={{ mt: 1, maxWidth: 900 }}>
              <Stack direction="row" spacing={2} alignItems="center" sx={{ mb: 0.5 }}>
                <Typography variant="body2" sx={{ flex: 1 }}>
                  {analyzeProgress.done.toLocaleString()} / {analyzeProgress.total.toLocaleString()}
                  {analyzeProgress.etaSeconds != null &&
                    ` \u00b7 ~${formatEta(analyzeProgress.etaSeconds)} left`}
                  {analyzeProgress.unreadable > 0 &&
                    ` \u00b7 ${analyzeProgress.unreadable} unreadable`}
                </Typography>
                <Button size="small" color="inherit" onClick={cancelAnalyze}>
                  Cancel
                </Button>
              </Stack>
              <LinearProgress
                variant="determinate"
                value={
                  analyzeProgress.total > 0
                    ? (analyzeProgress.done / analyzeProgress.total) * 100
                    : 0
                }
                sx={{
                  height: 6,
                  borderRadius: 3,
                  // primary.main is warm amber in this theme; the approved
                  // colorblind-safe accent is blue.
                  backgroundColor: "action.hover",
                  "& .MuiLinearProgress-bar": { backgroundColor: RIG_BLUE },
                }}
              />
            </Box>
          )}
        </Box>
      )}

      {/* Others is dominated by files that can never have a frame type — WBPP
          writes an .xnml and an .xdrz beside every registered sub — so the few
          unclassified frames need a way to be isolated. */}
      {tab === "others" && (
        <Stack direction="row" alignItems="center" sx={{ mb: 1 }}>
          <Tooltip title="Hide the files that aren't frames — PixInsight sidecars (.xnml, .xdrz), logs, and the project file. Only unknown-type frames can be given a frame type.">
            <FormControlLabel
              control={
                <Checkbox
                  size="small"
                  checked={unclassifiedOnly}
                  onChange={(e) => {
                    setUnclassifiedOnly(e.target.checked);
                    clearSelection();
                  }}
                />
              }
              label={
                <Typography sx={{ fontSize: 13 }}>
                  Unclassified frames only
                  {summary ? ` (${summary.unknown_frames})` : ""}
                </Typography>
              }
            />
          </Tooltip>
        </Stack>
      )}

      {/* Per-filter pills — click to filter the list by that filter (toggle).
          Lights show name · count; Flats add total exposure. */}
      {showFilterPills && filterStats.length > 0 && (
        <Stack direction="row" flexWrap="wrap" gap={1} sx={{ mb: 1 }}>
          {orderedFilterStats.map((s) => {
            const name = s.filter_name ?? "Not recorded";
            const pill: FramePill = s.filter_name
              ? { kind: "name", name: s.filter_name }
              : { kind: "notRecorded" };
            const resolvedFilter = s.filter_name
              ? resolveFilterLabel(s.filter_name)
              : notRecordedFilter();
            const active = framePillsEqual(filterPill, pill);
            const labelText =
              tab === "flat"
                ? `${name} · ${s.count} · ${formatExposure(s.total_seconds)}`
                : `${name} · ${s.count}`;
            return (
              <Chip
                key={framePillKey(pill)}
                size="small"
                clickable
                variant={active ? "filled" : "outlined"}
                color="primary"
                label={
                  <Box component="span" sx={{ display: "inline-flex", alignItems: "center", gap: "6px" }}>
                    <FilterSwatch filter={resolvedFilter} />
                    {labelText}
                  </Box>
                }
                onClick={() => changeFilterPill(active ? null : pill)}
              />
            );
          })}
        </Stack>
      )}

      {/* Selection / bulk-correction bar — only on the frame tabs. */}
      {showSelectionBar && (
        <Stack
          direction="row"
          spacing={1}
          alignItems="center"
          sx={{
            mb: 1,
            px: 1,
            py: 0.5,
            borderRadius: 1,
            bgcolor: selected.size > 0 ? "action.selected" : "transparent",
          }}
        >
          <Checkbox
            size="small"
            checked={allSelected}
            indeterminate={selected.size > 0 && !allSelected}
            onChange={() => {
              if (allSelected) clearSelection();
              else setSelected(new Set(selectableKeys));
            }}
            inputProps={{ "aria-label": "select all loaded frames" }}
          />
          <Typography variant="body2" color="text.secondary">
            {selected.size > 0
              ? `${selected.size} selected`
              : canCorrect
                ? `Select items to correct or remove`
                : `Select items to remove from the catalog`}
          </Typography>
          {selected.size > 0 && (
            <>
              {tab !== "masters" && tab !== "others" && (
                <Button size="small" variant="outlined" onClick={() => setCorrectTarget("bulk")}>
                  Correct {selected.size}
                </Button>
              )}
              {tab === "others" && selectedFrameIds.length > 0 && (
                <Button size="small" variant="outlined" onClick={() => setCorrectTarget("bulk")}>
                  Set frame type
                </Button>
              )}
              <Button
                size="small"
                variant="outlined"
                startIcon={<DeleteIcon fontSize="small" />}
                onClick={() => setConfirmDelete(true)}
              >
                Remove {selected.size}
              </Button>
              <Button size="small" onClick={clearSelection}>
                Clear
              </Button>
            </>
          )}
        </Stack>
      )}

      {tab === "uncataloged" ? (
        <UncatalogedFileTable
          rows={uncatalogedQuery.data?.files ?? []}
          timezone={tz}
          loading={uncatalogedQuery.isLoading}
          onOpen={openInAnalyzer}
        />
      ) : tab === "masters" ? (
        <CatalogMasterTable
          key={tab}
          rows={items as CatalogMaster[]}
          timezone={tz}
          selected={selected}
          onToggleSelect={toggleSelect}
          onOpen={openInAnalyzer}
          hasMore={Boolean(hasNextPage)}
          fetchingMore={isFetchingNextPage}
          onLoadMore={fetchNextPage}
          loading={isLoading}
        />
      ) : tab === "others" ? (
        <CatalogOtherTable
          key={`${tab}:${unclassifiedOnly}`}
          rows={items as CatalogOther[]}
          projectId={projectId}
          timezone={tz}
          selected={selected}
          onToggleSelect={toggleSelect}
          onOpen={openInAnalyzer}
          onCorrect={correctOther}
          hasMore={Boolean(hasNextPage)}
          fetchingMore={isFetchingNextPage}
          onLoadMore={fetchNextPage}
          loading={isLoading}
        />
      ) : tab === "light" && lightView === "thumbnails" ? (
        <CatalogThumbnailSheet
          key={`${tab}:${framePillKey(filterPill)}:${sort}`}
          rows={items as CatalogFrame[]}
          projectId={projectId}
          timezone={tz}
          showNightHeadings={sort === "date_desc" || sort === "date"}
          onOpen={openInAnalyzer}
          hasMore={Boolean(hasNextPage)}
          fetchingMore={isFetchingNextPage}
          onLoadMore={fetchNextPage}
          loading={isLoading}
        />
      ) : (
        <CatalogFrameTable
          key={`${tab}:${framePillKey(filterPill)}:${sort}`}
          rows={items as CatalogFrame[]}
          projectId={projectId}
          timezone={tz}
          sort={sort}
          calibration={tab !== "light"}
          showRig={showRigColumn}
          showTarget={showTargetColumn}
          selected={selected}
          onToggleSelect={toggleSelect}
          onSort={(next) => {
            setSort(next);
            clearSelection();
          }}
          onOpen={openInAnalyzer}
          onCorrect={setCorrectTarget}
          hasMore={Boolean(hasNextPage)}
          fetchingMore={isFetchingNextPage}
          onLoadMore={fetchNextPage}
          loading={isLoading}
        />
      )}

      <FileBrowser
        open={pickerOpen}
        onClose={() => setPickerOpen(false)}
        onSelect={(path) => {
          // Ask for the rig before adding: the folder's rig is the one equipment
          // fact ingest records, and frames inherit it the moment they're
          // scanned. Adding first and tagging afterwards means the first scan
          // files everything under "not stated".
          setPendingPath(path);
          setPendingRigId("");
          setPendingTargetId("");
        }}
        directoryMode
        title="Add source folder"
        emptyMessage="No subfolders here"
      />

      <Dialog
        open={pendingPath !== null}
        onClose={() => setPendingPath(null)}
        maxWidth="sm"
        fullWidth
      >
        <DialogTitle>Add source folder</DialogTitle>
        <DialogContent>
          <Typography
            variant="body2"
            sx={{ color: "text.secondary", wordBreak: "break-all", mb: 2 }}
          >
            {pendingPath}
          </Typography>
          <TextField
            select
            fullWidth
            size="small"
            label="Rig"
            value={pendingRigId}
            onChange={(e) =>
              setPendingRigId(e.target.value === "" ? "" : Number(e.target.value))
            }
            helperText="Which rig shot this folder. Frames inherit it; you can change it later."
          >
            <MenuItem value="">
              <em>Not stated</em>
            </MenuItem>
            {rigs.map((r) => (
              <MenuItem key={r.id} value={r.id}>
                {r.name}{r.active ? "" : " (retired)"}
              </MenuItem>
            ))}
          </TextField>
          {projectTargets.length > 0 && (
            <TextField
              select
              fullWidth
              size="small"
              label="Target"
              value={pendingTargetId}
              onChange={(e) =>
                setPendingTargetId(e.target.value === "" ? "" : Number(e.target.value))
              }
              sx={{ mt: 2 }}
              helperText="Which target this folder holds. Auto uses the project's target when it has exactly one — set it explicitly when a project covers several."
            >
              <MenuItem value="">
                <em>Auto</em>
              </MenuItem>
              {projectTargets.map((t) => (
                <MenuItem key={t.id} value={t.id}>
                  {targetLabel(t)}
                </MenuItem>
              ))}
            </TextField>
          )}
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setPendingPath(null)}>Cancel</Button>
          <Button
            variant="contained"
            disabled={addMut.isPending}
            onClick={() => {
              if (pendingPath === null) return;
              addMut.mutate({
                path: pendingPath,
                rigId: pendingRigId === "" ? null : pendingRigId,
                targetId: pendingTargetId === "" ? null : pendingTargetId,
              });
              setPendingPath(null);
              setPickerOpen(false);
            }}
          >
            Add folder
          </Button>
        </DialogActions>
      </Dialog>
      {/* Keyed so each frame gets a fresh instance. The dialog resets its field
          state in an effect, which runs AFTER the first render — without the key,
          reopening on a different frame briefly shows the previous frame's dirty
          state with Save enabled, and saving in that window would write the old
          picks to the new frame. Same reason FovSimulator is keyed in
          PlannerDetailPanel. "bulk" is its own key so switching between a single
          frame and the bulk action re-seeds the fields. */}
      <Dialog open={confirmDelete} onClose={() => setConfirmDelete(false)} maxWidth="sm" fullWidth>
        <DialogTitle>
          Remove {selected.size} item{selected.size === 1 ? "" : "s"} from the catalog?
        </DialogTitle>
        <DialogContent>
          <Typography variant="body2" sx={{ mb: 1.5 }}>
            This removes {selected.size === 1 ? "it" : "them"} from this project's catalog
            only. <strong>Nothing is deleted from disk.</strong>
          </Typography>
          <Alert severity="info" sx={{ mb: 1 }}>
            Re-scanning the source folder will catalog{" "}
            {selected.size === 1 ? "it" : "them"} again — the catalog reflects
            what's under the bound folders. To keep files out for good, move them
            out of the folder or unbind the folder.
          </Alert>
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setConfirmDelete(false)}>Cancel</Button>
          <Button
            variant="contained"
            onClick={() => deleteMut.mutate()}
            disabled={deleteMut.isPending}
            startIcon={deleteMut.isPending ? <CircularProgress size={14} /> : undefined}
          >
            Remove
          </Button>
        </DialogActions>
      </Dialog>

      <FrameCorrectionsDialog
        key={correctTarget === "bulk" ? "bulk" : (correctTarget?.id ?? "none")}
        open={correctTarget !== null}
        onClose={() => setCorrectTarget(null)}
        projectId={projectId}
        frame={correctTarget === "bulk" ? null : correctTarget}
        frameIds={correctTarget === "bulk" ? selectedFrameIds : []}
        onSaved={(updated) => {
          if (updated) {
            // A frame_type correction moves the frame to a different category
            // tab, so patching it in place would leave a stale row behind in
            // this one while the header counts already moved. Only the in-place
            // patch is safe when the type didn't change.
            if (correctTarget !== "bulk" && updated.frame_type !== correctTarget?.frame_type) {
              invalidateCatalog();
            } else {
              patchFrameRow(updated);
            }
            setSnack("Classification saved — this frame is protected from re-scans");
          } else {
            // Bulk changes move frames between category tabs, so the counts and
            // the list itself both shift — a full refresh is correct here.
            invalidateCatalog();
            clearSelection();
            setSnack(`Corrected ${selectedFrameIds.length} frames`);
          }
        }}
      />
      <AnalyzerOverlay
        open={analyzerIndex !== null}
        onClose={() => setAnalyzerIndex(null)}
        items={analyzerItems}
        index={analyzerIndex ?? 0}
        onIndexChange={setAnalyzerIndex}
        onNeedMore={() => {
          if (hasNextPage && !isFetchingNextPage) fetchNextPage();
        }}
      />
      <Snackbar
        open={snack !== null}
        autoHideDuration={4000}
        onClose={() => setSnack(null)}
        message={snack ?? ""}
      />
    </Box>
  );
}
