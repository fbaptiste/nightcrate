import { Fragment, useCallback, useEffect, useRef, useState } from "react";
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
import Slider from "@mui/material/Slider";
import Snackbar from "@mui/material/Snackbar";
import Tooltip from "@mui/material/Tooltip";
import FitScreenIcon from "@mui/icons-material/FitScreen";
import FolderOpenIcon from "@mui/icons-material/FolderOpen";
import ImageSearchIcon from "@mui/icons-material/ImageSearch";
import OneKIcon from "@mui/icons-material/PhotoSizeSelectActual";
import {
  DEFAULT_STRETCH,
  fetchExtensions,
  fetchHeader,
  fetchImageStats,
  fetchMetadata,
  fetchRecentFiles,
  isVirtualPath,
  recordRecentFile,
  stfToStretch,
  type ImageStats,
  type RecentFile,
  type StretchParams,
} from "@/api/images";
import { analyzeFrame, fetchSamples, reaggregateSquare, DEFAULT_STAR_FILTERS, type SampleSquare, type AberrationMetric, type StarFilters } from "@/api/aberration";
import { AberrationToolbar } from "@/components/aberration/AberrationToolbar";
import { CropGrid } from "@/components/aberration/CropGrid";
import { AberrationSidebar } from "@/components/aberration/AberrationSidebar";
import { ZoneOverlayMap } from "@/components/aberration/ZoneOverlayMap";
import { SidebarSection } from "@/components/SidebarSection";
import { FileBrowser } from "@/components/fits/FileBrowser";
import { FitsHeaderTable } from "@/components/fits/FitsHeaderTable";
import { FitsImage, type FitsImageHandle, type PixelInfo } from "@/components/fits/FitsImage";
import { HduSelector } from "@/components/fits/HduSelector";
import { Histogram } from "@/components/fits/Histogram";
import { StretchControls } from "@/components/fits/StretchControls";
import { CHANNEL_COLOR_ARRAY, CHANNEL_COLORS, LUMINOSITY_COLOR } from "@/lib/channelColors";
import { rgbToHex, findColorName } from "@/lib/colorName";
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

  // Pixel inspector
  const [pixelInspectorOn, setPixelInspectorOn] = useState(false);
  const [pixelData, setPixelData] = useState<PixelInfo | null>(null);
  const [patchRadius, setPatchRadius] = useState(50);

  // Error notification
  const [errorMsg, setErrorMsg] = useState<string | null>(null);

  // Stretch state
  const [linked, setLinked] = useState<StretchParams>({ ...DEFAULT_STRETCH });
  const [perChannel, setPerChannel] = useState<[StretchParams, StretchParams, StretchParams]>(DEFAULT_PER_CHANNEL);
  const [isLinked, setIsLinked] = useState(true);

  const debouncedLinked = useDebounce(linked, 300);
  const debouncedPerChannel = useDebounce(perChannel, 300);

  // Aberration state
  const [samplesAcross, setSamplesAcross] = useState(5);
  const [aberrationMetric, setAberrationMetric] = useState<AberrationMetric>("eccentricity");
  const [starFilters, setStarFilters] = useState<StarFilters>({ ...DEFAULT_STAR_FILTERS });
  const [selectedSquare, setSelectedSquare] = useState<SampleSquare | null>(null);
  const [customSquares, setCustomSquares] = useState<SampleSquare[] | null>(null);

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

  // Whether the active file supports stretch — authoritative, from backend
  const hasStretch = extensionsQuery.data?.[0]?.supports_stretch === true;

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

  const metadataQuery = useQuery({
    queryKey: ["metadata", activePath, selectedHdu],
    queryFn: () => fetchMetadata(activePath, selectedHdu),
    enabled: activePath !== "",
  });

  const debouncedFilters = useDebounce(starFilters, 500);

  const aberrationQuery = useQuery({
    queryKey: ["aberration", activePath, selectedHdu, debouncedFilters],
    queryFn: () => analyzeFrame(activePath, selectedHdu, debouncedFilters),
    enabled: activePath !== "" && tab === 2,
  });

  const samplesQuery = useQuery({
    queryKey: ["samples", activePath, selectedHdu, samplesAcross, debouncedFilters],
    queryFn: () => fetchSamples(activePath, selectedHdu, samplesAcross, debouncedFilters),
    enabled: aberrationQuery.data != null,
  });

  // Reset custom square positions when a fresh grid arrives from the backend
  useEffect(() => {
    setCustomSquares(null);
    setSelectedSquare(null);
  }, [samplesQuery.data]);

  // Active squares: custom positions if user has dragged, otherwise backend defaults
  const activeSquares = customSquares ?? samplesQuery.data?.squares ?? [];

  // Handle square drag — re-aggregate stars client-side
  const handleSquareMoved = useCallback((movedSq: SampleSquare) => {
    if (!aberrationQuery.data) return;
    const stars = aberrationQuery.data.stars;
    const base = customSquares ?? samplesQuery.data?.squares ?? [];
    const updated = base.map((sq) =>
      sq.row === movedSq.row && sq.col === movedSq.col
        ? reaggregateSquare(movedSq, stars)
        : sq,
    );
    setCustomSquares(updated);
    // Update selected square if it was the one moved
    if (selectedSquare?.row === movedSq.row && selectedSquare?.col === movedSq.col) {
      setSelectedSquare(updated.find((s) => s.row === movedSq.row && s.col === movedSq.col) ?? null);
    }
  }, [aberrationQuery.data, customSquares, samplesQuery.data?.squares, selectedSquare]);

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
    setSelectedSquare(null);
    // For project images, show a readable path in the input
    if (isVirtualPath(path) && displayName) {
      const projPath = path.split("::")[0];
      setInputPath(`${projPath} / ${displayName}`);
    } else {
      setInputPath(path);
    }
    setActivePath(path);
    recordRecentFile(path).then(() => recentQuery.refetch());
  }

  function handleOpen() {
    // Don't re-open if a project image is already active (inputPath is a display string)
    if (isVirtualPath(activePath)) return;
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
  const projectImageName = isVirtualPath(activePath)
    ? (extensionsQuery.data?.[0]?.name ?? null)
    : null;
  const fileName = activePath
    ? isVirtualPath(activePath)
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
                const name = typeof value === "string" ? undefined : (isVirtualPath(value.path) ? value.name : undefined);
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
          <Button variant="contained" onClick={handleOpen} disabled={!inputPath.trim() || inputPath.trim() === activePath || isVirtualPath(activePath)}>
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
            <Box sx={{ display: "flex", alignItems: "center", borderBottom: 1, borderColor: "divider", flexShrink: 0 }}>
              <Tabs
                value={tab}
                onChange={(_, v) => setTab(v)}
                sx={{ px: 2 }}
              >
                <Tab label="Image" disabled={!selectedExtInfo?.has_image} />
                <Tab label="Header" />
                <Tab label="Aberration" disabled={!hasFile || !selectedExtInfo?.has_image} />
              </Tabs>
              {/* Format and linearity indicators */}
              <Box sx={{ display: "flex", gap: 0.5, ml: "auto", mr: 2 }}>
                <Chip
                  label={isVirtualPath(activePath) ? "PXI" : activePath.split(".").pop()?.toUpperCase() ?? ""}
                  size="small"
                  variant="outlined"
                  sx={{ fontSize: "0.65rem", height: 20 }}
                />
                {hasStretch && (
                  <Chip
                    label={linked.stretch === "stf" ? "Linear" : "Non-linear"}
                    size="small"
                    variant="outlined"
                    sx={{ fontSize: "0.65rem", height: 20 }}
                  />
                )}
              </Box>
            </Box>

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
                      onPixelHover={pixelInspectorOn ? setPixelData : undefined}
                      pixelPatchRadius={patchRadius}
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
                  {/* Histogram — below image */}
                  <Histogram
                    path={activePath}
                    hdu={selectedHdu}
                    shadow={linked.shadow}
                    midtone={linked.midtone}
                    highlight={linked.highlight}
                    isStretching={hasStretch && linked.stretch === "stf"}
                    channelIntensities={
                      isColor && statsQuery.data
                        ? statsQuery.data.channels.map((ch, i) => ({
                            name: ["R", "G", "B"][i] ?? `${i}`,
                            median: ch.median,
                            mad: ch.mad,
                            color: CHANNEL_COLOR_ARRAY[i] ?? LUMINOSITY_COLOR,
                          }))
                        : undefined
                    }
                  />
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

            {/* Aberration tab content */}
            <Box sx={{ flexGrow: 1, overflow: "hidden", display: tab === 2 ? "flex" : "none", flexDirection: "column" }}>
              <AberrationToolbar
                samplesAcross={samplesAcross}
                onSamplesChange={(n) => { setSamplesAcross(n); setSelectedSquare(null); }}
                metric={aberrationMetric}
                onMetricChange={setAberrationMetric}
                filters={starFilters}
                onFiltersChange={setStarFilters}
                analyzing={aberrationQuery.isFetching}
              />
              <Box sx={{ flexGrow: 1, overflow: "auto", display: "flex", flexDirection: "column" }}>
                {/* Reference image with sample square markers */}
                {aberrationQuery.data && samplesQuery.data && (
                  <Box sx={{ height: 200, flexShrink: 0, display: "flex", justifyContent: "center", alignItems: "center", bgcolor: "#000", p: 0.5, gap: 0.5 }}>
                    <ZoneOverlayMap
                      path={activePath}
                      hdu={selectedHdu}
                      linked={debouncedLinked}
                      grid={samplesQuery.data}
                      squares={activeSquares}
                      selectedSquare={selectedSquare}
                      onSquareClick={setSelectedSquare}
                      onSquareMoved={handleSquareMoved}
                    />
                    <Tooltip title="Reset all squares to original positions" arrow>
                      <Button
                        size="small"
                        variant="text"
                        onClick={() => { setCustomSquares(null); setSelectedSquare(null); }}
                        sx={{
                          fontSize: "0.6rem", minWidth: 0, px: 0.5, writingMode: "vertical-rl", textOrientation: "mixed",
                          color: customSquares ? "text.secondary" : "transparent",
                          pointerEvents: customSquares ? "auto" : "none",
                        }}
                      >
                        Reset
                      </Button>
                    </Tooltip>
                  </Box>
                )}
                {samplesQuery.data && aberrationQuery.data && (
                  <CropGrid
                    grid={samplesQuery.data}
                    squares={activeSquares}
                    stars={aberrationQuery.data.stars}
                    path={activePath}
                    hdu={selectedHdu}
                    metric={aberrationMetric}
                    selectedSquare={selectedSquare}
                    onSquareClick={setSelectedSquare}
                  />
                )}
                {aberrationQuery.isLoading && (
                  <Box sx={{ display: "flex", justifyContent: "center", alignItems: "center", height: "100%" }}>
                    <CircularProgress size={32} />
                  </Box>
                )}
                {aberrationQuery.isError && (
                  <Alert severity="error" sx={{ m: 2 }}>{String(aberrationQuery.error)}</Alert>
                )}
              </Box>
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
                {["FITS", "XISF", "PXI Project", "PNG", "JPEG", "TIFF"].map((fmt) => (
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

      {/* Right sidebar — only when an image is open and on the Image or Aberration tab */}
      {hasFile && selectedExtInfo?.has_image && (tab === 0 || tab === 2) && (
        <Box
          sx={{
            width: 220,
            flexShrink: 0,
            borderLeft: 1,
            borderColor: "divider",
            overflowY: "auto",
            overflowX: "hidden",
            display: "flex",
            flexDirection: "column",
          }}
        >
          {tab === 0 && (
          <>
          {/* Key fields summary — curated header info */}
          <SidebarSection label="Image Info">
          {(() => {
            const meta = metadataQuery.data?.canonical;
            if (!meta || Object.keys(meta).length === 0) {
              return (
                <Typography variant="caption" color="text.secondary" sx={{ px: 1.5, py: 0.5, fontSize: "0.65rem" }}>
                  No metadata available
                </Typography>
              );
            }
            const displayFields: [string, string][] = [
              ["object_name", "Object"],
              ["filter_name", "Filter"],
              ["exposure_time", "Exposure"],
              ["gain", "Gain"],
              ["sensor_temp", "Sensor"],
              ["camera_name", "Camera"],
              ["telescope_name", "Telescope"],
              ["focal_length", "Focal Len"],
              ["frame_type", "Type"],
            ];
            const rows = displayFields
              .filter(([key]) => meta[key] != null && String(meta[key]).trim() !== "")
              .map(([key, label]) => {
                let val: React.ReactNode = String(meta[key]);
                if (key === "exposure_time") val = `${meta[key]}s`;
                if (key === "sensor_temp") val = `${meta[key]}\u00B0C`;
                if (key === "focal_length") {
                  val = <>{Number(meta[key]).toFixed(0)} mm{meta["focal_ratio"] != null && <span style={{ color: "var(--mui-palette-text-secondary)" }}> (f/{Number(meta["focal_ratio"]).toFixed(1)})</span>}</>;
                }
                return { label, val };
              });
            return rows.length > 0 ? (
              <Box sx={{ px: 1.5, py: 0.5, display: "grid", gridTemplateColumns: "auto 1fr", columnGap: 1, rowGap: 0.125, fontSize: "0.65rem", fontFamily: monoFontFamily }}>
                {rows.map(({ label, val }) => (
                  <Fragment key={label}>
                    <Typography sx={{ fontSize: "inherit", fontFamily: "inherit", color: "text.secondary", whiteSpace: "nowrap" }}>{label}</Typography>
                    <Typography sx={{ fontSize: "inherit", fontFamily: "inherit" }}>{val}</Typography>
                  </Fragment>
                ))}
              </Box>
            ) : (
              <Typography variant="caption" color="text.secondary" sx={{ px: 1.5, py: 0.5, fontSize: "0.65rem" }}>
                No metadata available
              </Typography>
            );
          })()}
          </SidebarSection>

          {/* Image Size section */}
          <SidebarSection label="Image Size">
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
          </SidebarSection>

          {/* Stretch section — for stretchable formats */}
          {hasStretch && (
            <SidebarSection label="Stretch" defaultOpen={false}>
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
            </SidebarSection>
          )}

          {/* Pixel inspector — enabled when expanded */}
          <SidebarSection label="Pixel Inspector" defaultOpen={false} open={pixelInspectorOn} onToggle={(v) => { setPixelInspectorOn(v); if (!v) setPixelData(null); }}>
            <Box sx={{ px: 1.5, py: 0.5 }}>
              {/* Magnified patch view with zoom slider */}
              <Box sx={{ mb: 0.75, display: "flex", alignItems: "stretch", gap: 0.75, justifyContent: "center" }}>
                <canvas
                  ref={(el) => {
                    if (!el) return;
                    const displaySize = 120;
                    const dpr = window.devicePixelRatio || 1;
                    el.width = displaySize * dpr;
                    el.height = displaySize * dpr;
                    el.style.width = `${displaySize}px`;
                    el.style.height = `${displaySize}px`;
                    const ctx = el.getContext("2d");
                    if (!ctx) return;
                    ctx.scale(dpr, dpr);
                    ctx.imageSmoothingEnabled = false;

                    if (pixelData?.patch) {
                      const tmpCanvas = document.createElement("canvas");
                      tmpCanvas.width = pixelData.patch.width;
                      tmpCanvas.height = pixelData.patch.height;
                      const tmpCtx = tmpCanvas.getContext("2d");
                      if (tmpCtx) {
                        tmpCtx.putImageData(pixelData.patch, 0, 0);
                        ctx.drawImage(tmpCanvas, 0, 0, displaySize, displaySize);
                      }
                    } else {
                      ctx.fillStyle = "#000";
                      ctx.fillRect(0, 0, displaySize, displaySize);
                    }

                    // Reticle
                    const center = displaySize / 2;
                    const r = 6;
                    const gap = r + 2;
                    ctx.strokeStyle = "#000";
                    ctx.lineWidth = 2.5;
                    ctx.beginPath();
                    ctx.arc(center, center, r, 0, Math.PI * 2);
                    ctx.stroke();
                    ctx.beginPath();
                    ctx.moveTo(center, 0); ctx.lineTo(center, center - gap);
                    ctx.moveTo(center, center + gap); ctx.lineTo(center, displaySize);
                    ctx.moveTo(0, center); ctx.lineTo(center - gap, center);
                    ctx.moveTo(center + gap, center); ctx.lineTo(displaySize, center);
                    ctx.stroke();
                    ctx.strokeStyle = "#d4993f";
                    ctx.lineWidth = 1;
                    ctx.beginPath();
                    ctx.arc(center, center, r, 0, Math.PI * 2);
                    ctx.stroke();
                    ctx.beginPath();
                    ctx.moveTo(center, 0); ctx.lineTo(center, center - gap);
                    ctx.moveTo(center, center + gap); ctx.lineTo(center, displaySize);
                    ctx.moveTo(0, center); ctx.lineTo(center - gap, center);
                    ctx.moveTo(center + gap, center); ctx.lineTo(displaySize, center);
                    ctx.stroke();
                  }}
                  style={{ borderRadius: 4, border: "1px solid var(--mui-palette-divider)" }}
                />
                <Slider
                  orientation="vertical"
                  min={10}
                  max={150}
                  value={patchRadius}
                  onChange={(_, v) => setPatchRadius(v as number)}
                  size="small"
                  sx={{
                    height: 120,
                    "& .MuiSlider-thumb": { width: 10, height: 10 },
                  }}
                />
              </Box>
              <table style={{ borderCollapse: "collapse", fontSize: "0.65rem", fontFamily: monoFontFamily }}>
                <tbody>
                  <tr>
                    <td style={{ color: "var(--mui-palette-text-secondary)", paddingRight: 8 }}>X, Y</td>
                    <td>{pixelData ? `${pixelData.x}, ${pixelData.y}` : "—, —"}</td>
                  </tr>
                  <tr>
                    <td style={{ color: CHANNEL_COLORS.R, paddingRight: 8 }}>R</td>
                    <td>{pixelData ? pixelData.R.toFixed(5) : "0.00000"}</td>
                  </tr>
                  <tr>
                    <td style={{ color: CHANNEL_COLORS.G, paddingRight: 8 }}>G</td>
                    <td>{pixelData ? pixelData.G.toFixed(5) : "0.00000"}</td>
                  </tr>
                  <tr>
                    <td style={{ color: CHANNEL_COLORS.B, paddingRight: 8 }}>B</td>
                    <td>{pixelData ? pixelData.B.toFixed(5) : "0.00000"}</td>
                  </tr>
                  <tr>
                    <td style={{ color: LUMINOSITY_COLOR, paddingRight: 8 }}>K</td>
                    <td>{pixelData ? pixelData.K.toFixed(5) : "0.00000"}</td>
                  </tr>
                  <tr>
                    <td style={{ color: "var(--mui-palette-text-secondary)", paddingRight: 8 }}>Hex</td>
                    <td>{pixelData ? rgbToHex(pixelData.R, pixelData.G, pixelData.B) : "#000000"}</td>
                  </tr>
                  <tr>
                    <td style={{ color: "var(--mui-palette-text-secondary)", paddingRight: 8, verticalAlign: "top" }}>Color</td>
                    <td>
                      <Box component="span" sx={{ display: "inline-flex", alignItems: "center", gap: 0.5 }}>
                        <Box
                          sx={{
                            width: 8,
                            height: 8,
                            borderRadius: "50%",
                            bgcolor: pixelData ? rgbToHex(pixelData.R, pixelData.G, pixelData.B) : "#000",
                            border: "1px solid rgba(255,255,255,0.2)",
                            flexShrink: 0,
                          }}
                        />
                        {pixelData ? findColorName(pixelData.R, pixelData.G, pixelData.B) : "black"}
                      </Box>
                    </td>
                  </tr>
                </tbody>
              </table>
            </Box>
          </SidebarSection>

          {/* Pixel statistics — shown when stats are available */}
          {statsQuery.data && (
            <SidebarSection label="Statistics">
              <Box sx={{ px: 1.5, py: 0.5, display: "flex", flexDirection: "column", gap: 1 }}>
                {statsQuery.data.channels.map((ch, i) => {
                  const label = statsQuery.data!.color ? ["R", "G", "B"][i] ?? `${i}` : "L";
                  const chColor = statsQuery.data!.color ? (CHANNEL_COLOR_ARRAY[i] ?? LUMINOSITY_COLOR) : LUMINOSITY_COLOR;
                  const delta = statsQuery.data!.background_delta?.[i];
                  return (
                    <Box key={i}>
                      <Typography sx={{ fontSize: "0.65rem", fontFamily: monoFontFamily, color: chColor, fontWeight: 600, mb: 0.25 }}>
                        {label}
                      </Typography>
                      <Box sx={{ display: "grid", gridTemplateColumns: "auto 1fr", columnGap: 1, rowGap: 0.125, fontSize: "0.65rem", fontFamily: monoFontFamily }}>
                        <Tooltip title="Median pixel value" arrow>
                          <Typography sx={{ fontSize: "inherit", fontFamily: "inherit", color: "text.secondary", cursor: "help" }}>Med</Typography>
                        </Tooltip>
                        <Typography sx={{ fontSize: "inherit", fontFamily: "inherit", textAlign: "right" }}>{ch.median.toFixed(6)}</Typography>

                        <Tooltip title="Median Absolute Deviation — noise measure" arrow>
                          <Typography sx={{ fontSize: "inherit", fontFamily: "inherit", color: "text.secondary", cursor: "help" }}>MAD</Typography>
                        </Tooltip>
                        <Typography sx={{ fontSize: "inherit", fontFamily: "inherit", textAlign: "right" }}>{ch.mad.toFixed(6)}</Typography>

                        <Tooltip title="Average Deviation — used by auto stretch algorithm" arrow>
                          <Typography sx={{ fontSize: "inherit", fontFamily: "inherit", color: "text.secondary", cursor: "help" }}>AvgDev</Typography>
                        </Tooltip>
                        <Typography sx={{ fontSize: "inherit", fontFamily: "inherit", textAlign: "right" }}>{ch.avg_dev.toFixed(6)}</Typography>

                        <Tooltip title="Signal-to-Noise Ratio (median / σ)" arrow>
                          <Typography sx={{ fontSize: "inherit", fontFamily: "inherit", color: "text.secondary", cursor: "help" }}>SNR</Typography>
                        </Tooltip>
                        <Typography sx={{ fontSize: "inherit", fontFamily: "inherit", textAlign: "right" }}>{ch.snr.toFixed(1)}</Typography>

                        {delta != null && (
                          <>
                            <Tooltip title="Background deviation from channel mean — shows color balance" arrow>
                              <Typography sx={{ fontSize: "inherit", fontFamily: "inherit", color: "text.secondary", cursor: "help" }}>Δbkg</Typography>
                            </Tooltip>
                            <Typography sx={{ fontSize: "inherit", fontFamily: "inherit", textAlign: "right", color: Math.abs(delta) < 0.001 ? "inherit" : "#d4993f" }}>
                              {delta >= 0 ? "+" : ""}{delta.toFixed(6)}
                            </Typography>
                          </>
                        )}
                      </Box>
                    </Box>
                  );
                })}

                {/* Lab a* color balance diagnostic — color images only */}
                {statsQuery.data.lab_a_median != null && (
                  <Box sx={{ display: "grid", gridTemplateColumns: "auto 1fr", columnGap: 1, fontSize: "0.65rem", fontFamily: monoFontFamily, alignItems: "baseline" }}>
                    <Tooltip title="CIE L*a*b* a* median — positive = red/magenta excess, negative = green excess. Near zero = neutral." arrow>
                      <Typography sx={{ fontSize: "inherit", fontFamily: "inherit", color: "text.secondary", cursor: "help" }}>a* median</Typography>
                    </Tooltip>
                    <Box sx={{ display: "flex", justifyContent: "flex-end", alignItems: "baseline", gap: 0.75 }}>
                      <Typography sx={{ fontSize: "inherit", fontFamily: "inherit" }}>
                        {statsQuery.data.lab_a_median.toFixed(3)}
                      </Typography>
                      <Typography sx={{
                        fontSize: "0.65rem",
                        color: Math.abs(statsQuery.data.lab_a_median) < 0.5
                          ? "text.secondary"
                          : statsQuery.data.lab_a_median > 0 ? CHANNEL_COLORS.G : CHANNEL_COLORS.R,
                      }}>
                        {Math.abs(statsQuery.data.lab_a_median) < 0.5
                          ? "neutral"
                          : statsQuery.data.lab_a_median > 0 ? "warm excess" : "cool excess"}
                      </Typography>
                    </Box>
                  </Box>
                )}
              </Box>
            </SidebarSection>
          )}

          {/* Spacer pushes help to bottom */}
          <Box sx={{ flexGrow: 1 }} />

          {/* Help tips */}
          <SidebarSection label="Help" defaultOpen={false}>
            <Box sx={{ px: 1.5, pb: 1.5 }}>
              <Typography variant="caption" color="text.secondary" sx={{ fontSize: "0.65rem", display: "block", lineHeight: 2 }}>
                Scroll to zoom<br />
                Click + drag to pan<br />
                F &mdash; fit to window<br />
                1 &mdash; 1:1 pixel zoom<br />
                {"\u2318"}O / Ctrl+O &mdash; browse files
              </Typography>
            </Box>
          </SidebarSection>
          </>
          )}
          {tab === 2 && (
            <AberrationSidebar
              analysis={aberrationQuery.data ?? null}
            />
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
