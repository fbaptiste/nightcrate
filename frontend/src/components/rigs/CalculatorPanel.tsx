import { useEffect, useState } from "react";
import Box from "@mui/material/Box";
import Tab from "@mui/material/Tab";
import Tabs from "@mui/material/Tabs";
import Typography from "@mui/material/Typography";
import {
  fetchRigCalculators,
  type Rig,
  type RigCalculators,
} from "@/api/rigs";
import { useDebounce } from "@/lib/useDebounce";
import EquipmentTab from "./EquipmentTab";
import ImagingTab from "./ImagingTab";
import GuidingTab from "./GuidingTab";

interface CalculatorPanelProps {
  rig: Rig;
}

type TabKey = "equipment" | "imaging" | "guiding";

const TAB_ORDER: TabKey[] = ["equipment", "imaging", "guiding"];

export default function CalculatorPanel({ rig }: CalculatorPanelProps) {
  const [guideBinning, setGuideBinning] = useState<number>(1);
  const [centroidAccuracy, setCentroidAccuracy] = useState<number>(0.2);
  // Image binning on the Guiding tab — drives the guiding-tolerance
  // thresholds on the backend. Independent from the Imaging tab's own
  // (purely display-side) binning selector.
  const [guidingImageBinning, setGuidingImageBinning] = useState<number>(1);
  // Fetched calculator data keyed by rig.id; falls back to rig.calculators
  // (the snapshot included on the rig list response) until a fetch resolves.
  // Keying by rig.id ensures the fallback resets cleanly when the user
  // switches between rigs.
  const [fetched, setFetched] = useState<{ rigId: number; data: RigCalculators } | null>(
    null,
  );
  const calculatorData: RigCalculators =
    fetched?.rigId === rig.id ? fetched.data : rig.calculators;
  const [activeTab, setActiveTab] = useState<TabKey>("equipment");


  const debouncedGuideBinning = useDebounce(guideBinning, 150);
  const debouncedCentroidAccuracy = useDebounce(centroidAccuracy, 300);
  const debouncedGuidingImageBinning = useDebounce(guidingImageBinning, 150);

  // Fetch calculator data when any parameter changes.
  useEffect(() => {
    let cancelled = false;
    // No location is passed: a rig has no location, and the one thing seeing
    // was needed for is set directly by the Imaging tab's seeing slider. The
    // backend's own 2-4" default seeds that slider's starting position.
    fetchRigCalculators(rig.id, {
      guide_binning: debouncedGuideBinning,
      centroid_accuracy_pixels: debouncedCentroidAccuracy,
      image_binning: debouncedGuidingImageBinning,
    }).then((data) => {
      if (!cancelled) setFetched({ rigId: rig.id, data });
    });
    return () => {
      cancelled = true;
    };
  }, [
    rig.id,
    debouncedGuideBinning,
    debouncedCentroidAccuracy,
    debouncedGuidingImageBinning,
  ]);

  const hasGuideCamera = rig.guide_camera_id != null;

  return (
    <Box>
      {/* Header row: rig name + location selector */}
      <Box
        sx={{
          display: "flex",
          alignItems: "center",
          gap: 2,
          mb: 1.5,
          flexWrap: "wrap",
        }}
      >
        <Typography variant="h6" sx={{ flex: "1 1 auto", minWidth: 200 }}>
          {rig.name}
        </Typography>
      </Box>

      {/* Tabs */}
      <Box sx={{ borderBottom: 1, borderColor: "divider", mb: 2 }}>
        <Tabs
          value={activeTab}
          onChange={(_, v: TabKey) => setActiveTab(v)}
          aria-label="rig calculator tabs"
        >
          {/* Tabs styles its children by cloning them, so a Tab must stay a
              direct child — wrapping one (in a Tooltip, say) silently costs it
              the disabled colour and it renders as bright as an active tab. */}
          {TAB_ORDER.map((key) => (
            <Tab
              key={key}
              value={key}
              label={TAB_LABELS[key]}
              disabled={key === "guiding" && !hasGuideCamera}
            />
          ))}
        </Tabs>
      </Box>

      {/* Tab body */}
      {activeTab === "equipment" && <EquipmentTab rig={rig} />}
      {activeTab === "imaging" && <ImagingTab calculators={calculatorData} />}
      {activeTab === "guiding" && hasGuideCamera && (
        <GuidingTab
          rig={rig}
          calculators={calculatorData}
          guideBinning={guideBinning}
          onGuideBinningChange={setGuideBinning}
          imageBinning={guidingImageBinning}
          onImageBinningChange={setGuidingImageBinning}
          centroidAccuracy={centroidAccuracy}
          onCentroidChange={setCentroidAccuracy}
        />
      )}
    </Box>
  );
}

const TAB_LABELS: Record<TabKey, string> = {
  equipment: "Equipment",
  imaging: "Imaging",
  guiding: "Guiding",
};
