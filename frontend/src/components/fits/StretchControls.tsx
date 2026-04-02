import { useCallback, useState } from "react";
import Box from "@mui/material/Box";
import Button from "@mui/material/Button";
import FormControl from "@mui/material/FormControl";
import InputLabel from "@mui/material/InputLabel";
import MenuItem from "@mui/material/MenuItem";
import Select from "@mui/material/Select";
import Slider from "@mui/material/Slider";
import ToggleButton from "@mui/material/ToggleButton";
import ToggleButtonGroup from "@mui/material/ToggleButtonGroup";
import Typography from "@mui/material/Typography";
import type { StretchParams } from "@/api/images";
import { CHANNEL_COLOR_ARRAY } from "@/lib/channelColors";
import { monoFontFamily } from "@/theme/theme";

/** Slider with an editable value — click the number to type a precise value. */
function StretchSlider({ label, value, min, max, onChange }: {
  label: string;
  value: number;
  min: number;
  max: number;
  onChange: (v: number) => void;
}) {
  const [editing, setEditing] = useState(false);
  const [editText, setEditText] = useState("");

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

  return (
    <Box>
      <Box sx={{ display: "flex", alignItems: "baseline", justifyContent: "space-between" }}>
        <Typography variant="caption" color="text.secondary">
          {label}:
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
        min={min} max={max} step={0.000001}
        value={value}
        onChange={(_, v) => onChange(v as number)}
        size="small"
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
          // Push midtone along if shadow would pass it
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
          // Push midtone along if highlight would pass it
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
  perChannel: [StretchParams, StretchParams, StretchParams];
  isLinked: boolean;
  onLinkedChange: (p: StretchParams) => void;
  onPerChannelChange: (ch: [StretchParams, StretchParams, StretchParams]) => void;
  onLinkedToggle: (linked: boolean) => void;
  onReset: () => void;
}

const CHANNEL_LABELS = ["Red", "Green", "Blue"];

export function StretchControls({
  isColor,
  linked,
  perChannel,
  isLinked,
  onLinkedChange,
  onPerChannelChange,
  onLinkedToggle,
  onReset,
}: Props) {
  const isStf = linked.stretch === "stf";

  function updateChannel(i: number, p: StretchParams) {
    const next = [...perChannel] as [StretchParams, StretchParams, StretchParams];
    next[i] = p;
    onPerChannelChange(next);
  }

  function setStretchType(type: "stf" | "linear") {
    if (type === "stf") {
      onReset();
    } else {
      onLinkedChange({ ...linked, stretch: type });
    }
  }

  return (
    <Box sx={{ display: "flex", flexDirection: "column", gap: 2, p: 1.5, overflowX: "hidden" }}>
      {/* Stretch type selector */}
      <FormControl size="small" fullWidth>
        <InputLabel>Stretch</InputLabel>
        <Select
          label="Stretch"
          value={linked.stretch}
          onChange={(e) => setStretchType(e.target.value as "stf" | "linear")}
        >
          <MenuItem value="stf">Auto Stretch</MenuItem>
          <MenuItem value="linear">None</MenuItem>
        </Select>
      </FormControl>

      {/* Linked/Unlinked toggle — only for color images with active stretch */}
      {isStf && isColor && (
        <ToggleButtonGroup
          exclusive
          size="small"
          value={isLinked ? "linked" : "unlinked"}
          onChange={(_, v) => { if (v) onLinkedToggle(v === "linked"); }}
        >
          <ToggleButton value="linked">Linked</ToggleButton>
          <ToggleButton value="unlinked">Unlinked</ToggleButton>
        </ToggleButtonGroup>
      )}

      {/* Auto stretch controls */}
      {isStf && (!isColor || isLinked) && (
        <ChannelControls
          label=""
          params={linked}
          onChange={onLinkedChange}
        />
      )}

      {isStf && isColor && !isLinked && (
        <Box sx={{ display: "flex", gap: 3 }}>
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

      {/* No stretch: just a note */}
      {!isStf && (
        <Typography variant="caption" color="text.secondary">
          No stretch applied — displaying raw pixel values
        </Typography>
      )}

      {/* Reset button — only when stretch is active */}
      {isStf && (
        <Button variant="text" size="small" onClick={onReset} sx={{ alignSelf: "flex-start", fontSize: "0.75rem" }}>
          Reset to auto
        </Button>
      )}
    </Box>
  );
}
