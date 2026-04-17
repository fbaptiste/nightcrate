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
  onBinningChange: (b: number) => void;
  centroidAccuracy: number;
  onCentroidChange: (v: number) => void;
}

type SubTab = "guide-system" | "guiding-tolerance";

export default function GuidingTab({
  rig,
  calculators,
  guideBinning,
  onBinningChange,
  centroidAccuracy,
  onCentroidChange,
}: GuidingTabProps) {
  const [subTab, setSubTab] = useState<SubTab>("guide-system");

  return (
    <Box>
      {/* Shared binning control, above the sub-tabs so it applies to both. */}
      <Box
        sx={{
          display: "flex",
          alignItems: "center",
          gap: 1.5,
          mb: 1.5,
          flexWrap: "wrap",
        }}
      >
        <Typography variant="body2" color="text.secondary">
          Guide camera binning
        </Typography>
        <ToggleButtonGroup
          value={guideBinning}
          exclusive
          size="small"
          onChange={(_, v) => {
            if (v !== null) onBinningChange(v);
          }}
        >
          {[1, 2, 3, 4].map((b) => (
            <ToggleButton key={b} value={b} sx={{ px: 1.5, py: 0.25 }}>
              {b}&times;{b}
            </ToggleButton>
          ))}
        </ToggleButtonGroup>
      </Box>

      <Box sx={{ borderBottom: 1, borderColor: "divider", mb: 2 }}>
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
