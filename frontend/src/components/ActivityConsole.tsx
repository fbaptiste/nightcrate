import { useCallback, useEffect, useRef, useState } from "react";
import { createPortal } from "react-dom";
import createCache from "@emotion/cache";
import { CacheProvider } from "@emotion/react";
import { ThemeProvider as MuiThemeProvider } from "@mui/material";
import CssBaseline from "@mui/material/CssBaseline";
import Accordion from "@mui/material/Accordion";
import AccordionDetails from "@mui/material/AccordionDetails";
import AccordionSummary from "@mui/material/AccordionSummary";
import Box from "@mui/material/Box";
import Button from "@mui/material/Button";
import Chip from "@mui/material/Chip";
import Dialog from "@mui/material/Dialog";
import DialogActions from "@mui/material/DialogActions";
import DialogContent from "@mui/material/DialogContent";
import DialogTitle from "@mui/material/DialogTitle";
import IconButton from "@mui/material/IconButton";
import Paper, { type PaperProps } from "@mui/material/Paper";
import Snackbar from "@mui/material/Snackbar";
import Table from "@mui/material/Table";
import TableBody from "@mui/material/TableBody";
import TableCell from "@mui/material/TableCell";
import TableHead from "@mui/material/TableHead";
import TableRow from "@mui/material/TableRow";
import Tooltip from "@mui/material/Tooltip";
import Typography from "@mui/material/Typography";
import ContentCopyIcon from "@mui/icons-material/ContentCopy";
import ExpandMoreIcon from "@mui/icons-material/ExpandMore";
import OpenInNewIcon from "@mui/icons-material/OpenInNew";
import {
  clearActivity,
  fetchActivity,
  type ActivityGroup,
  type RequestRecord,
} from "@/api/diagnostics";
import { monoFontFamily } from "@/theme/theme";
import { useSettingsStore } from "@/stores/settingsStore";
import { darkTheme, lightTheme } from "@/theme/theme";
import { useMediaQuery } from "@mui/material";

interface Props {
  open: boolean;
  onClose: () => void;
}

function formatDuration(ms: number): string {
  if (ms < 1000) return `${ms.toFixed(0)} ms`;
  return `${(ms / 1000).toFixed(2)} s`;
}

function formatTimestamp(iso: string): string {
  const d = new Date(iso);
  const h = String(d.getHours()).padStart(2, "0");
  const m = String(d.getMinutes()).padStart(2, "0");
  const s = String(d.getSeconds()).padStart(2, "0");
  const ms = String(d.getMilliseconds()).padStart(3, "0");
  return `${h}:${m}:${s}.${ms}`;
}

/** Shorten a query string by removing long path/query values for readability. */
function shortenQuery(query: string): string {
  const params = new URLSearchParams(query);
  // Remove _activity from display — it's metadata, not a real param
  params.delete("_activity");
  if (params.size === 0) return "";
  return "?" + params.toString();
}

function durationColor(ms: number): "info" | "warning" | "default" {
  if (ms < 100) return "info";
  if (ms < 500) return "default";
  return "warning";
}

function statusColor(code: number): "info" | "warning" | "default" {
  if (code >= 200 && code < 300) return "info";
  if (code >= 400) return "warning";
  return "default";
}

/** Build a clean JSON object for a single request row. */
function rowToJson(group: ActivityGroup, req: RequestRecord) {
  return {
    activity: group.activity,
    timestamp: req.timestamp,
    method: req.method,
    path: req.path,
    query: req.query || undefined,
    status_code: req.status_code,
    duration_ms: req.duration_ms,
  };
}

/** Build JSON for a single activity group. */
function groupToJson(g: ActivityGroup) {
  return {
    activity: g.activity,
    total_duration_ms: g.total_duration_ms,
    request_count: g.requests.length,
    requests: g.requests.map((r) => ({
      timestamp: r.timestamp,
      method: r.method,
      path: r.path,
      query: r.query || undefined,
      status_code: r.status_code,
      duration_ms: r.duration_ms,
    })),
  };
}

/** Build the full JSON export for all groups. */
function allToJson(groups: ActivityGroup[]) {
  return groups.map(groupToJson);
}

// ---------------------------------------------------------------------------
// Shared activity content (used by both dialog and popout)
// ---------------------------------------------------------------------------

interface ActivityContentProps {
  groups: ActivityGroup[];
  copyToClipboard: (data: unknown, label: string) => void;
}

function ActivityContent({ groups, copyToClipboard }: ActivityContentProps) {
  return (
    <>
      {groups.length === 0 && (
        <Box sx={{ p: 3, textAlign: "center" }}>
          <Typography color="text.secondary">No activity recorded yet.</Typography>
        </Box>
      )}
      {[...groups].reverse().map((group, gi) => (
        <Accordion
          key={groups.length - 1 - gi}
          defaultExpanded={gi === 0}
          disableGutters
          square
          sx={{ "&:before": { display: "none" } }}
        >
          <AccordionSummary expandIcon={<ExpandMoreIcon />}>
            <Box sx={{ display: "flex", alignItems: "center", gap: 1.5, width: "100%" }}>
              <Typography variant="body2" sx={{ fontWeight: 600, flexGrow: 1 }}>
                {group.activity}
              </Typography>
              <Chip
                label={`${group.requests.length} req`}
                size="small"
                variant="outlined"
              />
              <Chip
                label={formatDuration(group.total_duration_ms)}
                size="small"
                color={durationColor(group.total_duration_ms)}
                variant="outlined"
              />
              <Tooltip title="Copy activity as JSON">
                <IconButton
                  size="small"
                  onClick={(e) => {
                    e.stopPropagation();
                    copyToClipboard(groupToJson(group), "Activity copied");
                  }}
                >
                  <ContentCopyIcon sx={{ fontSize: 14 }} />
                </IconButton>
              </Tooltip>
            </Box>
          </AccordionSummary>
          <AccordionDetails sx={{ p: 0 }}>
            <Table size="small">
              <TableHead>
                <TableRow>
                  <TableCell sx={{ fontWeight: 600, width: 100 }}>Start Time</TableCell>
                  <TableCell sx={{ fontWeight: 600, width: 60 }}>Method</TableCell>
                  <TableCell sx={{ fontWeight: 600 }}>Endpoint</TableCell>
                  <TableCell sx={{ fontWeight: 600, width: 80 }} align="right">
                    Status
                  </TableCell>
                  <TableCell sx={{ fontWeight: 600, width: 100 }} align="right">
                    Duration
                  </TableCell>
                  <TableCell sx={{ width: 40 }} />
                </TableRow>
              </TableHead>
              <TableBody>
                {group.requests.map((req, ri) => (
                  <TableRow key={ri} hover>
                    <TableCell sx={{ fontFamily: monoFontFamily, fontSize: "0.75rem" }}>
                      {formatTimestamp(req.timestamp)}
                    </TableCell>
                    <TableCell sx={{ fontFamily: monoFontFamily, fontSize: "0.75rem" }}>
                      {req.method}
                    </TableCell>
                    <Tooltip
                      title={
                        <Typography sx={{ fontFamily: monoFontFamily, fontSize: "0.75rem", wordBreak: "break-all" }}>
                          {req.path}{req.query ? "?" + req.query : ""}
                        </Typography>
                      }
                      arrow
                      placement="bottom-start"
                      slotProps={{ tooltip: { sx: { maxWidth: 600 } } }}
                    >
                      <TableCell
                        sx={{
                          fontFamily: monoFontFamily,
                          fontSize: "0.75rem",
                          maxWidth: 400,
                          overflow: "hidden",
                          textOverflow: "ellipsis",
                          whiteSpace: "nowrap",
                          cursor: "help",
                        }}
                      >
                        {req.path}
                        <Typography
                          component="span"
                          sx={{
                            fontFamily: monoFontFamily,
                            fontSize: "0.7rem",
                            color: "text.secondary",
                            ml: 0.5,
                          }}
                        >
                          {shortenQuery(req.query)}
                        </Typography>
                      </TableCell>
                    </Tooltip>
                    <TableCell align="right">
                      <Chip
                        label={req.status_code}
                        size="small"
                        color={statusColor(req.status_code)}
                        variant="outlined"
                        sx={{ fontFamily: monoFontFamily, fontSize: "0.7rem" }}
                      />
                    </TableCell>
                    <TableCell align="right">
                      <Chip
                        label={formatDuration(req.duration_ms)}
                        size="small"
                        color={durationColor(req.duration_ms)}
                        variant="outlined"
                        sx={{ fontFamily: monoFontFamily, fontSize: "0.7rem" }}
                      />
                    </TableCell>
                    <TableCell sx={{ p: 0 }}>
                      <Tooltip title="Copy row as JSON">
                        <IconButton
                          size="small"
                          onClick={() => copyToClipboard(rowToJson(group, req), "Row copied")}
                        >
                          <ContentCopyIcon sx={{ fontSize: 14 }} />
                        </IconButton>
                      </Tooltip>
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </AccordionDetails>
        </Accordion>
      ))}
    </>
  );
}

// ---------------------------------------------------------------------------
// Draggable dialog paper
// ---------------------------------------------------------------------------

function DraggablePaper(props: PaperProps) {
  const paperRef = useRef<HTMLDivElement>(null);
  const offset = useRef({ x: 0, y: 0 });
  const dragging = useRef(false);

  const onMouseDown = useCallback((e: React.MouseEvent) => {
    const target = e.target as HTMLElement;
    if (!target.closest("[data-drag-handle]")) return;
    dragging.current = true;
    const paper = paperRef.current;
    if (!paper) return;
    const rect = paper.getBoundingClientRect();
    offset.current = { x: e.clientX - rect.left, y: e.clientY - rect.top };
    e.preventDefault();

    const onMouseMove = (ev: MouseEvent) => {
      if (!dragging.current || !paper) return;
      paper.style.position = "fixed";
      paper.style.margin = "0";
      paper.style.left = `${ev.clientX - offset.current.x}px`;
      paper.style.top = `${ev.clientY - offset.current.y}px`;
    };
    const onMouseUp = () => {
      dragging.current = false;
      document.removeEventListener("mousemove", onMouseMove);
      document.removeEventListener("mouseup", onMouseUp);
    };
    document.addEventListener("mousemove", onMouseMove);
    document.addEventListener("mouseup", onMouseUp);
  }, []);

  return (
    <Paper
      ref={paperRef}
      onMouseDown={onMouseDown}
      {...props}
      sx={{
        ...((props.sx ?? {}) as object),
        resize: "both",
        overflow: "auto",
        minWidth: 400,
        minHeight: 300,
      }}
    />
  );
}

// ---------------------------------------------------------------------------
// Popout window component
// ---------------------------------------------------------------------------

function useCurrentTheme() {
  const settings = useSettingsStore((s) => s.settings);
  const prefersDark = useMediaQuery("(prefers-color-scheme: dark)");
  const mode = settings?.theme ?? "browser";
  if (mode === "dark") return darkTheme;
  if (mode === "light") return lightTheme;
  return prefersDark ? darkTheme : lightTheme;
}

interface PopoutWindowProps {
  groups: ActivityGroup[];
  onRefresh: () => void;
  onClear: () => void;
  onClose: () => void;
  copyToClipboard: (data: unknown, label: string) => void;
  loading: boolean;
}

// Persistent ref outside the component so StrictMode double-mount doesn't lose it
let popupWindowRef: Window | null = null;

function PopoutWindow({ groups, onRefresh, onClear, onClose, copyToClipboard, loading }: PopoutWindowProps) {
  const containerRef = useRef<HTMLDivElement | null>(null);
  const cacheRef = useRef<ReturnType<typeof createCache> | null>(null);
  const [ready, setReady] = useState(false);
  const theme = useCurrentTheme();
  const onCloseRef = useRef(onClose);
  onCloseRef.current = onClose;
  const onRefreshRef = useRef(onRefresh);
  onRefreshRef.current = onRefresh;

  useEffect(() => {
    // Reuse existing popup if StrictMode re-mounts
    let popup = popupWindowRef && !popupWindowRef.closed ? popupWindowRef : null;

    if (!popup) {
      popup = window.open(
        "",
        "nightcrate-activity",
        "width=900,height=600,menubar=no,toolbar=no",
      );
      if (!popup) {
        onCloseRef.current();
        return;
      }
      popupWindowRef = popup;

      // Write a minimal HTML document so the popup has a proper DOM
      popup.document.open();
      popup.document.write(
        "<!DOCTYPE html><html><head><title>NightCrate — Activity Console</title></head>"
        + '<body style="margin:0"><div id="activity-root"></div></body></html>',
      );
      popup.document.close();
    }

    const container = popup.document.getElementById("activity-root");
    if (!container) {
      onCloseRef.current();
      return;
    }
    containerRef.current = container as HTMLDivElement;

    // Create emotion cache targeting the popup's head
    cacheRef.current = createCache({
      key: "popup",
      container: popup.document.head,
    });

    setReady(true);

    // Auto-refresh every 2 seconds
    const interval = setInterval(() => onRefreshRef.current(), 2000);

    // Poll for window closed (beforeunload is unreliable across browsers)
    const poll = setInterval(() => {
      if (popup!.closed) {
        clearInterval(poll);
        clearInterval(interval);
        popupWindowRef = null;
        onCloseRef.current();
      }
    }, 500);

    return () => {
      clearInterval(interval);
      clearInterval(poll);
      // Don't close the popup on cleanup — StrictMode double-mounts would kill it.
      // The popup closes itself when the user closes it (detected by poll),
      // or when PopoutWindow is truly removed (handlePopoutClose sets poppedOut=false).
    };
  }, []);

  if (!ready || !containerRef.current || !cacheRef.current) return null;

  return createPortal(
    <CacheProvider value={cacheRef.current}>
      <MuiThemeProvider theme={theme}>
        <CssBaseline />
        <Box sx={{ display: "flex", flexDirection: "column", height: "100vh" }}>
          <Box sx={{ display: "flex", alignItems: "center", gap: 2, px: 2, py: 1, borderBottom: 1, borderColor: "divider" }}>
            <Typography variant="h6" sx={{ flexGrow: 1 }}>
              Activity Console
            </Typography>
            <Chip label={`${groups.length} activities`} size="small" variant="outlined" />
            <Button onClick={onClear} color="warning" size="small" disabled={groups.length === 0}>
              Clear
            </Button>
            <Button
              onClick={() => {
                void navigator.clipboard.writeText(JSON.stringify(allToJson(groups), null, 2));
              }}
              size="small"
              disabled={groups.length === 0}
              startIcon={<ContentCopyIcon />}
            >
              Copy All
            </Button>
            <Button onClick={onRefresh} size="small" disabled={loading}>
              Refresh
            </Button>
          </Box>
          <Box sx={{ flex: 1, overflow: "auto" }}>
            <ActivityContent groups={groups} copyToClipboard={copyToClipboard} />
          </Box>
        </Box>
      </MuiThemeProvider>
    </CacheProvider>,
    containerRef.current,
  );
}

// ---------------------------------------------------------------------------
// Main exported component
// ---------------------------------------------------------------------------

export function ActivityConsole({ open, onClose }: Props) {
  const [groups, setGroups] = useState<ActivityGroup[]>([]);
  const [loading, setLoading] = useState(false);
  const [copyMsg, setCopyMsg] = useState<string | null>(null);
  const [poppedOut, setPoppedOut] = useState(false);

  const refresh = useCallback(async () => {
    setLoading(true);
    try {
      const data = await fetchActivity();
      setGroups(data.groups);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    if (open || poppedOut) refresh();
  }, [open, poppedOut, refresh]);

  const handleClear = useCallback(async () => {
    await clearActivity();
    setGroups([]);
  }, []);

  const copyToClipboard = useCallback(async (data: unknown, label: string) => {
    await navigator.clipboard.writeText(JSON.stringify(data, null, 2));
    setCopyMsg(label);
  }, []);

  const handlePopOut = useCallback(() => {
    onClose(); // close the dialog
    setPoppedOut(true);
  }, [onClose]);

  const handlePopoutClose = useCallback(() => {
    if (popupWindowRef && !popupWindowRef.closed) {
      popupWindowRef.close();
    }
    popupWindowRef = null;
    setPoppedOut(false);
  }, []);

  return (
    <>
      {poppedOut && (
        <PopoutWindow
          groups={groups}
          onRefresh={refresh}
          onClear={handleClear}
          onClose={handlePopoutClose}
          copyToClipboard={copyToClipboard}
          loading={loading}
        />
      )}

      <Dialog
        open={open && !poppedOut}
        onClose={onClose}
        maxWidth="lg"
        fullWidth
        PaperComponent={DraggablePaper}
      >
        <DialogTitle
          data-drag-handle
          sx={{ display: "flex", alignItems: "center", gap: 2, cursor: "move", userSelect: "none" }}
        >
          Activity Console
          <Chip label={`${groups.length} activities`} size="small" variant="outlined" />
          <Box sx={{ flexGrow: 1 }} />
          <Tooltip title="Open in separate window">
            <IconButton size="small" onClick={handlePopOut}>
              <OpenInNewIcon fontSize="small" />
            </IconButton>
          </Tooltip>
        </DialogTitle>
        <DialogContent dividers sx={{ p: 0 }}>
          <ActivityContent groups={groups} copyToClipboard={copyToClipboard} />
        </DialogContent>
        <DialogActions>
          <Button onClick={handleClear} color="warning" disabled={groups.length === 0}>
            Clear
          </Button>
          <Button
            onClick={() => copyToClipboard(allToJson(groups), "All activity copied")}
            disabled={groups.length === 0}
            startIcon={<ContentCopyIcon />}
          >
            Copy All
          </Button>
          <Button onClick={refresh} disabled={loading}>
            Refresh
          </Button>
          <Button onClick={onClose}>Close</Button>
        </DialogActions>

        <Snackbar
          open={copyMsg !== null}
          autoHideDuration={2000}
          onClose={() => setCopyMsg(null)}
          message={copyMsg}
          anchorOrigin={{ vertical: "bottom", horizontal: "center" }}
        />
      </Dialog>
    </>
  );
}
