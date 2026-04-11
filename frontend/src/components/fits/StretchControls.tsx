import { useCallback, useRef, useState } from "react";
import Box from "@mui/material/Box";
import Button from "@mui/material/Button";
import Slider from "@mui/material/Slider";
import ToggleButton from "@mui/material/ToggleButton";
import ToggleButtonGroup from "@mui/material/ToggleButtonGroup";
import Typography from "@mui/material/Typography";
import type { StretchParams } from "@/api/images";
import { CHANNEL_COLOR_ARRAY } from "@/lib/channelColors";
import { monoFontFamily } from "@/theme/theme";

const FINE_FACTOR = 0.1; // Shift+drag sensitivity reduction

/** Slider with an editable value and Shift+drag for fine control. */
function StretchSlider({ label, value, min, max, onChange }: {
  label: string;
  value: number;
  min: number;
  max: number;
  onChange: (v: number) => void;
}) {
  const [editing, setEditing] = useState(false);
  const [editText, setEditText] = useState("");
  const [fineMode, setFineMode] = useState(false);
  const dragging = useRef(false);
  const sliderRef = useRef<HTMLSpanElement>(null);
  const anchorValue = useRef(value);
  const anchorClientX = useRef(0);

  function startEdit() {
    setEditText(value.toFixed(6));
    setEditing(true);
  }

  function commitEdit() {
    setEditing(false);
    const v = parseFloat(editText);
    if (!isNaN(v)) {
      onChange(Math.max(min, Math.min(max, v)));
    }
  }

  function handleSliderChange(e: Event, raw: number | number[]) {
    const mouseEvent = e as unknown as MouseEvent;
    const isShift = mouseEvent?.shiftKey ?? false;

    if (isShift && dragging.current) {
      if (!fineMode) {
        // Entering fine mode mid-drag
        setFineMode(true);
        anchorValue.current = value;
        anchorClientX.current = mouseEvent.clientX;
        return;
      }
      // Fine mode: compute delta from mouse pixel movement
      const sliderEl = sliderRef.current;
      if (!sliderEl) return;
      const sliderWidth = sliderEl.getBoundingClientRect().width;
      const range = max - min;
      const pxDelta = mouseEvent.clientX - anchorClientX.current;
      const valueDelta = (pxDelta / sliderWidth) * range * FINE_FACTOR;
      const result = Math.max(min, Math.min(max, anchorValue.current + valueDelta));
      onChange(result);
    } else {
      if (fineMode) {
        // Leaving fine mode — released Shift mid-drag
        setFineMode(false);
      }
      onChange(raw as number);
    }
  }

  function handleMouseDown(e: React.MouseEvent) {
    dragging.current = true;
    if (e.shiftKey) {
      setFineMode(true);
      anchorValue.current = value;
      anchorClientX.current = e.clientX;
    } else {
      setFineMode(false);
    }
    const handleUp = () => {
      dragging.current = false;
      setFineMode(false);
      window.removeEventListener("mouseup", handleUp);
    };
    window.addEventListener("mouseup", handleUp);
  }

  return (
    <Box>
      <Box sx={{ display: "flex", alignItems: "baseline", justifyContent: "space-between" }}>
        <Typography variant="caption" color={fineMode ? "primary.main" : "text.secondary"}>
          {label}:{fineMode ? " (fine)" : ""}
        </Typography>
        {editing ? (
          <input
            autoFocus
            value={editText}
            onChange={(e) => setEditText(e.target.value)}
            onBlur={commitEdit}
            onKeyDown={(e) => { if (e.key === "Enter") commitEdit(); if (e.key === "Escape") setEditing(false); }}
            style={{
              width: 80,
              fontSize: "0.65rem",
              fontFamily: monoFontFamily,
              background: "transparent",
              border: "1px solid var(--mui-palette-primary-main)",
              borderRadius: 3,
              color: "inherit",
              padding: "1px 4px",
              textAlign: "right",
              outline: "none",
            }}
          />
        ) : (
          <Typography
            variant="caption"
            color="text.secondary"
            onClick={startEdit}
            sx={{
              fontFamily: monoFontFamily,
              cursor: "text",
              "&:hover": { color: "primary.main" },
            }}
          >
            {value.toFixed(6)}
          </Typography>
        )}
      </Box>
      <Slider
        ref={sliderRef}
        min={min} max={max} step={0.000001}
        value={value}
        onChange={handleSliderChange}
        onMouseDown={handleMouseDown}
        size="small"
        slotProps={{
          rail: { style: { pointerEvents: "none" } },
          track: { style: { pointerEvents: "none" } },
        }}
      />
    </Box>
  );
}

interface ChannelControlsProps {
  label: string;
  color?: string;
  params: StretchParams;
  onChange: (p: StretchParams) => void;
}

function ChannelControls({ label, color, params, onChange }: ChannelControlsProps) {
  const set = useCallback(
    (patch: Partial<StretchParams>) => onChange({ ...params, ...patch }),
    [params, onChange],
  );

  return (
    <Box sx={{ display: "flex", flexDirection: "column", gap: 1.5, minWidth: 0 }}>
      {label && (
        <Typography variant="caption" fontWeight="bold" sx={{ color: color ?? "text.primary" }}>
          {label}
        </Typography>
      )}

      <StretchSlider label="Shadow" value={params.shadow} min={0} max={1}
        onChange={(v) => {
          const s = Math.min(v, params.highlight - 0.000001);
          const m = params.midtone <= s ? s + 0.000001 : params.midtone;
          set({ shadow: s, midtone: Math.min(m, params.highlight - 0.000001) });
        }} />
      <StretchSlider label="Midtone" value={params.midtone} min={0} max={1}
        onChange={(v) => {
          set({ midtone: Math.max(params.shadow + 0.000001, Math.min(v, params.highlight - 0.000001)) });
        }} />
      <StretchSlider label="Highlight" value={params.highlight} min={0} max={1}
        onChange={(v) => {
          const h = Math.max(v, params.shadow + 0.000001);
          const m = params.midtone >= h ? h - 0.000001 : params.midtone;
          set({ highlight: h, midtone: Math.max(m, params.shadow + 0.000001) });
        }} />
    </Box>
  );
}

// ── Top-level component ───────────────────────────────────────────────────────

interface Props {
  isColor: boolean;
  linked: StretchParams;
  appliedLinked: StretchParams;
  perChannel: [StretchParams, StretchParams, StretchParams];
  appliedPerChannel: [StretchParams, StretchParams, StretchParams];
  isLinked: boolean;
  onLinkedChange: (p: StretchParams) => void;
  onPerChannelChange: (ch: [StretchParams, StretchParams, StretchParams]) => void;
  onStretchTypeChange: (type: "stf" | "linear") => void;
  onLinkedToggle: (linked: boolean) => void;
  onApply: () => void;
  onReset: () => void;
  onSliderHover?: (hovering: boolean) => void;
}

const CHANNEL_LABELS = ["Red", "Green", "Blue"];

export function StretchControls({
  isColor,
  linked,
  appliedLinked,
  perChannel,
  appliedPerChannel,
  isLinked,
  onLinkedChange,
  onPerChannelChange,
  onStretchTypeChange,
  onLinkedToggle,
  onApply,
  onReset,
  onSliderHover,
}: Props) {
  const isStf = linked.stretch === "stf" || linked.stretch === "auto";

  function updateChannel(i: number, p: StretchParams) {
    const next = [...perChannel] as [StretchParams, StretchParams, StretchParams];
    next[i] = { ...p, stretch: "stf" };
    onPerChannelChange(next);
  }

  // Detect whether slider values differ from what's currently rendered
  const hasPendingLinked = isStf && (
    linked.shadow !== appliedLinked.shadow ||
    linked.midtone !== appliedLinked.midtone ||
    linked.highlight !== appliedLinked.highlight
  );
  const hasPendingPerChannel = isStf && isColor && !isLinked && perChannel.some((ch, i) =>
    ch.shadow !== appliedPerChannel[i].shadow ||
    ch.midtone !== appliedPerChannel[i].midtone ||
    ch.highlight !== appliedPerChannel[i].highlight
  );
  const hasPending = hasPendingLinked || hasPendingPerChannel;

  return (
    <Box sx={{ display: "flex", flexDirection: "column", gap: 2, p: 1.5, overflowX: "hidden" }}>
      {/* Stretch type selector — applies immediately */}
      <ToggleButtonGroup
        exclusive
        size="small"
        value={isStf ? "stf" : "linear"}
        onChange={(_, v) => { if (v) onStretchTypeChange(v as "stf" | "linear"); }}
        fullWidth
      >
        <ToggleButton value="stf" sx={{ fontSize: "0.65rem" }}>Auto Stretch</ToggleButton>
        <ToggleButton value="linear" sx={{ fontSize: "0.65rem" }}>None</ToggleButton>
      </ToggleButtonGroup>

      {/* Linked/Unlinked toggle — applies immediately */}
      {isStf && isColor && (
        <ToggleButtonGroup
          exclusive
          size="small"
          value={isLinked ? "linked" : "unlinked"}
          onChange={(_, v) => { if (v) onLinkedToggle(v === "linked"); }}
        >
          <ToggleButton value="linked" sx={{ fontSize: "0.65rem" }}>Linked</ToggleButton>
          <ToggleButton value="unlinked" sx={{ fontSize: "0.65rem" }}>Unlinked</ToggleButton>
        </ToggleButtonGroup>
      )}

      {/* Linked stretch sliders — update local state only */}
      {isStf && (!isColor || isLinked) && (
        <Box
          onMouseEnter={() => onSliderHover?.(true)}
          onMouseLeave={() => onSliderHover?.(false)}
        >
          <ChannelControls
            label=""
            params={linked}
            onChange={onLinkedChange}
          />
        </Box>
      )}

      {/* Per-channel stretch sliders — update local state only */}
      {isStf && isColor && !isLinked && (
        <Box
          sx={{ display: "flex", flexDirection: "column", gap: 2 }}
          onMouseEnter={() => onSliderHover?.(true)}
          onMouseLeave={() => onSliderHover?.(false)}
        >
          {perChannel.map((ch, i) => (
            <ChannelControls
              key={i}
              label={CHANNEL_LABELS[i]}
              color={CHANNEL_COLOR_ARRAY[i]}
              params={ch}
              onChange={(p) => updateChannel(i, p)}
            />
          ))}
        </Box>
      )}

      {/* Apply + Reset buttons */}
      {isStf && (
        <Box sx={{ display: "flex", gap: 1, mt: "-8px" }}>
          <Button
            variant={hasPending ? "contained" : "outlined"}
            size="small"
            onClick={onApply}
            disabled={!hasPending}
            sx={{ fontSize: "0.65rem", flexGrow: 1 }}
          >
            Apply
          </Button>
          <Button
            variant="text"
            size="small"
            onClick={onReset}
            sx={{ fontSize: "0.65rem" }}
          >
            Reset
          </Button>
        </Box>
      )}

      {/* No stretch: just a note */}
      {!isStf && (
        <Typography variant="caption" color="text.secondary">
          No stretch applied — displaying raw pixel values
        </Typography>
      )}
    </Box>
  );
}
