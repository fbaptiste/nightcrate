/**
 * PHD2 Guide-Log Analyzer — v0.22.0 Pass A.
 *
 * Standalone-first (spec §4.1): user pastes a path, hits Open, sees the
 * guiding graph + top-line stats. No persistence, no catalog linkage, no
 * interpretation — just a solid viewer anchored on a correct parser.
 */
import { useEffect, useMemo, useState } from "react";
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
import { parseGuideLog, type ParseResponse } from "@/api/guideLogs";
import { setActivity } from "@/api/client";
import { FileBrowser } from "@/components/fits/FileBrowser";
import SectionNavigator from "@/components/guidelogs/SectionNavigator";
import StatsPanel from "@/components/guidelogs/StatsPanel";
import TimeSeriesChart from "@/components/guidelogs/TimeSeriesChart";
import CalibrationPlot from "@/components/guidelogs/CalibrationPlot";
import SectionDataTab from "@/components/guidelogs/SectionDataTab";
import WarningsDrawer from "@/components/guidelogs/WarningsDrawer";

// Stable reference — consumers of FileBrowser should pass a stable array
// for ``accept`` so the browser's useEffect deps don't churn on each render.
const GUIDE_LOG_ACCEPT = [".txt"];

export default function GuideLogsPage() {
  const [pathInput, setPathInput] = useState("");
  const [activePath, setActivePath] = useState<string>("");
  const [selectedIndex, setSelectedIndex] = useState(0);
  const [parsed, setParsed] = useState<ParseResponse | null>(null);
  const [browserOpen, setBrowserOpen] = useState(false);
  // Section-view tab: 0 = Graph, 1 = Data. Tab state is page-level so
  // switching sections keeps the user on the same tab.
  const [tab, setTab] = useState(0);

  useEffect(() => {
    setActivity("Guide Logs");
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
          <Typography variant="h6" sx={{ mr: 2 }}>
            Guide Logs
          </Typography>
          <Button
            variant="outlined"
            size="small"
            startIcon={<FolderOpenIcon sx={{ fontSize: 16 }} />}
            onClick={() => setBrowserOpen(true)}
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
          >
            {parseMutation.isPending ? "Parsing…" : "Open"}
          </Button>
          {parsed && (
            <>
              <Divider orientation="vertical" flexItem />
              <Chip
                label={`PHD2 ${parsed.log.phd2_version ?? "—"}`}
                size="small"
                variant="outlined"
              />
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
          {/* Left — section list */}
          <Box
            sx={{
              width: 280,
              flexShrink: 0,
              borderRight: 1,
              borderColor: "divider",
              overflow: "auto",
              p: 1,
            }}
          >
            <SectionNavigator
              sections={parsed.sections}
              selectedIndex={selectedIndex}
              onSelect={setSelectedIndex}
            />
          </Box>
          {/* Right — section view with tabs */}
          <Box sx={{ flex: 1, display: "flex", flexDirection: "column", minHeight: 0 }}>
            <Tabs
              value={tab}
              onChange={(_, v) => setTab(v)}
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
                    samples={selected.section.samples}
                    events={selected.section.events}
                  />
                  <StatsPanel metrics={selected.metrics} kind="guiding" />
                </Stack>
              ) : (
                <Stack spacing={2}>
                  <CalibrationPlot phases={selected.section.calibration_phases} />
                  <StatsPanel metrics={selected.metrics} kind="calibration" />
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
              }}
            >
              <SectionDataTab
                key={selected.section.index}
                section={selected.section}
              />
            </Box>
          </Box>
        </Box>
      )}
    </Box>
  );
}
