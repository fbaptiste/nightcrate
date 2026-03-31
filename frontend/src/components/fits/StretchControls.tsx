import { useCallback } from "react";
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
import type { StretchParams } from "@/api/fits";

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

  const isStf = params.stretch === "stf";
  const isAsinh = params.stretch === "asinh";

  return (
    <Box sx={{ display: "flex", flexDirection: "column", gap: 1.5, minWidth: 0 }}>
      {label && (
        <Typography variant="caption" fontWeight="bold" sx={{ color: color ?? "text.primary" }}>
          {label}
        </Typography>
      )}

      {/* Stretch type */}
      <FormControl size="small" fullWidth>
        <InputLabel>Stretch</InputLabel>
        <Select
          label="Stretch"
          value={params.stretch}
          onChange={(e) => set({ stretch: e.target.value as StretchParams["stretch"] })}
        >
          <MenuItem value="stf">Auto</MenuItem>
          <MenuItem value="linear">Linear</MenuItem>
          <MenuItem value="asinh">Asinh</MenuItem>
        </Select>
      </FormControl>

      {/* ── STF controls ── */}
      {isStf && (
        <>
          <Box>
            <Typography variant="caption" color="text.secondary">
              Shadow: {params.shadow.toFixed(6)}
            </Typography>
            <Slider
              min={0} max={0.2} step={0.000001}
              value={params.shadow}
              onChange={(_, v) => set({ shadow: v as number })}
              size="small"
            />
          </Box>
          <Box>
            <Typography variant="caption" color="text.secondary">
              Midtone: {params.midtone.toFixed(6)}
            </Typography>
            <Slider
              min={0} max={0.5} step={0.000001}
              value={params.midtone}
              onChange={(_, v) => set({ midtone: v as number })}
              size="small"
            />
          </Box>
          <Box>
            <Typography variant="caption" color="text.secondary">
              Highlight: {params.highlight.toFixed(6)}
            </Typography>
            <Slider
              min={0.5} max={1} step={0.000001}
              value={params.highlight}
              onChange={(_, v) => set({ highlight: v as number })}
              size="small"
            />
          </Box>
        </>
      )}

      {/* ── Linear controls ── */}
      {!isStf && !isAsinh && (
        <>
          <Box>
            <Typography variant="caption" color="text.secondary">
              Black point: {params.black_pct.toFixed(2)}%
            </Typography>
            <Slider
              min={0} max={100} step={0.01}
              value={params.black_pct}
              onChange={(_, v) => set({ black_pct: v as number })}
              size="small"
            />
          </Box>
          <Box>
            <Typography variant="caption" color="text.secondary">
              White point: {params.white_pct.toFixed(2)}%
            </Typography>
            <Slider
              min={0} max={100} step={0.01}
              value={params.white_pct}
              onChange={(_, v) => set({ white_pct: v as number })}
              size="small"
            />
          </Box>
          <Box>
            <Typography variant="caption" color="text.secondary">
              Gamma: {params.gamma.toFixed(2)}
            </Typography>
            <Slider
              min={0.1} max={10} step={0.05}
              value={params.gamma}
              onChange={(_, v) => set({ gamma: v as number })}
              size="small"
            />
          </Box>
        </>
      )}

      {/* ── Asinh controls ── */}
      {isAsinh && (
        <>
          <Box>
            <Typography variant="caption" color="text.secondary">
              Black point: {params.black_pct.toFixed(2)}%
            </Typography>
            <Slider
              min={0} max={100} step={0.01}
              value={params.black_pct}
              onChange={(_, v) => set({ black_pct: v as number })}
              size="small"
            />
          </Box>
          <Box>
            <Typography variant="caption" color="text.secondary">
              White point: {params.white_pct.toFixed(2)}%
            </Typography>
            <Slider
              min={0} max={100} step={0.01}
              value={params.white_pct}
              onChange={(_, v) => set({ white_pct: v as number })}
              size="small"
            />
          </Box>
          <Box>
            <Typography variant="caption" color="text.secondary">
              Softening (β): {params.asinh_beta.toFixed(3)}
            </Typography>
            <Slider
              min={0.001} max={5} step={0.001}
              value={params.asinh_beta}
              onChange={(_, v) => set({ asinh_beta: v as number })}
              size="small"
            />
          </Box>
        </>
      )}
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

const CHANNEL_COLORS = ["#4878CF", "#F5A623", "#7EC8E3"]; // blue / orange / teal — color-blind safe
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
  function updateChannel(i: number, p: StretchParams) {
    const next = [...perChannel] as [StretchParams, StretchParams, StretchParams];
    next[i] = p;
    onPerChannelChange(next);
  }

  return (
    <Box sx={{ display: "flex", flexDirection: "column", gap: 2, p: 1.5, overflowX: "hidden" }}>
      {/* Linked/Unlinked toggle — only shown for color images */}
      {isColor && (
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

      {/* Controls */}
      {(!isColor || isLinked) && (
        <ChannelControls
          label=""
          params={linked}
          onChange={onLinkedChange}
        />
      )}

      {isColor && !isLinked && (
        <Box sx={{ display: "flex", gap: 3 }}>
          {perChannel.map((ch, i) => (
            <ChannelControls
              key={i}
              label={CHANNEL_LABELS[i]}
              color={CHANNEL_COLORS[i]}
              params={ch}
              onChange={(p) => updateChannel(i, p)}
            />
          ))}
        </Box>
      )}

      <Button variant="text" size="small" onClick={onReset} sx={{ alignSelf: "flex-start", fontSize: "0.75rem", mt: 0.5 }}>
        Reset to auto
      </Button>
    </Box>
  );
}
