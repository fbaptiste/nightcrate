import { useRef, useState } from "react";
import Button from "@mui/material/Button";
import ButtonGroup from "@mui/material/ButtonGroup";
import Chip from "@mui/material/Chip";
import IconButton from "@mui/material/IconButton";
import Menu from "@mui/material/Menu";
import MenuItem from "@mui/material/MenuItem";
import Stack from "@mui/material/Stack";
import ToggleButton from "@mui/material/ToggleButton";
import ToggleButtonGroup from "@mui/material/ToggleButtonGroup";
import Tooltip from "@mui/material/Tooltip";
import Typography from "@mui/material/Typography";
import FileDownloadIcon from "@mui/icons-material/FileDownload";
import FileUploadIcon from "@mui/icons-material/FileUpload";
import RestartAltIcon from "@mui/icons-material/RestartAlt";
import CompressIcon from "@mui/icons-material/Compress";
import AutoGraphIcon from "@mui/icons-material/AutoGraph";
import CompareArrowsIcon from "@mui/icons-material/CompareArrows";
import LayersIcon from "@mui/icons-material/Layers";
import UndoIcon from "@mui/icons-material/Undo";
import RedoIcon from "@mui/icons-material/Redo";
import KeyboardArrowDownIcon from "@mui/icons-material/KeyboardArrowDown";

import type { AltitudeRange } from "./HorizonChart";

export type ExportFormat = "nina" | "stellarium" | "csv";

interface Props {
  pointCount: number;
  altitudeRange: AltitudeRange;
  canUndo: boolean;
  canRedo: boolean;
  canExport: boolean;
  canReduce: boolean;
  smoothed: boolean;
  referenceCount: number; // 0 when no reference active
  canShowOriginal: boolean;
  showOriginal: boolean;
  onAltitudeRangeChange: (value: AltitudeRange) => void;
  onUndo: () => void;
  onRedo: () => void;
  onReset: () => void;
  onReduce: () => void;
  onSmoothedChange: (value: boolean) => void;
  onShowOriginalChange: (value: boolean) => void;
  onImport: (file: File) => void;
  onExport: (format: ExportFormat) => void;
  onUseAsReference: () => void;
  onClearReference: () => void;
}

export default function HorizonEditorToolbar({
  pointCount,
  altitudeRange,
  canUndo,
  canRedo,
  canExport,
  canReduce,
  smoothed,
  referenceCount,
  canShowOriginal,
  showOriginal,
  onAltitudeRangeChange,
  onUndo,
  onRedo,
  onReset,
  onReduce,
  onSmoothedChange,
  onShowOriginalChange,
  onImport,
  onExport,
  onUseAsReference,
  onClearReference,
}: Props) {
  const fileInputRef = useRef<HTMLInputElement | null>(null);
  const [exportAnchor, setExportAnchor] = useState<HTMLElement | null>(null);

  const handleFileSelected = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (file) onImport(file);
    e.target.value = ""; // allow re-picking the same file
  };

  const handleExportPick = (format: ExportFormat) => {
    setExportAnchor(null);
    onExport(format);
  };

  return (
    <Stack direction="row" spacing={1.5} alignItems="center" sx={{ flexWrap: "wrap" }}>
      <Button
        size="small"
        variant="outlined"
        startIcon={<FileUploadIcon />}
        onClick={() => fileInputRef.current?.click()}
        disabled={smoothed}
      >
        Import
      </Button>
      <input
        ref={fileInputRef}
        type="file"
        accept=".hrz,.txt,.csv"
        hidden
        onChange={handleFileSelected}
      />

      <Button
        size="small"
        variant="outlined"
        startIcon={<FileDownloadIcon />}
        endIcon={<KeyboardArrowDownIcon />}
        disabled={!canExport}
        onClick={(e) => setExportAnchor(e.currentTarget)}
      >
        Export
      </Button>
      <Menu
        anchorEl={exportAnchor}
        open={Boolean(exportAnchor)}
        onClose={() => setExportAnchor(null)}
      >
        <MenuItem onClick={() => handleExportPick("nina")}>
          N.I.N.A. .hrz (also APCC, Telescopius)
        </MenuItem>
        <MenuItem onClick={() => handleExportPick("stellarium")}>
          Stellarium landscape (.zip)
        </MenuItem>
        <MenuItem onClick={() => handleExportPick("csv")}>CSV</MenuItem>
      </Menu>

      <Button
        size="small"
        variant="outlined"
        startIcon={<CompressIcon />}
        onClick={onReduce}
        disabled={smoothed || !canReduce}
      >
        Reduce&hellip;
      </Button>

      {referenceCount > 0 ? (
        <Chip
          icon={<LayersIcon />}
          label={`Tracing (${referenceCount} pts)`}
          onDelete={onClearReference}
          color="primary"
          variant="outlined"
          size="small"
          disabled={smoothed}
        />
      ) : (
        <Button
          size="small"
          variant="outlined"
          startIcon={<LayersIcon />}
          onClick={onUseAsReference}
          disabled={smoothed || pointCount < 2}
        >
          Trace from current
        </Button>
      )}

      <Button
        size="small"
        variant="outlined"
        startIcon={<RestartAltIcon />}
        onClick={onReset}
        disabled={smoothed}
      >
        Clear
      </Button>

      <ButtonGroup size="small" variant="outlined">
        <Tooltip title={"Undo (\u2318 Z)"}>
          <span>
            <IconButton size="small" onClick={onUndo} disabled={smoothed || !canUndo}>
              <UndoIcon fontSize="small" />
            </IconButton>
          </span>
        </Tooltip>
        <Tooltip title={"Redo (\u2318 \u21E7 Z)"}>
          <span>
            <IconButton size="small" onClick={onRedo} disabled={smoothed || !canRedo}>
              <RedoIcon fontSize="small" />
            </IconButton>
          </span>
        </Tooltip>
      </ButtonGroup>

      <ToggleButton
        size="small"
        value="smoothed"
        selected={smoothed}
        onChange={() => onSmoothedChange(!smoothed)}
        aria-label="Preview as smooth spline"
      >
        <AutoGraphIcon fontSize="small" sx={{ mr: 0.5 }} />
        Smooth
      </ToggleButton>

      <ToggleButton
        size="small"
        value="original"
        selected={showOriginal}
        onChange={() => onShowOriginalChange(!showOriginal)}
        disabled={!canShowOriginal}
        aria-label="Overlay original-as-loaded horizon for comparison"
      >
        <CompareArrowsIcon fontSize="small" sx={{ mr: 0.5 }} />
        Compare
      </ToggleButton>

      <ToggleButtonGroup
        size="small"
        exclusive
        value={altitudeRange}
        onChange={(_, v) => v && onAltitudeRangeChange(v)}
      >
        <ToggleButton value="fit">Fit</ToggleButton>
        <ToggleButton value="0-90">0&ndash;90&deg;</ToggleButton>
      </ToggleButtonGroup>

      <Typography variant="caption" color="text.secondary" sx={{ ml: "auto" }}>
        {pointCount} points
      </Typography>
    </Stack>
  );
}
