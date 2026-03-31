import { useCallback, useEffect, useRef, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import Alert from "@mui/material/Alert";
import Box from "@mui/material/Box";
import Button from "@mui/material/Button";
import Divider from "@mui/material/Divider";
import Tab from "@mui/material/Tab";
import Tabs from "@mui/material/Tabs";
import TextField from "@mui/material/TextField";
import Typography from "@mui/material/Typography";
import FitScreenIcon from "@mui/icons-material/FitScreen";
import OneKIcon from "@mui/icons-material/PhotoSizeSelectActual";
import {
  DEFAULT_STRETCH,
  fetchHdus,
  fetchHeader,
  fetchImageStats,
  stfToStretch,
  type ImageStats,
  type StretchParams,
} from "@/api/fits";
import { FileBrowser } from "@/components/fits/FileBrowser";
import { FitsHeaderTable } from "@/components/fits/FitsHeaderTable";
import { FitsImage, type FitsImageHandle } from "@/components/fits/FitsImage";
import { HduSelector } from "@/components/fits/HduSelector";
import { StretchControls } from "@/components/fits/StretchControls";
import { useDebounce } from "@/lib/useDebounce";

const DEFAULT_PER_CHANNEL: [StretchParams, StretchParams, StretchParams] = [
  { ...DEFAULT_STRETCH },
  { ...DEFAULT_STRETCH },
  { ...DEFAULT_STRETCH },
];

/** Apply auto-computed STF defaults from image stats to the stretch state. */
function applyAutoStf(
  stats: ImageStats,
  setLinked: (p: StretchParams) => void,
  setPerChannel: (ch: [StretchParams, StretchParams, StretchParams]) => void,
) {
  if (stats.color && stats.linked_stf) {
    // Linked: use dimmest-channel STF for all
    setLinked(stfToStretch(stats.linked_stf));
  } else if (stats.channels.length >= 1) {
    // Mono: use the single channel's STF
    setLinked(stfToStretch(stats.channels[0].stf));
  }

  // Per-channel: each channel gets its own STF
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

  // Debounce stretch params — sliders update instantly, backend call fires 300ms after last change
  const debouncedLinked = useDebounce(linked, 300);
  const debouncedPerChannel = useDebounce(perChannel, 300);
  const debouncedIsLinked = useDebounce(isLinked, 300);

  const hdusQuery = useQuery({
    queryKey: ["hdus", activePath],
    queryFn: () => fetchHdus(activePath),
    enabled: activePath !== "",
  });

  const statsQuery = useQuery({
    queryKey: ["stats", activePath, selectedHdu],
    queryFn: () => fetchImageStats(activePath, selectedHdu),
    enabled: activePath !== "",
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
  }

  function handleOpen() {
    openFile(inputPath.trim());
  }

  function handleBrowseSelect(path: string) {
    openFile(path);
  }

  const handleReset = useCallback(() => {
    if (statsQuery.data) {
      applyAutoStf(statsQuery.data, setLinked, setPerChannel);
      setIsLinked(true);
    }
  }, [statsQuery.data]);

  const handleLinkedToggle = useCallback((val: boolean) => {
    setIsLinked(val);
    // When switching to unlinked, copy current linked params into all channels
    if (!val) {
      setPerChannel([{ ...linked }, { ...linked }, { ...linked }]);
    }
  }, [linked]);

  const hdus = hdusQuery.data ?? [];
  const selectedHduInfo = hdus.find((h) => h.index === selectedHdu);
  const hasFile = activePath !== "";
  const isColor = statsQuery.data?.color ?? false;

  // Extract display metadata from header
  const headerCards = headerQuery.data ?? [];
  const headerVal = (key: string) => {
    const card = headerCards.find((c) => c.key === key);
    return card?.value && card.value !== "" && card.value !== "None" ? card.value : null;
  };
  const fileName = activePath ? activePath.split("/").pop() ?? null : null;
  const dateObsRaw = headerVal("DATE-OBS");
  const dateObs = (() => {
    if (!dateObsRaw) return null;
    const d = new Date(dateObsRaw.endsWith("Z") ? dateObsRaw : dateObsRaw + "Z");
    if (isNaN(d.getTime())) return dateObsRaw;
    const short = new Intl.DateTimeFormat(undefined, {
      year: "numeric", month: "short", day: "numeric",
      hour: "2-digit", minute: "2-digit", second: "2-digit",
      timeZoneName: "short",
    }).format(d);
    return short;
  })();
  const exposure = headerVal("EXPTIME");
  const filter = headerVal("FILTER");

  // Build per-channel arg only when in unlinked color mode
  const activePerChannel = (isColor && !debouncedIsLinked) ? debouncedPerChannel : undefined;

  return (
    <Box sx={{ display: "flex", height: "100%", overflow: "hidden" }}>
      {/* Main area */}
      <Box sx={{ display: "flex", flexDirection: "column", flexGrow: 1, minWidth: 0, height: "100%" }}>
        {/* Toolbar */}
        <Box sx={{ display: "flex", alignItems: "center", gap: 1.5, p: 1.5, borderBottom: 1, borderColor: "divider", flexShrink: 0 }}>
          <TextField
            size="small"
            placeholder="Absolute path to .fits file…"
            value={inputPath}
            onChange={(e) => setInputPath(e.target.value)}
            onKeyDown={(e) => e.key === "Enter" && handleOpen()}
            inputProps={{ style: { fontFamily: "monospace", fontSize: "0.85rem" } }}
            sx={{ flexGrow: 1 }}
          />
          <Button variant="outlined" onClick={() => setBrowserOpen(true)}>
            Browse
          </Button>
          <Button variant="contained" onClick={handleOpen} disabled={!inputPath.trim()}>
            Open
          </Button>

          {hasFile && hdus.length > 0 && hdus.filter((h) => h.has_image).length > 1 && (
            <>
              <Divider orientation="vertical" flexItem />
              <HduSelector
                hdus={hdus}
                selected={selectedHdu}
                onChange={(i) => { setSelectedHdu(i); setTab(0); }}
              />
            </>
          )}
        </Box>

        {/* Error */}
        {hdusQuery.isError && (
          <Alert severity="error" sx={{ mx: 2, mt: 1 }}>
            {String(hdusQuery.error)}
          </Alert>
        )}

        {/* Tabs + content */}
        {hasFile && !hdusQuery.isError && (
          <>
            <Tabs
              value={tab}
              onChange={(_, v) => setTab(v)}
              sx={{ px: 2, flexShrink: 0, borderBottom: 1, borderColor: "divider" }}
            >
              <Tab label="Image" disabled={!selectedHduInfo?.has_image} />
              <Tab label="Header" />
            </Tabs>

            <Box sx={{ flexGrow: 1, overflow: "hidden", display: "flex", flexDirection: "column" }}>
              {tab === 0 && (
                selectedHduInfo?.has_image
                  ? <>
                      <Box sx={{ flexGrow: 1, overflow: "hidden" }}>
                        <FitsImage
                          ref={imageRef}
                          path={activePath}
                          hdu={selectedHdu}
                          linked={debouncedLinked}
                          perChannel={activePerChannel}
                          onZoomChange={setCurrentZoom}
                        />
                      </Box>
                      {/* Image info bar */}
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
                  : <Box sx={{ display: "flex", alignItems: "center", justifyContent: "center", height: "100%" }}>
                      <Typography color="text.secondary">Selected HDU has no image data</Typography>
                    </Box>
              )}
              {tab === 1 && (
                headerQuery.isLoading
                  ? <Typography sx={{ p: 2 }} color="text.secondary">Loading header…</Typography>
                  : headerQuery.data
                    ? <FitsHeaderTable cards={headerQuery.data} />
                    : null
              )}
            </Box>
          </>
        )}

        {/* Empty state */}
        {!hasFile && (
          <Box sx={{ display: "flex", alignItems: "center", justifyContent: "center", flexGrow: 1 }}>
            <Typography color="text.secondary">Enter a path or click Browse to open a FITS file</Typography>
          </Box>
        )}
      </Box>

      {/* Stretch panel — right sidebar, only when an image is open */}
      {hasFile && selectedHduInfo?.has_image && tab === 0 && (
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

          <Divider sx={{ mx: 1.5 }} />

          {/* Stretch section */}
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
        </Box>
      )}

      {/* File browser dialog */}
      <FileBrowser
        open={browserOpen}
        onClose={() => setBrowserOpen(false)}
        onSelect={handleBrowseSelect}
      />
    </Box>
  );
}
