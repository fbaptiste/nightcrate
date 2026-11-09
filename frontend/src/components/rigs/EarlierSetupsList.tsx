import { useState } from "react";
import Box from "@mui/material/Box";
import Button from "@mui/material/Button";
import Divider from "@mui/material/Divider";
import Typography from "@mui/material/Typography";
import CorrectSetupDialog from "@/components/rigs/CorrectSetupDialog";
import type { EquipmentOptions, Rig, RigSetup } from "@/api/rigs";

interface EarlierSetupsListProps {
  rig: Rig;
  setups: RigSetup[];
  options: EquipmentOptions;
  onCorrected: () => void;
}

function nightsLabel(count: number): string {
  return `${count} ${count === 1 ? "night" : "nights"}`;
}

function formatSetupDate(value: string): string {
  const isoValue = value.includes("T") ? value : value.replace(" ", "T");
  const date = new Date(/[zZ]|[+-]\d\d:\d\d$/.test(isoValue) ? isoValue : `${isoValue}Z`);
  return new Intl.DateTimeFormat("en-GB", {
    day: "numeric",
    month: "short",
    year: "numeric",
  }).format(date);
}

function changedParts(rig: Rig, setup: RigSetup): { label: string; value: string }[] {
  const parts = setup.parts;
  const changed: { label: string; value: string }[] = [];
  if (parts.telescope_configuration_id !== rig.telescope_configuration_id) {
    changed.push({ label: "Telescope", value: `${parts.telescope_name}, ${parts.telescope_config_name}` });
  }
  if (parts.camera_id !== rig.camera_id) changed.push({ label: "Camera", value: parts.camera_name });
  const setupSlots = parts.filter_slots.map((slot) => `${slot.slot_number}:${slot.filter_id}`).join(",");
  const rigSlots = rig.filter_slots.map((slot) => `${slot.slot_number}:${slot.filter_id}`).join(",");
  if (
    parts.filter_wheel_id !== rig.filter_wheel_id ||
    parts.single_filter_id !== rig.single_filter_id ||
    setupSlots !== rigSlots
  ) {
    const slots = parts.filter_slots.map((slot) => slot.filter_name).join(", ");
    changed.push({
      label: "Filters",
      value: parts.filter_wheel_name
        ? `${parts.filter_wheel_name}${slots ? `: ${slots}` : ""}`
        : parts.single_filter_name ?? "None",
    });
  }
  const singles: [string, number | null, number | null, string | null][] = [
    ["Mount", parts.mount_id, rig.mount_id, parts.mount_name],
    ["Focuser", parts.focuser_id, rig.focuser_id, parts.focuser_name],
    ["Guide camera", parts.guide_camera_id, rig.guide_camera_id, parts.guide_camera_name],
    ["Computer", parts.computer_id, rig.computer_id, parts.computer_name],
  ];
  for (const [label, setupId, rigId, name] of singles) {
    if (setupId !== rigId) changed.push({ label, value: name ?? "None" });
  }
  if (parts.oag_id !== rig.oag_id || parts.guide_scope_id !== rig.guide_scope_id) {
    changed.push({ label: "Guiding", value: parts.oag_name ?? parts.guide_scope_name ?? "None" });
  }
  const setupSoftware = parts.software.map((item) => item.id).sort((a, b) => a - b).join(",");
  const rigSoftware = rig.software.map((item) => item.id).sort((a, b) => a - b).join(",");
  if (setupSoftware !== rigSoftware) {
    changed.push({
      label: "Software",
      value: parts.software.map((item) => item.name).join(", ") || "None",
    });
  }
  return changed;
}

export default function EarlierSetupsList({
  rig,
  setups,
  options,
  onCorrected,
}: EarlierSetupsListProps) {
  const [editing, setEditing] = useState<RigSetup | null>(null);
  if (setups.length === 0) return null;

  return (
    <Box sx={{ mt: 3 }}>
      <Divider
        sx={(theme) => ({
          mb: 2,
          borderColor: theme.palette.mode === "dark" ? "#34373d" : "#dcd9d4",
        })}
      />
      <Typography variant="subtitle1" sx={{ fontWeight: 600, mb: 1 }}>
        Earlier setups
      </Typography>
      <Box sx={{ display: "grid", gap: 1.5 }}>
        {setups.map((setup) => {
          const changes = changedParts(rig, setup);
          return (
            <Box
              key={setup.id}
              sx={(theme) => ({
                border: "1px solid",
                borderColor: theme.palette.mode === "dark" ? "#34373d" : "#dcd9d4",
                borderRadius: "8px",
                p: 1.5,
              })}
            >
              <Box sx={{ display: "flex", alignItems: "center", flexWrap: "wrap", gap: 1 }}>
                <Typography sx={{ fontSize: "15px", fontWeight: 600 }}>
                  Until {formatSetupDate(setup.until_at)}
                </Typography>
                <Typography sx={{ fontSize: "13px", color: "text.secondary" }}>
                  {nightsLabel(setup.night_count)}
                </Typography>
                <Box sx={{ flex: 1 }} />
                <Button size="small" onClick={() => setEditing(setup)}>
                  Correct this setup
                </Button>
              </Box>
              {changes.length > 0 && (
                <Box sx={{ display: "grid", gridTemplateColumns: "100px 1fr", gap: "4px 12px", mt: 1 }}>
                  {changes.map((change) => (
                    <Box key={change.label} sx={{ display: "contents" }}>
                      <Typography sx={{ fontSize: "13px", color: "text.secondary" }}>
                        {change.label}
                      </Typography>
                      <Typography sx={{ fontSize: "13px" }}>{change.value}</Typography>
                    </Box>
                  ))}
                </Box>
              )}
            </Box>
          );
        })}
      </Box>
      <CorrectSetupDialog
        open={editing !== null}
        setup={editing}
        options={options}
        onClose={() => setEditing(null)}
        onSaved={onCorrected}
      />
    </Box>
  );
}
