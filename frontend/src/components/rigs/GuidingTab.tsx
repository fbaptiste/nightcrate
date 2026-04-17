import Box from "@mui/material/Box";
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

export default function GuidingTab({
  rig,
  calculators,
  guideBinning,
  onBinningChange,
  centroidAccuracy,
  onCentroidChange,
}: GuidingTabProps) {
  return (
    <Box>
      <GuideSuitabilityPanel
        rig={rig}
        suitability={calculators.guide_suitability}
        mainImageScale={calculators.image_scale_arcsec_per_pixel}
        guideBinning={guideBinning}
        onBinningChange={onBinningChange}
        centroidAccuracy={centroidAccuracy}
        onCentroidChange={onCentroidChange}
      />
      {calculators.guiding_tolerance && (
        <GuidingTolerancePanel tolerance={calculators.guiding_tolerance} />
      )}
    </Box>
  );
}
