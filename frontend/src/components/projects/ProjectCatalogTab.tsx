import { useState } from "react";
import {
  useInfiniteQuery,
  useMutation,
  useQuery,
  useQueryClient,
} from "@tanstack/react-query";
import Box from "@mui/material/Box";
import Button from "@mui/material/Button";
import Chip from "@mui/material/Chip";
import CircularProgress from "@mui/material/CircularProgress";
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

  const changeTab = (next: TabKey) => {
    setTab(next);
    setFilterName(null);
  };

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
  const items: CatalogItem[] = data?.pages.flatMap((p) => p.rows) ?? [];
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
    return (
      <FrameCard
        row={item as CatalogFrame}
        projectId={projectId}
        tz={tz}
        showFilter={tab === "light" || tab === "flat"}
        showObject={tab === "light"}
      />
    );
  };

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
            const selected = filterName === s.filter_name;
            const label =
              tab === "flat"
                ? `${name} · ${s.count} · ${formatExposure(s.total_seconds)}`
                : `${name} · ${s.count}`;
            return (
              <Chip
                key={name}
                size="small"
                clickable
                variant={selected ? "filled" : "outlined"}
                color="primary"
                label={label}
                onClick={() => setFilterName(selected ? null : s.filter_name)}
              />
            );
          })}
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
      <Snackbar
        open={snack !== null}
        autoHideDuration={4000}
        onClose={() => setSnack(null)}
        message={snack ?? ""}
      />
    </Box>
  );
}
