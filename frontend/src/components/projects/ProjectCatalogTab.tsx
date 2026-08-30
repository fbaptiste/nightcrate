import { useCallback, useMemo, useState } from "react";
import {
  useInfiniteQuery,
  useMutation,
  useQuery,
  useQueryClient,
} from "@tanstack/react-query";
import Box from "@mui/material/Box";
import Button from "@mui/material/Button";
import Checkbox from "@mui/material/Checkbox";
import Chip from "@mui/material/Chip";
import MenuItem from "@mui/material/MenuItem";
import TextField from "@mui/material/TextField";
import CircularProgress from "@mui/material/CircularProgress";
import { fetchRigs } from "@/api/rigs";
import IconButton from "@mui/material/IconButton";
import Snackbar from "@mui/material/Snackbar";
import Stack from "@mui/material/Stack";
import Tab from "@mui/material/Tab";
import Tabs from "@mui/material/Tabs";
import Tooltip from "@mui/material/Tooltip";
import Typography from "@mui/material/Typography";
import AddIcon from "@mui/icons-material/Add";
import DeleteIcon from "@mui/icons-material/Delete";
import RefreshIcon from "@mui/icons-material/Refresh";
import { FileBrowser } from "@/components/fits/FileBrowser";
import CatalogCardList from "./CatalogCardList";
import AnalyzerOverlay, { type AnalyzerItem } from "./AnalyzerOverlay";
import FrameCorrectionsDialog from "./FrameCorrectionsDialog";
import {
  formatExposure,
  FrameCard,
  MasterCard,
  OtherCard,
} from "./CatalogCards";
import {
  addFolder,
  fetchCatalogFilterSummary,
  fetchCatalogFrames,
  fetchCatalogMasters,
  fetchCatalogOthers,
  fetchCatalogSummary,
  listFolders,
  removeFolder,
  setFolderRig,
  startIngest,
  type CatalogFrame,
  type CatalogMaster,
  type CatalogOther,
} from "@/api/projectCatalog";

interface Props {
  projectId: number;
}

const PAGE_SIZE = 60;

type TabKey =
  | "light"
  | "dark"
  | "flat"
  | "dark_flat"
  | "bias"
  | "masters"
  | "others";

type CatalogItem = CatalogFrame | CatalogMaster | CatalogOther;
interface CatalogPage {
  rows: CatalogItem[];
  total: number;
  timezone: string;
}

export default function ProjectCatalogTab({ projectId }: Props) {
  const queryClient = useQueryClient();
  const [snack, setSnack] = useState<string | null>(null);
  const [pickerOpen, setPickerOpen] = useState(false);
  const [tab, setTab] = useState<TabKey>("light");
  // Active filter-pill scope on the Lights / Flats lists (null = show all).
  const [filterName, setFilterName] = useState<string | null>(null);

  // Multi-select for bulk corrections. Cleared whenever the visible set changes,
  // so a hidden selection can never be acted on by mistake.
  const [selected, setSelected] = useState<Set<number>>(new Set());

  const changeTab = (next: TabKey) => {
    setTab(next);
    setFilterName(null);
    setSelected(new Set());
  };

  const changeFilterPill = (next: string | null) => {
    setFilterName(next);
    setSelected(new Set());
  };

  const toggleSelect = useCallback((id: number) => {
    setSelected((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  }, []);

  const { data: folders = [] } = useQuery({
    queryKey: ["project-folders", projectId],
    queryFn: () => listFolders(projectId),
  });
  const { data: summary } = useQuery({
    queryKey: ["project-catalog-summary", projectId],
    queryFn: () => fetchCatalogSummary(projectId),
  });

  const {
    data,
    isLoading,
    fetchNextPage,
    hasNextPage,
    isFetchingNextPage,
  } = useInfiniteQuery({
    queryKey: ["project-catalog", projectId, tab, filterName],
    initialPageParam: 0,
    queryFn: async ({ pageParam }): Promise<CatalogPage> => {
      const off = pageParam;
      if (tab === "masters") return fetchCatalogMasters(projectId, PAGE_SIZE, off);
      if (tab === "others") return fetchCatalogOthers(projectId, PAGE_SIZE, off);
      return fetchCatalogFrames(projectId, PAGE_SIZE, off, tab, filterName);
    },
    getNextPageParam: (_last, allPages) => {
      const loaded = allPages.reduce((n, p) => n + p.rows.length, 0);
      return loaded < (allPages[0]?.total ?? 0) ? loaded : undefined;
    },
  });
  // Memoized: `items` feeds `analyzerItems` -> `openInAnalyzer` -> every card's
  // `onOpen`. A fresh array each render would change that prop's identity and
  // defeat memo(FrameCard) for every loaded card on every checkbox tick and every
  // analyzer prev/next step.
  const items: CatalogItem[] = useMemo(() => data?.pages.flatMap((p) => p.rows) ?? [], [data]);
  const tz = data?.pages[0]?.timezone ?? "UTC";

  // Per-filter pills (count + total exposure) for the Lights & Flats tabs.
  const showFilterPills = tab === "light" || tab === "flat";
  const { data: filterStats = [] } = useQuery({
    queryKey: ["project-catalog-filters", projectId, tab],
    queryFn: () => fetchCatalogFilterSummary(projectId, tab as "light" | "flat"),
    enabled: showFilterPills,
  });

  const invalidateCatalog = () => {
    queryClient.invalidateQueries({
      queryKey: ["project-catalog-summary", projectId],
    });
    queryClient.invalidateQueries({ queryKey: ["project-catalog", projectId] });
    queryClient.invalidateQueries({
      queryKey: ["project-catalog-filters", projectId],
    });
  };

  /** Counts only — the row itself is patched in place by `patchFrameRow`. */
  const invalidateCounts = () => {
    queryClient.invalidateQueries({
      queryKey: ["project-catalog-summary", projectId],
    });
    queryClient.invalidateQueries({
      queryKey: ["project-catalog-filters", projectId],
    });
  };

  /** Replace one row in the loaded pages instead of refetching the whole
   *  infinite query. A full invalidate refetches EVERY page already loaded, so
   *  editing one card after scrolling 20 pages cost 20 round-trips. */
  const patchFrameRow = (updated: CatalogFrame) => {
    queryClient.setQueryData<{ pages: CatalogPage[]; pageParams: unknown[] }>(
      ["project-catalog", projectId, tab, filterName],
      (old) =>
        old
          ? {
              ...old,
              pages: old.pages.map((p) => ({
                ...p,
                rows: p.rows.map((r) =>
                  "kind" in r && r.kind === "sub_frame" && r.id === updated.id
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
      invalidateCatalog();
      setSnack(
        `Scan ${s.status}: ${s.subs_inserted} new, ${s.subs_updated} updated` +
          (s.errors_count ? `, ${s.errors_count} errors` : ""),
      );
    },
    onError: (e: Error) => setSnack(e.message),
    onSettled: () => setScanningFolderId(null),
  });
  const addMut = useMutation({
    mutationFn: (path: string) => addFolder(projectId, path),
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
      invalidateCatalog(); // its cataloged items are gone — refresh lists + counts
      setSnack("Folder removed");
    },
    onError: (e: Error) => setSnack(e.message),
  });

  // Classification corrections: a frame for single-frame mode, or "bulk".
  // Rigs available to tag a source folder with. The user declares which rig shot a
  // folder; nothing infers it from a header.
  const { data: rigs = [] } = useQuery({ queryKey: ["rigs"], queryFn: () => fetchRigs(true) });
  const folderRigMut = useMutation({
    mutationFn: ({ folderId, rigId }: { folderId: number; rigId: number | null }) =>
      setFolderRig(projectId, folderId, rigId),
    onSuccess: (f) => {
      // Only the folder list changes on screen — no card renders a rig, so
      // invalidating the infinite catalog query would refetch every loaded page
      // for nothing.
      queryClient.invalidateQueries({ queryKey: ["project-folders", projectId] });
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
  const analyzerItems: AnalyzerItem[] = useMemo(
    () =>
      items
        .filter((i): i is CatalogFrame => "kind" in i && i.kind === "sub_frame" && !!i.path)
        .map((f) => ({
          id: f.id,
          path: f.path as string,
          name: f.path!.split("/").pop() ?? String(f.id),
        })),
    [items],
  );

  const openInAnalyzer = useCallback(
    (row: CatalogFrame) => {
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
  ];

  const renderItem = (item: CatalogItem) => {
    if (tab === "masters") {
      return (
        <MasterCard row={item as CatalogMaster} projectId={projectId} tz={tz} />
      );
    }
    if (tab === "others") {
      return <OtherCard row={item as CatalogOther} tz={tz} />;
    }
    const row = item as CatalogFrame;
    return (
      <FrameCard
        row={row}
        projectId={projectId}
        tz={tz}
        showFilter={tab === "light" || tab === "flat"}
        showObject={tab === "light"}
        onCorrect={setCorrectTarget}
        onOpen={openInAnalyzer}
        selected={selected.has(row.id)}
        onToggleSelect={toggleSelect}
      />
    );
  };

  const frameTab = tab !== "masters" && tab !== "others";
  const allSelected = frameTab && items.length > 0 && selected.size === items.length;

  return (
    <Box
      sx={{
        display: "flex",
        flexDirection: "column",
        height: "calc(100dvh - 150px)",
      }}
    >
      {/* Source folders */}
      <Typography variant="h6" sx={{ mb: 1 }}>
        Source folders
      </Typography>
      <Stack spacing={1} sx={{ mb: 2 }}>
        {folders.length === 0 && (
          <Typography variant="body2" color="text.secondary">
            No folders yet. Add a folder — its contents are cataloged
            automatically.
          </Typography>
        )}
        {folders.map((f) => {
          const scanning = scanningFolderId === f.id;
          return (
            <Stack key={f.id} direction="row" alignItems="center" spacing={1}>
              <Typography variant="body2" sx={{ fontFamily: "monospace" }}>
                {f.path}
              </Typography>
              <Button
                size="small"
                variant="outlined"
                onClick={() => ingestMut.mutate(f.id)}
                disabled={ingestMut.isPending}
                startIcon={
                  scanning ? (
                    <CircularProgress size={14} />
                  ) : (
                    <RefreshIcon fontSize="small" />
                  )
                }
              >
                {scanning ? "Scanning…" : "Re-scan"}
              </Button>
              <Tooltip title="Which rig shot this folder. Frames inherit it, a dual-rig night splits into one session per rig, and calibration frames only match lights from the same rig. Leave blank if you'd rather not say.">
                <TextField
                  select
                  size="small"
                  label="Rig"
                  value={f.rig_id ?? ""}
                  onChange={(e) =>
                    folderRigMut.mutate({
                      folderId: f.id,
                      rigId: e.target.value === "" ? null : Number(e.target.value),
                    })
                  }
                  disabled={folderRigMut.isPending}
                  sx={{ minWidth: 160 }}
                >
                  <MenuItem value="">
                    <em>Not stated</em>
                  </MenuItem>
                  {rigs.map((r) => (
                    <MenuItem key={r.id} value={r.id}>
                      {r.name}
                    </MenuItem>
                  ))}
                </TextField>
              </Tooltip>
              <Tooltip title="Remove folder">
                <IconButton size="small" onClick={() => removeMut.mutate(f.id)}>
                  <DeleteIcon fontSize="small" />
                </IconButton>
              </Tooltip>
            </Stack>
          );
        })}
      </Stack>

      <Stack direction="row" spacing={2} sx={{ mb: 2 }} alignItems="center">
        <Button
          startIcon={<AddIcon />}
          variant="outlined"
          onClick={() => setPickerOpen(true)}
        >
          Add folder
        </Button>
      </Stack>

      {/* Category sub-tabs */}
      <Box sx={{ borderBottom: 1, borderColor: "divider", mb: 1 }}>
        <Tabs
          value={tab}
          onChange={(_, v: TabKey) => changeTab(v)}
          variant="scrollable"
          scrollButtons="auto"
          aria-label="catalog category tabs"
        >
          {tabs.map((t) => (
            <Tab key={t.key} value={t.key} label={`${t.label} (${t.count})`} />
          ))}
        </Tabs>
      </Box>

      {/* Per-filter pills — click to filter the list by that filter (toggle).
          Lights show name · count; Flats add total exposure. */}
      {showFilterPills && filterStats.length > 0 && (
        <Stack direction="row" flexWrap="wrap" gap={1} sx={{ mb: 1 }}>
          {filterStats.map((s) => {
            const name = s.filter_name ?? "—";
            const active = filterName === s.filter_name;
            const label =
              tab === "flat"
                ? `${name} · ${s.count} · ${formatExposure(s.total_seconds)}`
                : `${name} · ${s.count}`;
            return (
              <Chip
                key={name}
                size="small"
                clickable
                variant={active ? "filled" : "outlined"}
                color="primary"
                label={label}
                onClick={() => changeFilterPill(active ? null : s.filter_name)}
              />
            );
          })}
        </Stack>
      )}

      {/* Selection / bulk-correction bar — only on the frame tabs. */}
      {frameTab && items.length > 0 && (
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
            onChange={() =>
              setSelected(allSelected ? new Set() : new Set(items.map((i) => i.id)))
            }
            inputProps={{ "aria-label": "select all loaded frames" }}
          />
          <Typography variant="body2" color="text.secondary">
            {selected.size > 0
              ? `${selected.size} selected`
              : `Select frames to correct in bulk`}
          </Typography>
          {selected.size > 0 && (
            <>
              <Button size="small" variant="outlined" onClick={() => setCorrectTarget("bulk")}>
                Correct {selected.size}
              </Button>
              <Button size="small" onClick={() => setSelected(new Set())}>
                Clear
              </Button>
            </>
          )}
        </Stack>
      )}

      <CatalogCardList
        key={`${tab}:${filterName ?? ""}`}
        items={items}
        getKey={(it) => {
          const o = it as { kind?: string; id: number };
          return o.kind ? `${o.kind}-${o.id}` : o.id;
        }}
        renderItem={renderItem}
        hasMore={hasNextPage}
        fetchingMore={isFetchingNextPage}
        onLoadMore={fetchNextPage}
        loading={isLoading}
        emptyMessage="Nothing in this category yet."
      />

      <FileBrowser
        open={pickerOpen}
        onClose={() => setPickerOpen(false)}
        onSelect={(path) => addMut.mutate(path)}
        directoryMode
        title="Add source folder"
        emptyMessage="No subfolders here"
      />
      {/* Keyed so each frame gets a fresh instance. The dialog resets its field
          state in an effect, which runs AFTER the first render — without the key,
          reopening on a different frame briefly shows the previous frame's dirty
          state with Save enabled, and saving in that window would write the old
          picks to the new frame. Same reason FovSimulator is keyed in
          PlannerDetailPanel. "bulk" is its own key so switching between a single
          frame and the bulk action re-seeds the fields. */}
      <FrameCorrectionsDialog
        key={correctTarget === "bulk" ? "bulk" : (correctTarget?.id ?? "none")}
        open={correctTarget !== null}
        onClose={() => setCorrectTarget(null)}
        projectId={projectId}
        frame={correctTarget === "bulk" ? null : correctTarget}
        frameIds={correctTarget === "bulk" ? [...selected] : []}
        onSaved={(updated) => {
          if (updated) {
            patchFrameRow(updated);
            setSnack("Classification saved — this frame is protected from re-scans");
          } else {
            // Bulk changes move frames between category tabs, so the counts and
            // the list itself both shift — a full refresh is correct here.
            invalidateCatalog();
            setSelected(new Set());
            setSnack(`Corrected ${selected.size} frames`);
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
