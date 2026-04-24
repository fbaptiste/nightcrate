/**
 * PHD2 Guide-Log Analyzer — v0.22.0 Pass A.
 *
 * Standalone-first (spec §4.1): user pastes a path, hits Open, sees the
 * guiding graph + top-line stats. No persistence, no catalog linkage, no
 * interpretation — just a solid viewer anchored on a correct parser.
 */
import { useEffect, useMemo, useRef, useState } from "react";
import { useMutation } from "@tanstack/react-query";
import Alert from "@mui/material/Alert";
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
import FormControlLabel from "@mui/material/FormControlLabel";
import IconButton from "@mui/material/IconButton";
import Switch from "@mui/material/Switch";
import Tooltip from "@mui/material/Tooltip";
import { parseGuideLog, type ParseResponse } from "@/api/phd2";
import { setActivity } from "@/api/client";
import { computeGuidingMetrics, computeSettleIntervals } from "@/lib/phd2GuidingMetrics";
import ScatterPlot from "@/components/phd2/ScatterPlot";
import EventList from "@/components/phd2/EventList";
import type { TimeSeriesChartHandle } from "@/components/phd2/TimeSeriesChart";
import { FileBrowser } from "@/components/fits/FileBrowser";
import SectionNavigator from "@/components/phd2/SectionNavigator";
import StatsPanel from "@/components/phd2/StatsPanel";
import TimeSeriesChart from "@/components/phd2/TimeSeriesChart";
import CalibrationPlot from "@/components/phd2/CalibrationPlot";
import SectionDataTab from "@/components/phd2/SectionDataTab";
import WarningsDrawer from "@/components/phd2/WarningsDrawer";

// Stable reference — consumers of FileBrowser should pass a stable array
// for ``accept`` so the browser's useEffect deps don't churn on each render.
const GUIDE_LOG_ACCEPT = [".txt"];

export default function Phd2AnalyzerPage() {
  const [pathInput, setPathInput] = useState("");
  const [activePath, setActivePath] = useState<string>("");
  const [selectedIndex, setSelectedIndex] = useState(0);
  const [parsed, setParsed] = useState<ParseResponse | null>(null);
  const [browserOpen, setBrowserOpen] = useState(false);
  // Section-view tab: 0 = Graph, 1 = Data. Tab state is page-level so
  // switching sections keeps the user on the same tab.
  const [tab, setTab] = useState(0);
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
  // PHD2 / PHDLogViewer default: settle frames are excluded from
  // guide-quality metrics. ``true`` flips both summary panels back to
  // the pre-v0.22.0 "include everything" behaviour AND hides the
  // settle shading on the chart.
  const [includeSettle, setIncludeSettle] = useState(false);
  // Imperative handle for the time-series chart — EventList rows
  // forward clicks through this so the chart pans / zooms to the
  // event time without drilling d3 through props.
  const chartRef = useRef<TimeSeriesChartHandle | null>(null);

  useEffect(() => {
    setActivity("PHD2 Analyzer");
  }, []);

  const parseMutation = useMutation({
    mutationFn: (path: string) => {
      setActivity(`Parse log ${path.split("/").pop() ?? "file"}`);
      return parseGuideLog(path);
    },
    onSuccess: (data) => {
      setParsed(data);
      // Select the first guiding section if present; else the first section.
      const firstGuiding = data.sections.find((s) => s.section.kind === "guiding");
      setSelectedIndex(firstGuiding?.section.index ?? data.sections[0]?.section.index ?? 0);
    },
  });

  const selected = useMemo(() => {
    if (!parsed) return null;
    return parsed.sections.find((s) => s.section.index === selectedIndex) ?? parsed.sections[0];
  }, [parsed, selectedIndex]);

  // Reset viewport state when the user switches sections — the new
  // section's chart mounts un-zoomed, but without this the stale
  // ``viewport`` from the previous section would briefly filter the
  // new section's samples before the chart fires its initial event.
  useEffect(() => {
    setViewport(null);
  }, [selectedIndex]);

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
      { includeSettle },
    );
  }, [selected, includeSettle]);

  // Viewport-filtered samples + metrics for the Viewport Summary
  // panel. Guiding sections only; calibration gets no chart so there's
  // no viewport to speak of.
  const viewportSamples = useMemo(() => {
    if (!selected || selected.section.kind !== "guiding") return null;
    if (!viewport) return selected.section.samples;
    const [t0, t1] = viewport;
    return selected.section.samples.filter(
      (s) => s.time_seconds >= t0 && s.time_seconds <= t1,
    );
  }, [selected, viewport]);

  const viewportMetrics = useMemo(() => {
    if (!viewportSamples || !selected) return null;
    return computeGuidingMetrics(
      viewportSamples,
      selected.section.events,
      selected.metrics.arcsec_scale,
      { includeSettle },
    );
  }, [viewportSamples, selected, includeSettle]);

  const openPath = (path: string) => {
    const trimmed = path.trim();
    if (!trimmed) return;
    setActivePath(trimmed);
    setPathInput(trimmed);
    parseMutation.mutate(trimmed);
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
          <TextField
            size="small"
            fullWidth
            placeholder="Path to PHD2_GuideLog_*.txt (or archive.zip::log.txt)"
            value={pathInput}
            onChange={(e) => setPathInput(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter") handleOpen();
            }}
            inputProps={{ style: { fontFamily: "monospace", fontSize: "0.8rem" } }}
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
            Paste the absolute path to a PHD2 guide log (filename pattern{" "}
            <code>PHD2_GuideLog_*.txt</code>) and press Open. The analyzer parses
            the file in-process — nothing is uploaded or persisted.
          </Typography>
          <Typography variant="body2" color="text.secondary" sx={{ mt: 2, maxWidth: 640 }}>
            v0.22.0 Pass A delivers the parser, the time-series chart, the
            calibration plot, and per-section summary metrics. Advanced analysis
            (FFT, unguided reconstruction, automated diagnostics) lands in later
            versions.
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
              <Box sx={{ overflow: "auto", p: 1, pt: 0 }}>
                <SectionNavigator
                  sections={parsed.sections}
                  selectedIndex={selectedIndex}
                  onSelect={setSelectedIndex}
                />
              </Box>
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
                if (v === 1) setDataVisited(true);
              }}
              sx={{ px: 2, borderBottom: 1, borderColor: "divider", minHeight: 40 }}
            >
              <Tab label="Graph" sx={{ minHeight: 40 }} />
              <Tab label="Data" sx={{ minHeight: 40 }} />
            </Tabs>
            {/* Graph panel — display-toggle so chart state (zoom) is preserved */}
            <Box
              sx={{
                flex: 1,
                overflow: "auto",
                p: 2,
                display: tab === 0 ? "block" : "none",
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
                  />
                  <FormControlLabel
                    control={
                      <Switch
                        size="small"
                        checked={includeSettle}
                        onChange={(e) => setIncludeSettle(e.target.checked)}
                      />
                    }
                    label={
                      <Typography variant="body2">
                        Include settle frames in stats
                        <Typography
                          component="span"
                          variant="caption"
                          color="text.secondary"
                          sx={{ ml: 1 }}
                        >
                          Off by default
                        </Typography>
                      </Typography>
                    }
                  />
                  {viewportMetrics && viewportSamples && (
                    <StatsPanel
                      metrics={viewportMetrics}
                      kind="guiding"
                      title="Viewport summary"
                      subtitle={
                        viewport === null
                          ? "All frames visible"
                          : `${viewportSamples.length.toLocaleString()} / ${selected.section.samples.length.toLocaleString()} frames visible`
                      }
                      collapsible
                    />
                  )}
                  {sectionMetrics && (
                    <StatsPanel
                      metrics={sectionMetrics}
                      kind="guiding"
                      collapsible
                    />
                  )}
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
                  <StatsPanel
                    metrics={selected.metrics}
                    kind="calibration"
                    collapsible
                  />
                </Stack>
              )}
            </Box>
            {/* Data panel — keyed by section index so the DataGrid resets
                scroll + selection when the user picks a different section. */}
            <Box
              sx={{
                flex: 1,
                p: 2,
                display: tab === 1 ? "flex" : "none",
                flexDirection: "column",
                minHeight: 0,
                minWidth: 0,
              }}
            >
              {dataVisited && (
                <SectionDataTab
                  key={selected.section.index}
                  section={selected.section}
                />
              )}
            </Box>
          </Box>
        </Box>
      )}
    </Box>
  );
}
