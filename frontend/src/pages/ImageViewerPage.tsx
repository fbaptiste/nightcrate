import { useCallback, useEffect, useRef, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import Alert from "@mui/material/Alert";
import Autocomplete from "@mui/material/Autocomplete";
import Box from "@mui/material/Box";
import Button from "@mui/material/Button";
import Divider from "@mui/material/Divider";
import Tab from "@mui/material/Tab";
import Tabs from "@mui/material/Tabs";
import TextField from "@mui/material/TextField";
import Typography from "@mui/material/Typography";
import CircularProgress from "@mui/material/CircularProgress";
import Chip from "@mui/material/Chip";
import Snackbar from "@mui/material/Snackbar";
import FitScreenIcon from "@mui/icons-material/FitScreen";
import FolderOpenIcon from "@mui/icons-material/FolderOpen";
import ImageSearchIcon from "@mui/icons-material/ImageSearch";
import OneKIcon from "@mui/icons-material/PhotoSizeSelectActual";
import {
  DEFAULT_STRETCH,
  fetchExtensions,
  fetchHeader,
  fetchImageStats,
  fetchRecentFiles,
  recordRecentFile,
  stfToStretch,
  supportsStretch,
  type ImageStats,
  type RecentFile,
  type StretchParams,
} from "@/api/images";
import { FileBrowser } from "@/components/fits/FileBrowser";
import { FitsHeaderTable } from "@/components/fits/FitsHeaderTable";
import { FitsImage, type FitsImageHandle } from "@/components/fits/FitsImage";
import { HduSelector } from "@/components/fits/HduSelector";
import { StretchControls } from "@/components/fits/StretchControls";
import { useDebounce } from "@/lib/useDebounce";
import { monoFontFamily } from "@/theme/theme";

function formatDateObs(raw: string | null): string | null {
  if (!raw) return null;
  const d = new Date(raw.endsWith("Z") ? raw : raw + "Z");
  if (isNaN(d.getTime())) return raw;
  return new Intl.DateTimeFormat(undefined, {
    year: "numeric", month: "short", day: "numeric",
    hour: "2-digit", minute: "2-digit", second: "2-digit",
    timeZoneName: "short",
  }).format(d);
}

const DEFAULT_PER_CHANNEL: [StretchParams, StretchParams, StretchParams] = [
  { ...DEFAULT_STRETCH },
  { ...DEFAULT_STRETCH },
  { ...DEFAULT_STRETCH },
];

function applyAutoStf(
  stats: ImageStats,
  setLinked: (p: StretchParams) => void,
  setPerChannel: (ch: [StretchParams, StretchParams, StretchParams]) => void,
) {
  if (stats.color && stats.linked_stf) {
    setLinked(stfToStretch(stats.linked_stf));
  } else if (stats.channels.length >= 1) {
    setLinked(stfToStretch(stats.channels[0].stf));
  }
  if (stats.color && stats.channels.length === 3) {
    setPerChannel([
      stfToStretch(stats.channels[0].stf),
      stfToStretch(stats.channels[1].stf),
      stfToStretch(stats.channels[2].stf),
    ]);
  }
}

export function ImageViewerPage() {
  const [inputPath, setInputPath] = useState("");
  const [activePath, setActivePath] = useState("");
  const [selectedHdu, setSelectedHdu] = useState(0);
  const [tab, setTab] = useState(0);
  const imageRef = useRef<FitsImageHandle>(null);
  const [currentZoom, setCurrentZoom] = useState(1);

  // File browser
  const [browserOpen, setBrowserOpen] = useState(false);

  // Error notification
  const [errorMsg, setErrorMsg] = useState<string | null>(null);

  // Stretch state
  const [linked, setLinked] = useState<StretchParams>({ ...DEFAULT_STRETCH });
  const [perChannel, setPerChannel] = useState<[StretchParams, StretchParams, StretchParams]>(DEFAULT_PER_CHANNEL);
  const [isLinked, setIsLinked] = useState(true);

  const debouncedLinked = useDebounce(linked, 300);
  const debouncedPerChannel = useDebounce(perChannel, 300);

  // Whether active file supports stretch (FITS/XISF yes, standard no)
  const hasStretch = activePath !== "" && supportsStretch(activePath);

  // Recent files
  const recentQuery = useQuery({
    queryKey: ["recent-files"],
    queryFn: fetchRecentFiles,
  });
  const recentFiles: RecentFile[] = recentQuery.data ?? [];

  const extensionsQuery = useQuery({
    queryKey: ["extensions", activePath],
    queryFn: () => fetchExtensions(activePath),
    enabled: activePath !== "",
  });

  const statsQuery = useQuery({
    queryKey: ["stats", activePath, selectedHdu],
    queryFn: () => fetchImageStats(activePath, selectedHdu),
    enabled: hasStretch,
  });

  const headerQuery = useQuery({
    queryKey: ["header", activePath, selectedHdu],
    queryFn: () => fetchHeader(activePath, selectedHdu),
    enabled: activePath !== "",
  });

  // Auto-apply stretch once when stats first arrive for a new file.
  // Uses a ref to track which path+hdu combo we've already applied defaults for,
  // so we don't re-apply when the user manually changes stretch settings.
  const appliedDefaultsFor = useRef("");
  useEffect(() => {
    if (!statsQuery.data || statsQuery.isFetching) return;

    const key = `${activePath}::${selectedHdu}`;
    if (appliedDefaultsFor.current === key) return;
    appliedDefaultsFor.current = key;

    const exts = extensionsQuery.data ?? [];
    const ext = exts.find((h) => h.index === selectedHdu);

    // Check explicit linear flag from pxiproject extensions
    if (ext?.linear === false) {
      setLinked({ ...DEFAULT_STRETCH, stretch: "linear" });
      return;
    }

    // For all files: check auto-stretch midtone to detect non-linear images
    const stats = statsQuery.data;
    const stf = stats.linked_stf ?? stats.channels[0]?.stf;
    if (stf && stf.midtone >= 0.1) {
      setLinked({ ...DEFAULT_STRETCH, stretch: "linear" });
      return;
    }

    applyAutoStf(stats, setLinked, setPerChannel);
  }, [statsQuery.data, statsQuery.isFetching, extensionsQuery.data, selectedHdu, activePath]);

  // Show error snackbar on query failures
  useEffect(() => {
    if (extensionsQuery.isError) setErrorMsg(String(extensionsQuery.error));
  }, [extensionsQuery.isError, extensionsQuery.error]);

  function openFile(path: string, displayName?: string) {
    setSelectedHdu(0);
    setTab(0);
    setLinked({ ...DEFAULT_STRETCH });
    setPerChannel(DEFAULT_PER_CHANNEL);
    setIsLinked(true);
    // For project images, show a readable path in the input
    if (path.includes("::") && displayName) {
      const projPath = path.split("::")[0];
      setInputPath(`${projPath} / ${displayName}`);
    } else {
      setInputPath(path);
    }
    setActivePath(path);
    recordRecentFile(path).then(() => recentQuery.refetch());
  }

  function handleOpen() {
    const p = inputPath.trim();
    if (p) openFile(p);
  }

  function handleReset() {
    if (statsQuery.data) {
      applyAutoStf(statsQuery.data, setLinked, setPerChannel);
      setIsLinked(true);
    }
  }

  const handleLinkedToggle = useCallback((val: boolean) => {
    setIsLinked(val);
    if (!val && statsQuery.data?.color && statsQuery.data.channels.length === 3) {
      // Use per-channel auto-stretch params from stats, not linked params
      setPerChannel([
        stfToStretch(statsQuery.data.channels[0].stf),
        stfToStretch(statsQuery.data.channels[1].stf),
        stfToStretch(statsQuery.data.channels[2].stf),
      ]);
    }
  }, [statsQuery.data]);

  const extensions = extensionsQuery.data ?? [];
  const selectedExtInfo = extensions.find((h) => h.index === selectedHdu);
  const hasFile = activePath !== "";
  const isColor = statsQuery.data?.color ?? false;

  // Keyboard shortcuts
  useEffect(() => {
    function onKeyDown(e: KeyboardEvent) {
      const tag = (e.target as HTMLElement).tagName;
      if (tag === "INPUT" || tag === "TEXTAREA" || tag === "SELECT") return;

      if ((e.metaKey || e.ctrlKey) && e.key === "o") {
        e.preventDefault();
        setBrowserOpen(true);
      } else if (e.key === "f" && hasFile) {
        imageRef.current?.fitToWindow();
      } else if (e.key === "1" && hasFile) {
        imageRef.current?.oneToOne();
      }
    }
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [hasFile]);

  // Display metadata
  const headerCards = headerQuery.data ?? [];
  const headerVal = (key: string) => {
    const card = headerCards.find((c) => c.key === key);
    return card?.value && card.value !== "" && card.value !== "None" ? card.value : null;
  };
  // For project images, resolve the image name from extensions query
  const projectImageName = activePath.includes("::")
    ? (extensionsQuery.data?.[0]?.name ?? null)
    : null;
  const fileName = activePath
    ? activePath.includes("::")
      ? (() => {
          const projPath = activePath.split("::")[0];
          const projName = projPath.split("/").pop() ?? "";
          return `${projName} / ${projectImageName ?? "…"}`;
        })()
      : activePath.split("/").pop() ?? null
    : null;
  const dateObs = formatDateObs(headerVal("DATE-OBS"));
  const exposure = headerVal("EXPTIME");
  const filter = headerVal("FILTER");

  const activePerChannel = (isColor && !isLinked) ? debouncedPerChannel : undefined;

  return (
    <Box sx={{ display: "flex", height: "100%", overflow: "hidden" }}>
      {/* Main area */}
      <Box sx={{ display: "flex", flexDirection: "column", flexGrow: 1, minWidth: 0, height: "100%" }}>
        {/* Toolbar */}
        <Box sx={{ display: "flex", alignItems: "center", gap: 1.5, p: 1.5, borderBottom: 1, borderColor: "divider", flexShrink: 0 }}>
          <Button
            variant="outlined"
            size="small"
            onClick={() => setBrowserOpen(true)}
            startIcon={<FolderOpenIcon sx={{ fontSize: 16 }} />}
          >
            Browse
          </Button>
          <Autocomplete
            freeSolo
            clearOnBlur={false}
            blurOnSelect
            options={recentFiles}
            getOptionLabel={(opt) => typeof opt === "string" ? opt : opt.name}
            filterOptions={(options) => options}
            inputValue={inputPath}
            onInputChange={(_, value, reason) => {
              if (reason !== "reset") setInputPath(value);
            }}
            onChange={(_, value) => {
              if (value) {
                const path = typeof value === "string" ? value : value.path;
                const name = typeof value === "string" ? undefined : (value.path.includes("::") ? value.name : undefined);
                openFile(path, name);
              }
            }}
            sx={{ flexGrow: 1 }}
            slotProps={{ listbox: { style: { maxHeight: 320 } } }}
            renderInput={(params) => (
              <TextField
                {...params}
                size="small"
                placeholder="Path to image file…"
                onKeyDown={(e) => e.key === "Enter" && handleOpen()}
                inputProps={{ ...params.inputProps, style: { fontFamily: monoFontFamily, fontSize: "0.75rem" } }}
              />
            )}
            renderOption={(props, option) => {
              const item = typeof option === "string" ? { path: option, name: option } : option;
              return (
              <li {...props} key={item.path}>
                <Typography sx={{ fontFamily: monoFontFamily, fontSize: "0.7rem" }}>{item.name}</Typography>
              </li>
              );
            }}
          />
          <Button variant="contained" onClick={handleOpen} disabled={!inputPath.trim() || inputPath.trim() === activePath}>
            Open
          </Button>

          {hasFile && extensions.length > 0 && extensions.filter((h) => h.has_image).length > 1 && (
            <>
              <Divider orientation="vertical" flexItem />
              <HduSelector
                hdus={extensions}
                selected={selectedHdu}
                onChange={(i) => { setSelectedHdu(i); setTab(0); }}
              />
            </>
          )}
        </Box>

        {/* Loading */}
        {hasFile && extensionsQuery.isLoading && (
          <Box sx={{ display: "flex", alignItems: "center", justifyContent: "center", flexGrow: 1 }}>
            <CircularProgress size={32} />
          </Box>
        )}

        {/* Tabs + content */}
        {hasFile && !extensionsQuery.isError && !extensionsQuery.isLoading && (
          <>
            <Tabs
              value={tab}
              onChange={(_, v) => setTab(v)}
              sx={{ px: 2, flexShrink: 0, borderBottom: 1, borderColor: "divider" }}
            >
              <Tab label="Image" disabled={!selectedExtInfo?.has_image} />
              <Tab label="Header" />
            </Tabs>

            {/* Image tab — kept mounted, hidden via CSS to avoid re-fetching */}
            <Box sx={{ flexGrow: 1, overflow: "hidden", display: tab === 0 ? "flex" : "none", flexDirection: "column" }}>
              {selectedExtInfo?.has_image ? (
                <>
                  <Box sx={{ flexGrow: 1, overflow: "hidden" }}>
                    <FitsImage
                      ref={imageRef}
                      path={activePath}
                      hdu={selectedHdu}
                      linked={debouncedLinked}
                      perChannel={hasStretch ? activePerChannel : undefined}
                      onZoomChange={setCurrentZoom}
                    />
                  </Box>
                  {(fileName || dateObs || exposure || filter) && (
                    <Box
                      sx={{
                        display: "flex",
                        gap: 2,
                        px: 1.5,
                        py: 0.5,
                        borderTop: 1,
                        borderColor: "divider",
                        flexShrink: 0,
                      }}
                    >
                      {fileName && (
                        <Typography variant="caption" color="text.secondary" fontFamily={monoFontFamily}>
                          {fileName}
                        </Typography>
                      )}
                      {dateObs && (
                        <Typography variant="caption" color="text.secondary">
                          {dateObs}
                        </Typography>
                      )}
                      {exposure && (
                        <Typography variant="caption" color="text.secondary">
                          {exposure}s
                        </Typography>
                      )}
                      {filter && (
                        <Typography variant="caption" color="text.secondary">
                          {filter}
                        </Typography>
                      )}
                    </Box>
                  )}
                </>
              ) : (
                <Box sx={{ display: "flex", alignItems: "center", justifyContent: "center", height: "100%" }}>
                  <Typography color="text.secondary">Selected extension has no image data</Typography>
                </Box>
              )}
            </Box>

            {/* Header tab */}
            <Box sx={{ flexGrow: 1, overflow: "hidden", display: tab === 1 ? "flex" : "none", flexDirection: "column" }}>
              {headerQuery.isLoading && (
                <Typography sx={{ p: 2 }} color="text.secondary">Loading header…</Typography>
              )}
              {!headerQuery.isLoading && headerQuery.data && (
                <FitsHeaderTable cards={headerQuery.data} />
              )}
            </Box>
          </>
        )}

        {/* Empty state */}
        {!hasFile && (
          <Box sx={{ display: "flex", alignItems: "center", justifyContent: "center", flexGrow: 1 }}>
            <Box sx={{ display: "flex", flexDirection: "column", alignItems: "center", gap: 2, maxWidth: 400 }}>
              <ImageSearchIcon sx={{ fontSize: 48, color: "text.secondary", opacity: 0.4 }} />
              <Typography variant="body1" color="text.secondary" textAlign="center">
                Open an image file to view it here
              </Typography>
              <Button
                variant="outlined"
                onClick={() => setBrowserOpen(true)}
                startIcon={<FolderOpenIcon />}
              >
                Browse Files
              </Button>
              <Box sx={{ display: "flex", gap: 0.5, flexWrap: "wrap", justifyContent: "center" }}>
                {["FITS", "XISF", "PNG", "JPEG", "TIFF"].map((fmt) => (
                  <Chip key={fmt} label={fmt} size="small" variant="outlined" sx={{ fontSize: "0.7rem", height: 22 }} />
                ))}
              </Box>
              <Typography variant="caption" color="text.secondary" sx={{ mt: 1, opacity: 0.6 }}>
                {"\u2318"}O / Ctrl+O to browse &nbsp;&bull;&nbsp; F to fit &nbsp;&bull;&nbsp; 1 for 1:1
              </Typography>
            </Box>
          </Box>
        )}
      </Box>

      {/* Right sidebar — only when an image is open and on the Image tab */}
      {hasFile && selectedExtInfo?.has_image && tab === 0 && (
        <Box
          sx={{
            width: isColor && !isLinked && linked.stretch === "stf" ? 600 : 220,
            flexShrink: 0,
            borderLeft: 1,
            borderColor: "divider",
            overflowY: "auto",
            overflowX: "hidden",
          }}
        >
          {/* Image Size section */}
          <Typography variant="caption" color="text.secondary" sx={{ px: 1.5, pt: 1.5, display: "block" }}>
            IMAGE SIZE
          </Typography>
          <Box sx={{ display: "flex", alignItems: "center", gap: 0.5, px: 1.5, py: 1 }}>
            <Button
              variant="outlined"
              size="small"
              onClick={() => imageRef.current?.fitToWindow()}
              startIcon={<FitScreenIcon sx={{ fontSize: 14 }} />}
              sx={{ fontSize: "0.7rem", py: 0.25, px: 1, minWidth: 0 }}
            >
              Fit
            </Button>
            <Button
              variant="outlined"
              size="small"
              onClick={() => imageRef.current?.oneToOne()}
              startIcon={<OneKIcon sx={{ fontSize: 14 }} />}
              sx={{ fontSize: "0.7rem", py: 0.25, px: 1, minWidth: 0 }}
            >
              1:1
            </Button>
            <Typography variant="caption" color="text.secondary" sx={{ ml: "auto", fontFamily: monoFontFamily }}>
              {(currentZoom * 100).toFixed(0)}%
            </Typography>
          </Box>

          {/* Stretch section — only for FITS/XISF */}
          {hasStretch && (
            <>
              <Divider sx={{ mx: 1.5 }} />
              <Typography variant="caption" color="text.secondary" sx={{ px: 1.5, pt: 1, display: "block" }}>
                STRETCH
              </Typography>
              <StretchControls
                isColor={isColor}
                linked={linked}
                perChannel={perChannel}
                isLinked={isLinked}
                onLinkedChange={setLinked}
                onPerChannelChange={setPerChannel}
                onLinkedToggle={handleLinkedToggle}
                onReset={handleReset}
              />
            </>
          )}
        </Box>
      )}

      {/* File browser dialog */}
      <FileBrowser
        open={browserOpen}
        onClose={() => setBrowserOpen(false)}
        onSelect={(path, displayName) => openFile(path, displayName)}
      />

      {/* Error notification */}
      <Snackbar
        open={errorMsg !== null}
        autoHideDuration={6000}
        onClose={() => setErrorMsg(null)}
        anchorOrigin={{ vertical: "bottom", horizontal: "center" }}
      >
        <Alert severity="error" onClose={() => setErrorMsg(null)} variant="filled">
          {errorMsg}
        </Alert>
      </Snackbar>
    </Box>
  );
}
