import { useEffect, useMemo, useRef, useState } from "react";
import Button from "@mui/material/Button";
import Card from "@mui/material/Card";
import CardContent from "@mui/material/CardContent";
import Grid from "@mui/material/Grid";
import Stack from "@mui/material/Stack";
import Tooltip from "@mui/material/Tooltip";
import Typography from "@mui/material/Typography";
import DragIndicatorIcon from "@mui/icons-material/DragIndicator";
import {
  DndContext,
  KeyboardSensor,
  PointerSensor,
  closestCenter,
  useSensor,
  useSensors,
  type DragEndEvent,
} from "@dnd-kit/core";
import {
  SortableContext,
  arrayMove,
  rectSortingStrategy,
  sortableKeyboardCoordinates,
  useSortable,
} from "@dnd-kit/sortable";
import { CSS } from "@dnd-kit/utilities";
import { fetchSiderealTime, type SiderealTimeResponse } from "@/api/calculators";
import CalculatorAboutSection from "@/components/rigs/CalculatorAboutSection";
import { useCalculatorLocation } from "@/components/calculators/CalculatorLocationBar";
import {
  CLOCK_IDS,
  DEFAULT_CLOCK_ORDER,
  type ClockId,
} from "@/stores/calculatorsStore";
import { useSettingsStore } from "@/stores/settingsStore";

/** Sidereal / solar rate ratio (IAU 1976). */
const SIDEREAL_RATIO = 1.00273790935;

/** Julian Date offset for Unix epoch (1970-01-01T00:00:00 UTC = JD 2440587.5). */
const JD_UNIX_EPOCH = 2440587.5;

function pad2(n: number): string {
  return n < 10 ? `0${n}` : String(n);
}

function formatHms(date: Date): string {
  return `${pad2(date.getHours())}:${pad2(date.getMinutes())}:${pad2(date.getSeconds())}`;
}

function formatHmsUtc(date: Date): string {
  return `${pad2(date.getUTCHours())}:${pad2(date.getUTCMinutes())}:${pad2(date.getUTCSeconds())}`;
}

function formatLongDate(date: Date): string {
  return date.toLocaleDateString(undefined, {
    weekday: "long",
    year: "numeric",
    month: "long",
    day: "numeric",
  });
}

function formatLongDateUtc(date: Date): string {
  return date.toLocaleDateString(undefined, {
    weekday: "long",
    year: "numeric",
    month: "long",
    day: "numeric",
    timeZone: "UTC",
  });
}

/** HH:MM:SS in a given IANA timezone. Silent fallback to "—" on bad tz. */
function formatHmsInTz(date: Date, timeZone: string): string {
  try {
    return new Intl.DateTimeFormat("en-GB", {
      timeZone,
      hour: "2-digit",
      minute: "2-digit",
      second: "2-digit",
      hour12: false,
    }).format(date);
  } catch {
    return "\u2014";
  }
}

/** Long date in a given IANA timezone. Silent fallback to empty on bad tz. */
function formatLongDateInTz(date: Date, timeZone: string): string {
  try {
    return date.toLocaleDateString(undefined, {
      weekday: "long",
      year: "numeric",
      month: "long",
      day: "numeric",
      timeZone,
    });
  } catch {
    return "";
  }
}

/** Current UTC offset of a timezone as "UTC-07:00" / "UTC+05:30". */
function formatUtcOffset(timeZone: string): string {
  try {
    const parts = new Intl.DateTimeFormat("en-US", {
      timeZone,
      timeZoneName: "longOffset",
    }).formatToParts(new Date());
    const tzPart = parts.find((p) => p.type === "timeZoneName")?.value ?? "";
    if (tzPart === "GMT") return "UTC+00:00";
    return tzPart.replace(/^GMT/, "UTC");
  } catch {
    return "";
  }
}

/** Format fractional hours as HH:MM:SS, wrapping into [0, 24). */
function formatHoursAsHms(hours: number): string {
  let h = hours % 24;
  if (h < 0) h += 24;
  const totalSec = Math.round(h * 3600);
  const hh = Math.floor(totalSec / 3600) % 24;
  const rem = totalSec - Math.floor(totalSec / 3600) * 3600;
  const mm = Math.floor(rem / 60);
  const ss = rem - mm * 60;
  return `${pad2(hh)}:${pad2(mm)}:${pad2(ss)}`;
}

/**
 * Seven-clock dashboard with drag-to-reorder. The chosen order persists in
 * localStorage via the calculators Zustand store.
 */
/** Normalise a persisted order: drop unknown ids, append any missing defaults.
 *  Runs every render so adding a new clock id in the future automatically
 *  surfaces it at the end of whatever order the user had saved. */
function normalizeClockOrder(raw: readonly unknown[] | undefined): ClockId[] {
  const known = new Set<string>(CLOCK_IDS);
  const seen = new Set<ClockId>();
  const out: ClockId[] = [];
  if (Array.isArray(raw)) {
    for (const id of raw) {
      if (typeof id === "string" && known.has(id) && !seen.has(id as ClockId)) {
        out.push(id as ClockId);
        seen.add(id as ClockId);
      }
    }
  }
  for (const id of DEFAULT_CLOCK_ORDER) {
    if (!seen.has(id)) out.push(id);
  }
  return out;
}

export default function ClocksCalc() {
  const { locationId, location } = useCalculatorLocation();
  const settings = useSettingsStore((s) => s.settings);
  const updateSettings = useSettingsStore((s) => s.update);

  const clockOrder = useMemo(
    () => normalizeClockOrder(settings?.calculators_clock_order),
    [settings?.calculators_clock_order],
  );

  const setClockOrder = (order: ClockId[]) => {
    void updateSettings({ calculators_clock_order: order });
  };

  const resetClockOrder = () => {
    void updateSettings({ calculators_clock_order: [] });
  };

  const [now, setNow] = useState(() => Date.now());
  const [anchor, setAnchor] = useState<{
    anchorLstHours: number;
    anchorUnixMs: number;
  } | null>(null);
  const cancelRef = useRef(false);

  useEffect(() => {
    const id = setInterval(() => setNow(Date.now()), 1000);
    return () => clearInterval(id);
  }, []);

  useEffect(() => {
    if (locationId == null) return;
    cancelRef.current = false;

    const loadLst = async () => {
      try {
        const r: SiderealTimeResponse = await fetchSiderealTime(locationId, null);
        if (cancelRef.current) return;
        const anchorUnixMs = Date.parse(r.utc_iso);
        if (!isNaN(anchorUnixMs)) {
          setAnchor({ anchorLstHours: r.lst_hours, anchorUnixMs });
        }
      } catch {
        // Non-fatal — display shows "—" until the next retry succeeds.
      }
    };

    loadLst();
    const id = setInterval(loadLst, 60_000);
    return () => {
      cancelRef.current = true;
      clearInterval(id);
    };
  }, [locationId]);

  const lstDisplay = useMemo(() => {
    if (!anchor) return "\u2014";
    const elapsedHours = (now - anchor.anchorUnixMs) / 3_600_000;
    const lstNow = anchor.anchorLstHours + elapsedHours * SIDEREAL_RATIO;
    return formatHoursAsHms(lstNow);
  }, [anchor, now]);

  const nowDate = new Date(now);
  const jd = now / 86_400_000 + JD_UNIX_EPOCH;
  const mjd = jd - 2_400_000.5;

  // Build the card definitions keyed by clock id; actual render order is
  // driven by the persisted `clockOrder`.
  const cardsById: Record<ClockId, ClockCardProps> = {
    local: {
      title: "Local Time",
      primary: formatHms(nowDate),
      secondary: formatLongDate(nowDate),
      help: "in your browser's time zone",
    },
    utc: {
      title: "UTC",
      primary: formatHmsUtc(nowDate),
      secondary: formatLongDateUtc(nowDate),
      help: "coordinated universal time",
    },
    lst: {
      title: "Local Sidereal Time",
      primary: locationId == null ? "\u2014" : lstDisplay,
      secondary: null,
      help:
        locationId == null
          ? "Select a location above"
          : "at the selected location",
    },
    "display-tz": {
      title: "Display Timezone",
      primary: location ? formatHmsInTz(nowDate, location.timezone) : "\u2014",
      secondary: location ? formatLongDateInTz(nowDate, location.timezone) : null,
      help: location
        ? `${location.timezone}${formatUtcOffset(location.timezone) ? `  (${formatUtcOffset(location.timezone)})` : ""}`
        : "Select a location above",
    },
    "location-tz": {
      title: "Location Timezone",
      primary: location?.geo_timezone
        ? formatHmsInTz(nowDate, location.geo_timezone)
        : "\u2014",
      secondary: location?.geo_timezone
        ? formatLongDateInTz(nowDate, location.geo_timezone)
        : null,
      help: location?.geo_timezone
        ? `${location.geo_timezone}${formatUtcOffset(location.geo_timezone) ? `  (${formatUtcOffset(location.geo_timezone)})` : ""}`
        : location
          ? "no geographic timezone on this location"
          : "Select a location above",
    },
    jd: {
      title: "Julian Date",
      primary: jd.toFixed(5),
      secondary: null,
      help: "days since -4712-01-01 12:00 TT",
    },
    mjd: {
      title: "Modified Julian Date",
      primary: mjd.toFixed(5),
      secondary: null,
      help: "JD \u2212 2 400 000.5",
    },
  };

  const sensors = useSensors(
    useSensor(PointerSensor, { activationConstraint: { distance: 4 } }),
    useSensor(KeyboardSensor, {
      coordinateGetter: sortableKeyboardCoordinates,
    }),
  );

  const handleDragEnd = (event: DragEndEvent) => {
    const { active, over } = event;
    if (!over || active.id === over.id) return;
    const oldIndex = clockOrder.indexOf(active.id as ClockId);
    const newIndex = clockOrder.indexOf(over.id as ClockId);
    if (oldIndex < 0 || newIndex < 0) return;
    setClockOrder(arrayMove(clockOrder, oldIndex, newIndex));
  };

  const orderIsDefault =
    clockOrder.length === DEFAULT_CLOCK_ORDER.length &&
    clockOrder.every((id, i) => id === DEFAULT_CLOCK_ORDER[i]);

  return (
    <Stack spacing={3}>
      <Stack
        direction="row"
        spacing={2}
        alignItems="center"
        justifyContent="space-between"
      >
        <Typography variant="h5">Clocks</Typography>
        <Tooltip title="Restore the default clock order">
          <span>
            <Button
              size="small"
              onClick={resetClockOrder}
              disabled={orderIsDefault}
            >
              Reset order
            </Button>
          </span>
        </Tooltip>
      </Stack>

      <DndContext
        sensors={sensors}
        collisionDetection={closestCenter}
        onDragEnd={handleDragEnd}
      >
        <SortableContext items={clockOrder} strategy={rectSortingStrategy}>
          <Grid container spacing={2}>
            {clockOrder.map((id) => (
              <SortableClockCard key={id} id={id} {...cardsById[id]} />
            ))}
          </Grid>
        </SortableContext>
      </DndContext>

      <CalculatorAboutSection>
        <p>
          Local, UTC, JD, and MJD clocks tick in the browser from{" "}
          <code>Date.now()</code>. Julian Date uses the conventional Unix-epoch
          offset of <code>2440587.5</code> days.
        </p>
        <p>
          <strong>Local Sidereal Time</strong> is fetched from the server (via
          astropy&rsquo;s <code>sidereal_time</code>) on location change and
          then refreshed once every 60&nbsp;s. Between server calls the clock
          advances in the browser at the sidereal rate,
          <code>1.00273790935</code> of solar time, keeping the display smooth
          without drifting.
        </p>
        <p>
          Drag any card by its handle to reorder. The arrangement is saved in
          your browser and restored on the next visit.
        </p>
      </CalculatorAboutSection>
    </Stack>
  );
}

interface ClockCardProps {
  title: string;
  primary: string;
  secondary: string | null;
  help: string;
}

function SortableClockCard(props: ClockCardProps & { id: ClockId }) {
  const { id, title, primary, secondary, help } = props;
  const {
    attributes,
    listeners,
    setNodeRef,
    setActivatorNodeRef,
    transform,
    transition,
    isDragging,
  } = useSortable({ id });

  const style: React.CSSProperties = {
    transform: CSS.Transform.toString(transform),
    transition,
    opacity: isDragging ? 0.5 : 1,
  };

  return (
    <Grid size={{ xs: 12, sm: 6, md: 4 }} ref={setNodeRef} style={style}>
      <Card
        variant="outlined"
        sx={{
          height: "100%",
          boxShadow: isDragging ? 4 : 0,
          cursor: isDragging ? "grabbing" : "default",
        }}
      >
        <CardContent sx={{ position: "relative" }}>
          <Tooltip title="Drag to reorder" placement="top">
            <span
              ref={setActivatorNodeRef}
              {...attributes}
              {...listeners}
              aria-label={`Reorder ${title}`}
              style={{
                position: "absolute",
                top: 6,
                right: 6,
                display: "inline-flex",
                alignItems: "center",
                color: "rgba(128, 128, 128, 0.8)",
                cursor: "grab",
                touchAction: "none",
                padding: 2,
                borderRadius: 4,
              }}
            >
              <DragIndicatorIcon fontSize="small" />
            </span>
          </Tooltip>

          <Typography
            variant="caption"
            color="text.secondary"
            sx={{ textTransform: "uppercase", letterSpacing: 0.5 }}
          >
            {title}
          </Typography>
          <Typography
            variant="h4"
            sx={{ fontFamily: "monospace", mt: 0.5, lineHeight: 1.2 }}
          >
            {primary}
          </Typography>
          {secondary && (
            <Typography variant="body2" color="text.secondary" sx={{ mt: 0.5 }}>
              {secondary}
            </Typography>
          )}
          <Typography
            variant="caption"
            color="text.secondary"
            sx={{ display: "block", mt: 0.5, fontStyle: "italic" }}
          >
            {help}
          </Typography>
        </CardContent>
      </Card>
    </Grid>
  );
}
