import { useState } from "react";
import Box from "@mui/material/Box";
import Tab from "@mui/material/Tab";
import Tabs from "@mui/material/Tabs";
import ToggleButton from "@mui/material/ToggleButton";
import ToggleButtonGroup from "@mui/material/ToggleButtonGroup";
import Typography from "@mui/material/Typography";
import type { Rig, RigCalculators } from "@/api/rigs";
import GuideSuitabilityPanel from "./GuideSuitabilityPanel";
import GuidingTolerancePanel from "./GuidingTolerancePanel";

interface GuidingTabProps {
  rig: Rig;
  calculators: RigCalculators;
  guideBinning: number;
  onGuideBinningChange: (b: number) => void;
  imageBinning: number;
  onImageBinningChange: (b: number) => void;
  centroidAccuracy: number;
  onCentroidChange: (v: number) => void;
}

type SubTab = "guide-system" | "guiding-tolerance";

export default function GuidingTab({
  rig,
  calculators,
  guideBinning,
  onGuideBinningChange,
  imageBinning,
  onImageBinningChange,
  centroidAccuracy,
  onCentroidChange,
}: GuidingTabProps) {
  const [subTab, setSubTab] = useState<SubTab>("guide-system");

  return (
    <Box>
      {/* Shared binning controls above the sub-tabs. Guide-camera binning
          drives Guide System; imaging-camera binning drives Guiding
          Tolerance. */}
      <BinningRow
        label="Guide camera binning"
        value={guideBinning}
        onChange={onGuideBinningChange}
      />
      <BinningRow
        label="Imaging camera binning"
        value={imageBinning}
        onChange={onImageBinningChange}
      />

      <Box sx={{ borderBottom: 1, borderColor: "divider", mt: 0.5, mb: 2 }}>
        <Tabs
          value={subTab}
          onChange={(_, v: SubTab) => setSubTab(v)}
          aria-label="guiding calculator sub-tabs"
        >
          <Tab value="guide-system" label="Guide System" />
          <Tab value="guiding-tolerance" label="Guiding Tolerance" />
        </Tabs>
      </Box>

      {subTab === "guide-system" && (
        <GuideSuitabilityPanel
          rig={rig}
          suitability={calculators.guide_suitability}
          mainImageScale={calculators.image_scale_arcsec_per_pixel}
          centroidAccuracy={centroidAccuracy}
          onCentroidChange={onCentroidChange}
        />
      )}
      {subTab === "guiding-tolerance" && calculators.guiding_tolerance && (
        <GuidingTolerancePanel tolerance={calculators.guiding_tolerance} />
      )}
    </Box>
  );
}

function BinningRow({
  label,
  value,
  onChange,
}: {
  label: string;
  value: number;
  onChange: (b: number) => void;
}) {
  return (
    <Box
      sx={{
        display: "flex",
        alignItems: "center",
        gap: 1.5,
        mb: 1,
        flexWrap: "wrap",
      }}
    >
      <Typography
        variant="body2"
        color="text.secondary"
        sx={{ minWidth: 180 }}
      >
        {label}
      </Typography>
      <ToggleButtonGroup
        value={value}
        exclusive
        size="small"
        onChange={(_, v) => {
          if (v !== null) onChange(v);
        }}
      >
        {[1, 2, 3, 4].map((b) => (
          <ToggleButton key={b} value={b} sx={{ px: 1.5, py: 0.25 }}>
            {b}&times;{b}
          </ToggleButton>
        ))}
      </ToggleButtonGroup>
    </Box>
  );
}
