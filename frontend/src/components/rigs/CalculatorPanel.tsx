import { useEffect, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import Autocomplete from "@mui/material/Autocomplete";
import Box from "@mui/material/Box";
import Tab from "@mui/material/Tab";
import Tabs from "@mui/material/Tabs";
import TextField from "@mui/material/TextField";
import Typography from "@mui/material/Typography";
import { fetchLocations, type Location } from "@/api/locations";
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
  const [selectedLocationId, setSelectedLocationId] = useState<number | null>(
    null,
  );
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

  const { data: locations = [] } = useQuery<Location[]>({
    queryKey: ["locations"],
    queryFn: fetchLocations,
  });

  // Set default location on first load
  useEffect(() => {
    if (locations.length > 0 && selectedLocationId === null) {
      const defaultLoc = locations.find((l) => l.is_default);
      if (defaultLoc) {
        setSelectedLocationId(defaultLoc.id);
      }
    }
  }, [locations, selectedLocationId]);

  const debouncedGuideBinning = useDebounce(guideBinning, 150);
  const debouncedCentroidAccuracy = useDebounce(centroidAccuracy, 300);
  const debouncedGuidingImageBinning = useDebounce(guidingImageBinning, 150);

  // Fetch calculator data when any parameter changes.
  useEffect(() => {
    if (selectedLocationId === null) return;
    let cancelled = false;
    fetchRigCalculators(rig.id, {
      location_id: selectedLocationId,
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
    selectedLocationId,
    debouncedGuideBinning,
    debouncedCentroidAccuracy,
    debouncedGuidingImageBinning,
  ]);

  const selectedLocation = locations.find((l) => l.id === selectedLocationId);
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
        <Autocomplete
          size="small"
          options={locations}
          getOptionLabel={(loc) =>
            `${loc.name}${loc.is_default ? " (default)" : ""}`
          }
          value={selectedLocation ?? null}
          onChange={(_, loc) => {
            if (loc) setSelectedLocationId(loc.id);
          }}
          renderInput={(params) => <TextField {...params} label="Location" />}
          sx={{ width: 260, flexShrink: 0, mr: 4 }}
          isOptionEqualToValue={(option, value) => option.id === value.id}
        />
      </Box>

      {/* Tabs */}
      <Box sx={{ borderBottom: 1, borderColor: "divider", mb: 2 }}>
        <Tabs
          value={activeTab}
          onChange={(_, v: TabKey) => setActiveTab(v)}
          aria-label="rig calculator tabs"
        >
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
