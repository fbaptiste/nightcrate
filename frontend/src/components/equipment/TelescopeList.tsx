import { useRef, useState } from "react";
import Box from "@mui/material/Box";
import Chip from "@mui/material/Chip";
import Popover from "@mui/material/Popover";
import Typography from "@mui/material/Typography";
import { type GridColDef } from "@mui/x-data-grid";
import {
  fetchTelescopes,
  deleteTelescope,
  type Telescope,
  type TelescopeConfiguration,
} from "@/api/equipment";
import EquipmentList from "./EquipmentList";
import TelescopeFormDialog from "./TelescopeFormDialog";
import DetailField from "@/components/equipment/shared/DetailField";
import ExternalLink from "@/components/equipment/shared/ExternalLink";

function TelescopeForm({
  open,
  item,
  onClose,
  onSaved,
}: {
  open: boolean;
  item: Telescope | null;
  onClose: () => void;
  onSaved: () => void;
}) {
  return (
    <TelescopeFormDialog
      open={open}
      telescope={item}
      onClose={onClose}
      onSaved={onSaved}
    />
  );
}

function ConfigChip({ cfg }: { cfg: TelescopeConfiguration }) {
  const anchorRef = useRef<HTMLDivElement | null>(null);
  const [open, setOpen] = useState(false);

  return (
    <>
      <Chip
        ref={anchorRef}
        label={cfg.config_name}
        size="small"
        variant={cfg.is_native ? "filled" : "outlined"}
        onMouseEnter={() => setOpen(true)}
        onMouseLeave={() => setOpen(false)}
        sx={{ cursor: "default" }}
      />
      <Popover
        open={open}
        anchorEl={anchorRef.current}
        onClose={() => setOpen(false)}
        anchorOrigin={{ vertical: "bottom", horizontal: "left" }}
        transformOrigin={{ vertical: "top", horizontal: "left" }}
        sx={{ pointerEvents: "none", mt: 0.5 }}
        disableRestoreFocus
      >
        <Box sx={{ p: 1.5, maxWidth: 320 }}>
          <Typography variant="subtitle2" gutterBottom>
            {cfg.config_name}
            {cfg.is_native ? " (native)" : ""}
          </Typography>
          {cfg.accessory_name && (
            <PopoverRow label="Accessory" value={cfg.accessory_name} />
          )}
          <PopoverRow
            label="Focal Length"
            value={`${cfg.effective_focal_length_mm}mm`}
          />
          <PopoverRow
            label="Focal Ratio"
            value={`f/${cfg.effective_focal_ratio}`}
          />
          {cfg.reduction_factor != null && cfg.reduction_factor !== 1.0 && (
            <PopoverRow label="Reduction" value={`${cfg.reduction_factor}x`} />
          )}
          {cfg.effective_image_circle_mm != null && (
            <PopoverRow
              label="Image Circle"
              value={`${cfg.effective_image_circle_mm}mm`}
            />
          )}
          {cfg.effective_back_focus_mm != null && (
            <PopoverRow
              label="Back Focus"
              value={`${cfg.effective_back_focus_mm}mm`}
            />
          )}
          {cfg.notes && (
            <Typography
              variant="caption"
              color="text.secondary"
              sx={{ display: "block", mt: 0.5 }}
            >
              {cfg.notes}
            </Typography>
          )}
        </Box>
      </Popover>
    </>
  );
}

function PopoverRow({ label, value }: { label: string; value: string }) {
  return (
    <Box sx={{ display: "flex", gap: 1, py: 0.15 }}>
      <Typography variant="caption" color="text.secondary" sx={{ minWidth: 90 }}>
        {label}
      </Typography>
      <Typography variant="caption">{value}</Typography>
    </Box>
  );
}

const columns: GridColDef<Telescope>[] = [
  {
    field: "manufacturer",
    headerName: "Manufacturer",
    flex: 1,
    minWidth: 130,
    valueGetter: (_value, row) => row.manufacturer.name,
  },
  {
    field: "model_name",
    headerName: "Model",
    flex: 1.5,
    minWidth: 160,
  },
  {
    field: "optical_design",
    headerName: "Design",
    width: 130,
    valueGetter: (_value, row) => row.optical_design?.name ?? "—",
  },
  {
    field: "aperture_mm",
    headerName: "Aperture",
    width: 110,
    valueGetter: (_value, row) => `${row.aperture_mm}mm`,
  },
  {
    field: "configurations",
    headerName: "Configs",
    width: 90,
    valueGetter: (_value, row) => row.configurations.length,
  },
];

export default function TelescopeList({ mineOnly = false }: { mineOnly?: boolean } = {}) {
  return (
    <EquipmentList<Telescope>
      title={mineOnly ? "My OTAs" : "OTAs"}
      addLabel="Add OTA"
      queryKey={mineOnly ? "my-telescopes" : "telescopes"}
      mineOnly={mineOnly}
      tableName="telescope"
      fetchFn={fetchTelescopes}
      deleteFn={deleteTelescope}
      columns={columns}
      dropdownFilterFields={["optical_design"]}
      getItemName={(t) => t.model_name}
      FormDialog={TelescopeForm}
      renderDetail={(item) => (
        <Box sx={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 0, columnGap: 4 }}>
          <DetailField label="Manufacturer" value={item.manufacturer.name} />
          <DetailField label="Optical Design" value={item.optical_design?.name ?? null} />
          <DetailField label="Aperture" value={`${item.aperture_mm}mm`} />
          <DetailField label="Image Circle" value={item.image_circle_mm != null ? `${item.image_circle_mm}mm` : null} />
          <DetailField label="Weight" value={item.weight_kg != null ? `${item.weight_kg}kg` : null} />
          <DetailField label="Obstruction %" value={item.obstruction_pct != null ? `${item.obstruction_pct}%` : null} />
          <DetailField
            label="Connectors"
            value={item.connectors.length > 0 ? item.connectors.map((c) => c.name).join(", ") : null}
          />
          <DetailField
            label="Configurations"
            value={
              item.configurations.length > 0 ? (
                <Box sx={{ display: "flex", flexWrap: "wrap", gap: 0.5 }}>
                  {item.configurations.map((cfg) => (
                    <ConfigChip key={cfg.id} cfg={cfg} />
                  ))}
                </Box>
              ) : null
            }
          />
          <DetailField label="Notes" value={item.notes ?? null} />
          <DetailField
            label="Source"
            value={item.source_url ? <ExternalLink href={item.source_url} /> : null}
          />
        </Box>
      )}
    />
  );
}
