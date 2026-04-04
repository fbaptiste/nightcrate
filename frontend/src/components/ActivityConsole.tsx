import { useCallback, useEffect, useState } from "react";
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
import {
  clearActivity,
  fetchActivity,
  type ActivityGroup,
  type RequestRecord,
} from "@/api/diagnostics";
import { monoFontFamily } from "@/theme/theme";

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

export function ActivityConsole({ open, onClose }: Props) {
  const [groups, setGroups] = useState<ActivityGroup[]>([]);
  const [loading, setLoading] = useState(false);
  const [copyMsg, setCopyMsg] = useState<string | null>(null);

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
    if (open) refresh();
  }, [open, refresh]);

  const handleClear = useCallback(async () => {
    await clearActivity();
    setGroups([]);
  }, []);

  const copyToClipboard = useCallback(async (data: unknown, label: string) => {
    await navigator.clipboard.writeText(JSON.stringify(data, null, 2));
    setCopyMsg(label);
  }, []);

  return (
    <Dialog open={open} onClose={onClose} maxWidth="lg" fullWidth>
      <DialogTitle sx={{ display: "flex", alignItems: "center", gap: 2 }}>
        Activity Console
        <Chip label={`${groups.length} activities`} size="small" variant="outlined" />
      </DialogTitle>
      <DialogContent dividers sx={{ p: 0 }}>
        {groups.length === 0 && !loading && (
          <Box sx={{ p: 3, textAlign: "center" }}>
            <Typography color="text.secondary">No activity recorded yet.</Typography>
          </Box>
        )}
        {/* Show newest activity first */}
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
  );
}
