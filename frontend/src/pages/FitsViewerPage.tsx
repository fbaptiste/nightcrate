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
import FitScreenIcon from "@mui/icons-material/FitScreen";
import FolderOpenIcon from "@mui/icons-material/FolderOpen";
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

export function FitsViewerPage() {
  const [inputPath, setInputPath] = useState("");
  const [activePath, setActivePath] = useState("");
  const [selectedHdu, setSelectedHdu] = useState(0);
  const [tab, setTab] = useState(0);
  const imageRef = useRef<FitsImageHandle>(null);
  const [currentZoom, setCurrentZoom] = useState(1);

  // File browser
  const [browserOpen, setBrowserOpen] = useState(false);

  // Stretch state
  const [linked, setLinked] = useState<StretchParams>({ ...DEFAULT_STRETCH });
  const [perChannel, setPerChannel] = useState<[StretchParams, StretchParams, StretchParams]>(DEFAULT_PER_CHANNEL);
  const [isLinked, setIsLinked] = useState(true);

  const debouncedLinked = useDebounce(linked, 300);
  const debouncedPerChannel = useDebounce(perChannel, 300);
  const debouncedIsLinked = useDebounce(isLinked, 300);

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

  // Auto-apply STF defaults when stats arrive
  useEffect(() => {
    if (statsQuery.data) {
      applyAutoStf(statsQuery.data, setLinked, setPerChannel);
    }
  }, [statsQuery.data]);

  function openFile(path: string) {
    setSelectedHdu(0);
    setTab(0);
    setLinked({ ...DEFAULT_STRETCH });
    setPerChannel(DEFAULT_PER_CHANNEL);
    setIsLinked(true);
    setInputPath(path);
    setActivePath(path);
    recordRecentFile(path).then(() => recentQuery.refetch());
  }

  function handleOpen() {
    const p = inputPath.trim();
    if (p) openFile(p);
  }

  const handleReset = useCallback(() => {
    if (statsQuery.data) {
      applyAutoStf(statsQuery.data, setLinked, setPerChannel);
      setIsLinked(true);
    }
  }, [statsQuery.data]);

  const handleLinkedToggle = useCallback((val: boolean) => {
    setIsLinked(val);
    if (!val) {
      setPerChannel([{ ...linked }, { ...linked }, { ...linked }]);
    }
  }, [linked]);

  const extensions = extensionsQuery.data ?? [];
  const selectedExtInfo = extensions.find((h) => h.index === selectedHdu);
  const hasFile = activePath !== "";
  const isColor = statsQuery.data?.color ?? false;

  // Display metadata
  const headerCards = headerQuery.data ?? [];
  const headerVal = (key: string) => {
    const card = headerCards.find((c) => c.key === key);
    return card?.value && card.value !== "" && card.value !== "None" ? card.value : null;
  };
  const fileName = activePath ? activePath.split("/").pop() ?? null : null;
  const dateObs = formatDateObs(headerVal("DATE-OBS"));
  const exposure = headerVal("EXPTIME");
  const filter = headerVal("FILTER");

  const activePerChannel = (isColor && !debouncedIsLinked) ? debouncedPerChannel : undefined;

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
            options={recentFiles.map((f) => f.path)}
            filterOptions={(options) => options}
            inputValue={inputPath}
            onInputChange={(_, value, reason) => {
              if (reason !== "reset") setInputPath(value);
            }}
            onChange={(_, value) => { if (value) openFile(value); }}
            sx={{ flexGrow: 1 }}
            slotProps={{ listbox: { style: { maxHeight: 320 } } }}
            renderInput={(params) => (
              <TextField
                {...params}
                size="small"
                placeholder="Path to image file…"
                onKeyDown={(e) => e.key === "Enter" && handleOpen()}
                inputProps={{ ...params.inputProps, style: { fontFamily: "monospace", fontSize: "0.75rem" } }}
              />
            )}
            renderOption={(props, option) => (
              <li {...props} key={option}>
                <Typography sx={{ fontFamily: "monospace", fontSize: "0.7rem" }}>{option}</Typography>
              </li>
            )}
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

        {/* Error */}
        {extensionsQuery.isError && (
          <Alert severity="error" sx={{ mx: 2, mt: 1 }}>
            {String(extensionsQuery.error)}
          </Alert>
        )}

        {/* Tabs + content */}
        {hasFile && !extensionsQuery.isError && (
          <>
            <Tabs
              value={tab}
              onChange={(_, v) => setTab(v)}
              sx={{ px: 2, flexShrink: 0, borderBottom: 1, borderColor: "divider" }}
            >
              <Tab label="Image" disabled={!selectedExtInfo?.has_image} />
              <Tab label="Header" />
            </Tabs>

            <Box sx={{ flexGrow: 1, overflow: "hidden", display: "flex", flexDirection: "column" }}>
              {tab === 0 && selectedExtInfo?.has_image && (
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
                        <Typography variant="caption" color="text.secondary" fontFamily="monospace">
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
              )}
              {tab === 0 && !selectedExtInfo?.has_image && (
                <Box sx={{ display: "flex", alignItems: "center", justifyContent: "center", height: "100%" }}>
                  <Typography color="text.secondary">Selected extension has no image data</Typography>
                </Box>
              )}
              {tab === 1 && headerQuery.isLoading && (
                <Typography sx={{ p: 2 }} color="text.secondary">Loading header…</Typography>
              )}
              {tab === 1 && !headerQuery.isLoading && headerQuery.data && (
                <FitsHeaderTable cards={headerQuery.data} />
              )}
            </Box>
          </>
        )}

        {/* Empty state */}
        {!hasFile && (
          <Box sx={{ display: "flex", alignItems: "center", justifyContent: "center", flexGrow: 1 }}>
            <Typography color="text.secondary">Enter a path or click Browse to open an image file</Typography>
          </Box>
        )}
      </Box>

      {/* Right sidebar — only when an image is open and on the Image tab */}
      {hasFile && selectedExtInfo?.has_image && tab === 0 && (
        <Box
          sx={{
            width: isColor && !isLinked ? 600 : 220,
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
            <Typography variant="caption" color="text.secondary" sx={{ ml: "auto", fontFamily: "monospace" }}>
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
        onSelect={(path) => openFile(path)}
      />
    </Box>
  );
}
