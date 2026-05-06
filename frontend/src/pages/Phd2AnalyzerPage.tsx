/**
 * PHD2 Guide-Log Analyzer page — standalone log viewer with Guiding,
 * Dispersion, and Data tabs.
 */
import { useEffect, useMemo, useRef, useState } from "react";
import { usePhd2Store } from "@/stores/phd2Store";
import { useMutation } from "@tanstack/react-query";
import Alert from "@mui/material/Alert";
import Autocomplete from "@mui/material/Autocomplete";
import Box from "@mui/material/Box";
import Button from "@mui/material/Button";
import Chip from "@mui/material/Chip";
import CircularProgress from "@mui/material/CircularProgress";
import Divider from "@mui/material/Divider";
import Paper from "@mui/material/Paper";
import Stack from "@mui/material/Stack";
import Tab from "@mui/material/Tab";
import Tabs from "@mui/material/Tabs";
import TextField from "@mui/material/TextField";
import Typography from "@mui/material/Typography";
import FolderOpenIcon from "@mui/icons-material/FolderOpen";
import ChevronLeftIcon from "@mui/icons-material/ChevronLeft";
import ChevronRightIcon from "@mui/icons-material/ChevronRight";
import IconButton from "@mui/material/IconButton";
import Popover from "@mui/material/Popover";
import Tooltip from "@mui/material/Tooltip";
import InfoOutlinedIcon from "@mui/icons-material/InfoOutlined";
import { parseGuideLog } from "@/api/phd2";
import { setActivity } from "@/api/client";
import { computeGuidingMetrics, computeSettleIntervals } from "@/lib/phd2GuidingMetrics";
import ScatterPlot from "@/components/phd2/ScatterPlot";
import EventList from "@/components/phd2/EventList";
import type { TimeSeriesChartHandle } from "@/components/phd2/TimeSeriesChart";
import {
  addRecentFile,
  formatRelativeTime,
  getRecentFiles,
  removeRecentFile,
  type RecentFile,
} from "@/lib/phd2RecentFiles";
import CloseIcon from "@mui/icons-material/Close";

import { FileBrowser } from "@/components/fits/FileBrowser";
import SectionNavigator from "@/components/phd2/SectionNavigator";
import SectionInfoPanel from "@/components/phd2/SectionInfoPanel";
import StatsPanel from "@/components/phd2/StatsPanel";
import TimeSeriesChart from "@/components/phd2/TimeSeriesChart";
import CalibrationPlot from "@/components/phd2/CalibrationPlot";
import SectionDataTab from "@/components/phd2/SectionDataTab";
import WarningsDrawer from "@/components/phd2/WarningsDrawer";

// Stable reference — consumers of FileBrowser should pass a stable array
// for ``accept`` so the browser's useEffect deps don't churn on each render.
const GUIDE_LOG_ACCEPT = [".txt"];

const TAB_HELP: Record<number, string> = {
  1: "Guide error panel: RA (blue) and Dec (orange) position error relative to the lock point. Vertical bars show guide pulse durations. SNR and Star Mass panels below track guide-star health. Drag dividers between panels to resize.",
  2: "2-D scatter of guide-star positions. A round, tight cloud means balanced guiding; an elongated cloud means one axis dominates. The 1σ and 2σ ellipses show dispersion shape. The centroid dot shows the average offset from the lock point.",
  3: "Per-frame data from the log. Click column headers to sort. Use the filter dropdowns above the grid to narrow by error type or other fields.",
};

export default function Phd2AnalyzerPage() {
  const {
    activePath, setActivePath,
    pathInput, setPathInput,
    selectedIndex, setSelectedIndex,
    parsed, setParsed,
    tab, setTab,
  } = usePhd2Store();
  const [browserOpen, setBrowserOpen] = useState(false);
  // Lazy-mount the Data tab. The heavy DataTable useMemo pass (14
  // columns × 7 500 rows) was competing for the first render with the
  // chart — pulses appeared to "come in later" because the chart's
  // render was blocked. Once Data has been visited once, it stays
  // mounted so the user keeps their scroll position.
  const [dataVisited, setDataVisited] = useState(false);
  // Collapse the section nav to a thin rail so the graph can use the
  // freed horizontal space. Rail stays visible with a single expand
  // arrow so the control never leaves the DOM.
  const [navCollapsed, setNavCollapsed] = useState(false);
  // Visible X-domain of the chart (null == full section). Driven by
  // TimeSeriesChart via ``onViewportChange``; consumed by the Viewport
  // Summary panel so metrics recompute over just the in-view samples.
  const [viewport, setViewport] = useState<[number, number] | null>(null);
  // PHD2 default: settle frames are excluded from guide-quality
  // metrics. ``true`` flips both summary panels back to the
  // pre-v0.22.0 "include everything" behaviour AND hides the settle
  // shading on the chart.
  const [includeSettle, setIncludeSettle] = useState(false);
  const [helpAnchor, setHelpAnchor] = useState<Element | null>(null);
  // Imperative handle for the time-series chart — EventList rows
  // forward clicks through this so the chart pans / zooms to the
  // event time without drilling d3 through props.
  const chartRef = useRef<TimeSeriesChartHandle | null>(null);
  // User-drawn selection + exclusion bands — both multi-additive.
  // Shift-drag appends a selection (teal band), Shift+Alt-drag
  // appends an exclusion (hatched-grey band). Net sample set =
  // union(selections) − union(exclusions). Removed via the per-zone
  // × button on the chart or the "Clear all" toolbar action. All
  // reset on section change alongside viewport.
  const [selections, setSelections] = useState<Array<[number, number]>>([]);
  const [exclusions, setExclusions] = useState<Array<[number, number]>>([]);
  // Recent files history — localStorage-backed, displayed on the
  // empty-state landing when no log is currently loaded.
  const [recentFiles, setRecentFiles] = useState<RecentFile[]>(() =>
    getRecentFiles(),
  );

  useEffect(() => {
    setActivity("PHD2 Analyzer");
  }, []);

  const parseMutation = useMutation({
    mutationFn: ({ path }: { path: string }) => {
      setActivity(`Parse log ${path.split("/").pop() ?? "file"}`);
      return parseGuideLog(path);
    },
    onSuccess: (data, { path }) => {
      setParsed(data);
      // Select the first guiding section if present; else the first section.
      const firstGuiding = data.sections.find((s) => s.section.kind === "guiding");
      setSelectedIndex(firstGuiding?.section.index ?? data.sections[0]?.section.index ?? 0);
      // Only record successfully-parsed logs in the recent-files
      // history so a typo path or unreadable file doesn't pollute
      // the list.
      setRecentFiles(addRecentFile(path));
    },
  });

  const selected = useMemo(() => {
    if (!parsed) return null;
    return parsed.sections.find((s) => s.section.index === selectedIndex) ?? parsed.sections[0];
  }, [parsed, selectedIndex]);

  // Reset viewport + user-drawn selection / exclusion state when the
  // user switches sections. Without this, a stale range from the
  // previous section would briefly filter the new section's samples
  // before the chart fires its initial event.
  useEffect(() => {
    setViewport(null);
    setSelections([]);
    setExclusions([]);
    if (selected && selected.section.kind !== "guiding" && tab === 2) {
      setTab(1);
    }
  }, [selectedIndex]); // eslint-disable-line react-hooks/exhaustive-deps

  // Settle intervals for the selected guiding section — derived once
  // per section and reused by both the chart shading and the
  // client-side metrics helpers.
  const settleIntervals = useMemo(() => {
    if (!selected || selected.section.kind !== "guiding") return [];
    const samples = selected.section.samples;
    const fallbackEnd =
      samples.length > 0 ? samples[samples.length - 1].time_seconds : 0;
    return computeSettleIntervals(selected.section.events, fallbackEnd);
  }, [selected]);

  // Section Summary — client-side recompute so the include-settle
  // toggle can flip without a backend round-trip. ``selected.metrics``
  // stays authoritative for the Section Navigator sidebar (which
  // doesn't honour the toggle — the default "excluded" view is right
  // for at-a-glance browsing).
  const sectionMetrics = useMemo(() => {
    if (!selected || selected.section.kind !== "guiding") return null;
    return computeGuidingMetrics(
      selected.section.samples,
      selected.section.events,
      selected.metrics.arcsec_scale,
      {
        includeSettle,
        declinationDeg: selected.section.header.declination_deg,
      },
    );
  }, [selected, includeSettle]);

  // Sample subset driving the Selection / Viewport Summary panel.
  // Base set = union of all selections (Shift-drag) when any exist;
  // else the zoom-driven viewport; else the full section. Then
  // subtract union of exclusions (Shift+Alt-drag). Guiding sections
  // only — calibration has no chart so there's no viewport to speak
  // of.
  const viewportSamples = useMemo(() => {
    if (!selected || selected.section.kind !== "guiding") return null;
    const base = (() => {
      if (selections.length > 0) {
        return selected.section.samples.filter((s) =>
          selections.some(
            ([t0, t1]) => s.time_seconds >= t0 && s.time_seconds <= t1,
          ),
        );
      }
      if (viewport) {
        const [t0, t1] = viewport;
        return selected.section.samples.filter(
          (s) => s.time_seconds >= t0 && s.time_seconds <= t1,
        );
      }
      return selected.section.samples;
    })();
    if (exclusions.length === 0) return base;
    return base.filter(
      (s) =>
        !exclusions.some(
          ([e0, e1]) => s.time_seconds >= e0 && s.time_seconds <= e1,
        ),
    );
  }, [selected, viewport, selections, exclusions]);

  const viewportMetrics = useMemo(() => {
    if (!viewportSamples || !selected) return null;
    return computeGuidingMetrics(
      viewportSamples,
      selected.section.events,
      selected.metrics.arcsec_scale,
      {
        includeSettle,
        declinationDeg: selected.section.header.declination_deg,
      },
    );
  }, [viewportSamples, selected, includeSettle]);

  const handleExportViewport = async () => {
    if (!activePath || !selected || !viewport) return;
    const params = new URLSearchParams({
      path: activePath,
      section_index: String(selected.section.index),
      time_start: String(viewport[0]),
      time_end: String(viewport[1]),
    });
    const res = await fetch(`/api/phd2/export?${params.toString()}`, { method: "POST" });
    if (!res.ok) return;
    const blob = await res.blob();
    const url = URL.createObjectURL(blob);
    const filename = res.headers.get("Content-Disposition")?.match(/filename="(.+)"/)?.[1] ?? "PHD2_Export.txt";
    const a = document.createElement("a");
    a.href = url;
    a.download = filename;
    a.style.display = "none";
    document.body.appendChild(a);
    a.click();
    setTimeout(() => {
      document.body.removeChild(a);
      URL.revokeObjectURL(url);
    }, 100);
  };

  const openPath = (path: string) => {
    const trimmed = path.trim();
    if (!trimmed) return;
    setActivePath(trimmed);
    setPathInput(trimmed);
    parseMutation.mutate({ path: trimmed });
  };

  const handleOpen = () => openPath(pathInput);

  return (
    <Box sx={{ height: "100%", display: "flex", flexDirection: "column", overflow: "hidden" }}>
      {/* Toolbar */}
      <Paper elevation={0} sx={{ p: 2, borderBottom: 1, borderColor: "divider", flexShrink: 0 }}>
        <Stack direction="row" spacing={1.5} alignItems="center">
          <Typography
            variant="h6"
            sx={{ mr: 2, whiteSpace: "nowrap", flexShrink: 0 }}
          >
            PHD2 Analyzer
          </Typography>
          <Button
            variant="outlined"
            size="small"
            startIcon={<FolderOpenIcon sx={{ fontSize: 16 }} />}
            onClick={() => setBrowserOpen(true)}
            sx={{ height: 32, flexShrink: 0, whiteSpace: "nowrap" }}
          >
            Browse
          </Button>
          <Autocomplete
            freeSolo
            forcePopupIcon
            clearOnBlur={false}
            blurOnSelect
            options={recentFiles}
            getOptionLabel={(opt) =>
              typeof opt === "string" ? opt : opt.path
            }
            filterOptions={(options) => options}
            inputValue={pathInput}
            onInputChange={(_, value, reason) => {
              if (reason !== "reset") setPathInput(value);
            }}
            onChange={(_, value) => {
              if (!value) return;
              const path = typeof value === "string" ? value : value.path;
              if (path) openPath(path);
            }}
            sx={{
              // Path field aims for ~50% of toolbar width but yields
              // gracefully on narrow viewports so the Open button
              // never gets pushed off-screen. Doesn't grow past 720
              // px even on ultra-wide windows — past that the field
              // becomes unwieldy without adding any utility.
              flexBasis: "50%",
              flexGrow: 0,
              flexShrink: 1,
              minWidth: 240,
              maxWidth: 720,
              "& .MuiInputBase-root": { height: 32, py: 0 },
            }}
            slotProps={{ listbox: { style: { maxHeight: 360 } } }}
            renderInput={(params) => (
              <TextField
                {...params}
                size="small"
                placeholder="Path to PHD2_GuideLog_*.txt (or archive.zip::log.txt)"
                onKeyDown={(e) => {
                  if (e.key === "Enter") handleOpen();
                }}
                inputProps={{
                  ...params.inputProps,
                  style: { fontFamily: "monospace", fontSize: "0.8rem" },
                }}
              />
            )}
            renderOption={(props, option) => {
              const item =
                typeof option === "string"
                  ? { path: option, openedAt: "" }
                  : option;
              const { key, ...rest } = props as { key?: string } & Record<
                string,
                unknown
              >;
              return (
                <li {...rest} key={key ?? item.path}>
                  <Stack
                    direction="row"
                    spacing={1}
                    alignItems="baseline"
                    sx={{ width: "100%", minWidth: 0 }}
                  >
                    <Box sx={{ flex: 1, minWidth: 0 }}>
                      <Typography
                        sx={{
                          fontFamily: "monospace",
                          fontSize: "0.75rem",
                          fontWeight: 500,
                          overflow: "hidden",
                          textOverflow: "ellipsis",
                          whiteSpace: "nowrap",
                        }}
                      >
                        {basename(item.path)}
                      </Typography>
                      <Typography
                        variant="caption"
                        color="text.secondary"
                        sx={{
                          fontFamily: "monospace",
                          fontSize: "0.65rem",
                          display: "block",
                          overflow: "hidden",
                          textOverflow: "ellipsis",
                          whiteSpace: "nowrap",
                        }}
                      >
                        {item.path}
                      </Typography>
                    </Box>
                    {item.openedAt && (
                      <Typography
                        variant="caption"
                        color="text.secondary"
                        sx={{ flexShrink: 0, minWidth: 80, textAlign: "right" }}
                      >
                        {formatRelativeTime(item.openedAt)}
                      </Typography>
                    )}
                    <IconButton
                      size="small"
                      aria-label={`Remove ${item.path} from recent logs`}
                      onClick={(e) => {
                        e.stopPropagation();
                        setRecentFiles(removeRecentFile(item.path));
                      }}
                      sx={{ ml: 0.5 }}
                    >
                      <CloseIcon sx={{ fontSize: 14 }} />
                    </IconButton>
                  </Stack>
                </li>
              );
            }}
          />
          <Button
            variant="contained"
            size="small"
            onClick={handleOpen}
            disabled={!pathInput.trim() || parseMutation.isPending}
            sx={{ height: 32, flexShrink: 0, whiteSpace: "nowrap" }}
          >
            {parseMutation.isPending ? "Parsing…" : "Open"}
          </Button>
          {parsed && (
            <>
              <Divider orientation="vertical" flexItem />
              {parsed.log.phd2_version && (
                <Chip
                  label={`PHD2 ${parsed.log.phd2_version}`}
                  size="small"
                  variant="outlined"
                />
              )}
              <Chip label={`Log v${parsed.log.log_version}`} size="small" variant="outlined" />
              <Chip label={`${parsed.sections.length} sections`} size="small" variant="outlined" />
              <WarningsDrawer warnings={parsed.log.warnings} />
              <Box sx={{ flex: 1 }} />
            </>
          )}
        </Stack>
        {parseMutation.isError && (
          <Alert severity="error" sx={{ mt: 1 }}>
            {(parseMutation.error as Error).message}
          </Alert>
        )}
      </Paper>

      {/* Main body */}
      {parseMutation.isPending && !parsed && (
        <Box sx={{ p: 4, display: "flex", alignItems: "center", gap: 2 }}>
          <CircularProgress size={20} />
          <Typography variant="body2">Parsing log…</Typography>
        </Box>
      )}

      {!parseMutation.isPending && !parsed && !parseMutation.isError && (
        <Box sx={{ p: 4 }}>
          <Typography variant="body2" color="text.secondary" sx={{ maxWidth: 640 }}>
            Open a PHD2 guide log to start —{" "}
            <Typography component="span" variant="body2" sx={{ fontWeight: 500 }}>
              Browse
            </Typography>{" "}
            to pick a file from disk, paste an absolute path into the field
            (filename pattern <code>PHD2_GuideLog_*.txt</code>), or open the
            path field's dropdown to pick a previously-analysed log. The
            analyzer parses the file in-process; nothing is uploaded or
            persisted.
          </Typography>
        </Box>
      )}

      <FileBrowser
        open={browserOpen}
        onClose={() => setBrowserOpen(false)}
        onSelect={(path) => openPath(path)}
        activePath={activePath}
        accept={GUIDE_LOG_ACCEPT}
        title="Open PHD2 Guide Log"
        emptyMessage="No guide logs or folders here"
      />

      {parsed && selected && (
        <Box sx={{ display: "flex", flex: 1, minHeight: 0, overflow: "hidden" }}>
          {/* Left — section list, collapsible to a thin rail */}
          <Box
            sx={{
              width: navCollapsed ? 32 : 280,
              flexShrink: 0,
              borderRight: 1,
              borderColor: "divider",
              overflow: "hidden",
              display: "flex",
              flexDirection: "column",
              transition: "width 120ms ease",
            }}
          >
            <Stack
              direction="row"
              alignItems="center"
              justifyContent="flex-end"
              sx={{ pr: 0.25, pt: 0.5, flexShrink: 0 }}
            >
              <Tooltip title={navCollapsed ? "Expand sections" : "Collapse sections"}>
                <IconButton
                  size="small"
                  onClick={() => setNavCollapsed((v) => !v)}
                >
                  {navCollapsed ? (
                    <ChevronRightIcon fontSize="small" />
                  ) : (
                    <ChevronLeftIcon fontSize="small" />
                  )}
                </IconButton>
              </Tooltip>
            </Stack>
            {!navCollapsed && (
              <>
                <Box sx={{ flexShrink: 0, p: 1, pt: 0 }}>
                  <SectionNavigator
                    sections={parsed.sections}
                    selectedIndex={selectedIndex}
                    onSelect={setSelectedIndex}
                  />
                </Box>
                {selected && selected.section.kind === "guiding" && (
                  <>
                    <Divider />
                    <Box sx={{ overflow: "auto", flex: 1, minHeight: 0, p: 1 }}>
                      <StatsPanel
                        metrics={sectionMetrics ?? selected.metrics}
                        kind="guiding"
                        collapsible
                        defaultExpanded={false}
                      />
                      {viewportMetrics && viewportSamples && (
                        <Box sx={{ mt: 1.5 }}>
                          <StatsPanel
                            metrics={viewportMetrics}
                            kind="guiding"
                            title={
                              selections.length > 0
                                ? "Selection stats"
                                : "Viewport stats"
                            }
                            subtitle={formatSubtitle(
                              viewportSamples.length,
                              selected.section.samples.length,
                            )}
                            collapsible
                            defaultExpanded={false}
                            footer={viewport && (
                              <Box sx={{ display: "flex", justifyContent: "center", mt: 1 }}>
                                <Button
                                  size="small"
                                  variant="outlined"
                                  sx={{ textTransform: "none" }}
                                  onClick={() => handleExportViewport()}
                                >
                                  Export viewport log
                                </Button>
                              </Box>
                            )}
                          />
                        </Box>
                      )}
                    </Box>
                  </>
                )}
              </>
            )}
          </Box>
          {/* Right — section view with tabs. ``minWidth: 0`` is needed
              everywhere down the flex chain so the DataTable's wide
              grid doesn't push the tab's filter toolbar off-screen. */}
          <Box sx={{ flex: 1, display: "flex", flexDirection: "column", minHeight: 0, minWidth: 0 }}>
            <Tabs
              value={tab}
              onChange={(_, v) => {
                setTab(v);
                setHelpAnchor(null);
                if (v === 3) setDataVisited(true);
              }}
              sx={{ px: 2, borderBottom: 1, borderColor: "divider", minHeight: 40 }}
            >
              <Tooltip title="Per-section equipment, sky, and algorithm metadata." arrow>
                <Tab label="Section Info" sx={{ minHeight: 40 }} />
              </Tooltip>
              {[
                { label: "Guiding", idx: 1 },
                { label: "Dispersion", idx: 2, guidingOnly: true },
                { label: "Data", idx: 3 },
              ].map(({ label, idx, guidingOnly }) => (
                <Tab
                  key={idx}
                  label={
                    <Stack direction="row" alignItems="center" spacing={0.5}>
                      <span>{label}</span>
                      <InfoOutlinedIcon
                        sx={{
                          fontSize: 14,
                          color: "action.active",
                          cursor: "pointer",
                          "&:hover": { color: "primary.main" },
                        }}
                        onClick={(e) => {
                          e.stopPropagation();
                          setHelpAnchor(helpAnchor ? null : e.currentTarget);
                        }}
                      />
                    </Stack>
                  }
                  sx={{
                    minHeight: 40,
                    display: guidingOnly && selected.section.kind !== "guiding" ? "none" : undefined,
                  }}
                />
              ))}
            </Tabs>
            <Popover
              open={Boolean(helpAnchor)}
              anchorEl={helpAnchor}
              onClose={() => setHelpAnchor(null)}
              anchorOrigin={{ vertical: "bottom", horizontal: "left" }}
              transformOrigin={{ vertical: "top", horizontal: "left" }}
              slotProps={{ paper: { sx: { maxWidth: 360, p: 2 } } }}
            >
              <Typography variant="body2" color="text.secondary">
                {TAB_HELP[tab]}
              </Typography>
            </Popover>
            {/* Section Info panel — per-section equipment / sky /
                algorithm metadata from the log header. */}
            <Box
              sx={{
                flex: 1,
                overflow: "auto",
                p: 2,
                display: tab === 0 ? "block" : "none",
              }}
            >
              <SectionInfoPanel
                header={selected.section.header}
                collapsible={false}
                defaultExpanded
              />
            </Box>
            {/* Guiding panel — display-toggle so chart state (zoom) is preserved */}
            <Box
              sx={{
                flex: 1,
                overflow: "auto",
                p: 2,
                display: tab === 1 ? "block" : "none",
              }}
            >
              {selected.section.kind === "guiding" ? (
                <Stack spacing={2}>
                    <TimeSeriesChart
                      ref={chartRef}
                      samples={selected.section.samples}
                      events={selected.section.events}
                      startIso={selected.section.start_time}
                      arcsecScale={selected.metrics.arcsec_scale}
                      onViewportChange={setViewport}
                      settleIntervals={settleIntervals}
                      showSettleShading={!includeSettle}
                      selections={selections}
                      exclusions={exclusions}
                      onSelectionsChange={setSelections}
                      onExclusionsChange={setExclusions}
                      includeSettle={includeSettle}
                      onIncludeSettleChange={setIncludeSettle}
                    />
                    <EventList
                      events={selected.section.events}
                      startIso={selected.section.start_time}
                      onEventClick={(e) => {
                        if (e.time_seconds != null) {
                          chartRef.current?.scrollToTime(e.time_seconds);
                        }
                      }}
                    />
                </Stack>
              ) : (
                <Stack spacing={2}>
                  <CalibrationPlot phases={selected.section.calibration_phases} />
                </Stack>
              )}
            </Box>
            {/* Dispersion panel — extracted to its own tab so the
                guiding view stays focused on the time series. */}
            <Box
              sx={{
                flex: 1,
                overflow: "auto",
                p: 2,
                display: tab === 2 ? "block" : "none",
              }}
            >
              {selected.section.kind === "guiding" && (
                  <ScatterPlot
                    samples={
                      includeSettle
                        ? selected.section.samples
                        : selected.section.samples.filter(
                            (s) =>
                              !settleIntervals.some(
                                ([t0, t1]) =>
                                  s.time_seconds >= t0 && s.time_seconds <= t1,
                              ),
                          )
                    }
                    arcsecScale={selected.metrics.arcsec_scale}
                    subtitle={
                      includeSettle
                        ? "All frames included"
                        : `Settle frames excluded`
                    }
                  />
              )}
            </Box>
            {/* Data panel — keyed by section index so the DataGrid resets
                scroll + selection when the user picks a different section. */}
            <Box
              sx={{
                flex: 1,
                p: 2,
                display: tab === 3 ? "flex" : "none",
                flexDirection: "column",
                minHeight: 0,
                minWidth: 0,
              }}
            >
              {dataVisited && (
                <Box sx={{ flex: 1, minHeight: 0 }}>
                  <SectionDataTab
                    key={selected.section.index}
                    section={selected.section}
                  />
                </Box>
              )}
            </Box>
          </Box>
        </Box>
      )}
    </Box>
  );
}

/** Last path segment; handles both / and \ for cross-platform paths. */
function basename(path: string): string {
  const idx = Math.max(path.lastIndexOf("/"), path.lastIndexOf("\\"));
  return idx >= 0 ? path.slice(idx + 1) : path;
}


function formatSubtitle(
  visibleCount: number,
  totalCount: number,
): string {
  return `${visibleCount.toLocaleString()} / ${totalCount.toLocaleString()} frames`;
}
