/**
 * Collapsible chronological list of INFO events in a section.
 *
 * Renders one row per event with its friendly kind label, the
 * wall-clock timestamp (falling back to elapsed seconds when no
 * section start is available), and the raw message / parsed fields.
 * Clicking a row calls ``onEventClick`` — the parent page routes
 * that to the chart's ``scrollToTime`` imperative handle.
 *
 * Matches the collapsible-panel family (``StatsPanel``,
 * ``ScatterPlot``) so the Graph tab reads as a consistent stack.
 */
import { useState } from "react";
import Box from "@mui/material/Box";
import Chip from "@mui/material/Chip";
import Collapse from "@mui/material/Collapse";
import List from "@mui/material/List";
import ListItemButton from "@mui/material/ListItemButton";
import Stack from "@mui/material/Stack";
import Typography from "@mui/material/Typography";
import ExpandMoreIcon from "@mui/icons-material/ExpandMore";
import type { EventKind, LogEvent } from "@/api/phd2";
import { formatWallClock } from "@/lib/phd2Format";
import { RIG_BLUE, RIG_ORANGE, RIG_TEAL } from "@/lib/rigColors";

interface Props {
  events: LogEvent[];
  startIso?: string;
  onEventClick?: (event: LogEvent) => void;
  title?: string;
  collapsible?: boolean;
  defaultExpanded?: boolean;
}

/** Friendly kind labels. Keep in sync with ``phd2_parser.py`` event
 *  kinds — any new kind without a mapping falls back to Start Case. */
const KIND_LABELS: Record<EventKind, string> = {
  settle_begin: "Settle start",
  settle_end: "Settle complete",
  lock_position_set: "Lock position",
  dither: "Dither",
  server_pause: "Server paused",
  server_resume: "Server resumed",
  star_selected: "Star selected",
  alert: "Alert",
  guiding_enabled: "Guiding enabled",
  guiding_disabled: "Guiding disabled",
  info: "Info",
};

/** Category → chip colour. Keeps the row density readable without
 *  overloading the palette. */
const KIND_COLOR: Record<EventKind, string> = {
  settle_begin: RIG_BLUE,
  settle_end: RIG_BLUE,
  dither: RIG_ORANGE,
  alert: RIG_ORANGE,
  lock_position_set: RIG_TEAL,
  star_selected: RIG_TEAL,
  guiding_enabled: RIG_TEAL,
  guiding_disabled: RIG_TEAL,
  server_pause: RIG_TEAL,
  server_resume: RIG_TEAL,
  info: RIG_TEAL,
};

export default function EventList({
  events,
  startIso,
  onEventClick,
  title = "Events",
  collapsible = true,
  defaultExpanded = true,
}: Props) {
  const [expanded, setExpanded] = useState(defaultExpanded);
  const isOpen = collapsible ? expanded : true;
  const toggle = () => collapsible && setExpanded((v) => !v);

  // Events with a non-null time_seconds can be jumped-to on the
  // chart. Sort by time for a stable chronological display — parser
  // already emits them in file order but this is cheap insurance.
  const anchored = [...events]
    .filter((e): e is LogEvent & { time_seconds: number } => e.time_seconds != null)
    .sort((a, b) => a.time_seconds - b.time_seconds);

  const header = (
    <Stack
      direction="row"
      alignItems="center"
      spacing={0.5}
      onClick={toggle}
      sx={{
        cursor: collapsible ? "pointer" : "default",
        userSelect: "none",
        mb: isOpen ? 1 : 0.25,
      }}
    >
      {collapsible && (
        <ExpandMoreIcon
          fontSize="small"
          sx={{
            transition: "transform 120ms ease",
            transform: isOpen ? "rotate(0deg)" : "rotate(-90deg)",
            color: "text.secondary",
          }}
        />
      )}
      <Typography variant="subtitle2">{title}</Typography>
      <Typography variant="caption" color="text.secondary" sx={{ ml: 1 }}>
        {anchored.length} · click to jump
      </Typography>
    </Stack>
  );

  if (anchored.length === 0) {
    return (
      <Box>
        {header}
        <Collapse in={isOpen} unmountOnExit>
          <Typography variant="body2" color="text.secondary" sx={{ pl: 3 }}>
            No events in this section.
          </Typography>
        </Collapse>
      </Box>
    );
  }

  return (
    <Box>
      {header}
      <Collapse in={isOpen} unmountOnExit>
        <List dense disablePadding sx={{ maxHeight: 300, overflow: "auto" }}>
          {anchored.map((e, i) => (
            <ListItemButton
              key={`${e.kind}-${e.time_seconds}-${i}`}
              onClick={() => onEventClick?.(e)}
              sx={{ py: 0.25 }}
            >
              <Stack
                direction="row"
                spacing={1}
                alignItems="center"
                sx={{ width: "100%", minWidth: 0 }}
              >
                <Chip
                  label={KIND_LABELS[e.kind] ?? startCase(e.kind)}
                  size="small"
                  sx={{
                    fontSize: 11,
                    height: 20,
                    bgcolor: `${KIND_COLOR[e.kind] ?? RIG_TEAL}22`,
                    color: KIND_COLOR[e.kind] ?? RIG_TEAL,
                    flexShrink: 0,
                    minWidth: 110,
                  }}
                />
                <Typography
                  variant="caption"
                  sx={{
                    fontVariantNumeric: "tabular-nums",
                    color: "text.secondary",
                    flexShrink: 0,
                    minWidth: 80,
                  }}
                >
                  {startIso
                    ? formatWallClock(startIso, e.time_seconds)
                    : `${e.time_seconds.toFixed(1)} s`}
                </Typography>
                <Typography
                  variant="caption"
                  sx={{
                    color: "text.secondary",
                    overflow: "hidden",
                    textOverflow: "ellipsis",
                    whiteSpace: "nowrap",
                    minWidth: 0,
                    flex: 1,
                  }}
                >
                  {formatEventDetail(e)}
                </Typography>
              </Stack>
            </ListItemButton>
          ))}
        </List>
      </Collapse>
    </Box>
  );
}

function startCase(k: string): string {
  return k
    .split("_")
    .map((w) => w.charAt(0).toUpperCase() + w.slice(1))
    .join(" ");
}

function formatEventDetail(e: LogEvent): string {
  if (e.kind === "dither") {
    const dx = e.parsed_fields.dx ?? "?";
    const dy = e.parsed_fields.dy ?? "?";
    return `Δx=${dx}, Δy=${dy} px`;
  }
  return e.raw_message;
}
