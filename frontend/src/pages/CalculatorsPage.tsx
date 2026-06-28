import { useEffect } from "react";
import { useNavigate, useParams } from "react-router-dom";
import Box from "@mui/material/Box";
import Typography from "@mui/material/Typography";
import CalculatorSidebar, {
  ALL_CALC_IDS,
  isLocationAware,
} from "@/components/calculators/CalculatorSidebar";
import CalculatorLocationBar from "@/components/calculators/CalculatorLocationBar";
import LatLongCalc from "@/components/calculators/LatLongCalc";
import RaDecAltAzCalc from "@/components/calculators/RaDecAltAzCalc";
import ClocksCalc from "@/components/calculators/ClocksCalc";
import AngularUnitsCalc from "@/components/calculators/AngularUnitsCalc";
import LinearUnitsCalc from "@/components/calculators/LinearUnitsCalc";
import PixelScaleCalc from "@/components/calculators/PixelScaleCalc";
import FieldOfViewCalc from "@/components/calculators/FieldOfViewCalc";
import FileSizeCalc from "@/components/calculators/FileSizeCalc";
import AirmassCalc from "@/components/calculators/AirmassCalc";
import SqmBortleCalc from "@/components/calculators/SqmBortleCalc";
import TemperatureCalc from "@/components/calculators/TemperatureCalc";
import MoonAltitudeCalc from "@/components/calculators/MoonAltitudeCalc";

const DEFAULT_CALC = "lat-long";

function renderCalculator(calcId: string) {
  switch (calcId) {
    case "lat-long":
      return <LatLongCalc />;
    case "radec-altaz":
      return <RaDecAltAzCalc />;
    case "clocks":
      return <ClocksCalc />;
    case "angular-units":
      return <AngularUnitsCalc />;
    case "linear-units":
      return <LinearUnitsCalc />;
    case "pixel-scale":
      return <PixelScaleCalc />;
    case "fov":
      return <FieldOfViewCalc />;
    case "file-size":
      return <FileSizeCalc />;
    case "airmass":
      return <AirmassCalc />;
    case "moon-altitude":
      return <MoonAltitudeCalc />;
    case "sqm-bortle":
      return <SqmBortleCalc />;
    case "temperature":
      return <TemperatureCalc />;
    default:
      return (
        <Typography color="text.secondary">
          Unknown calculator. Pick one from the sidebar.
        </Typography>
      );
  }
}

export default function CalculatorsPage() {
  const { calcId } = useParams();
  const navigate = useNavigate();
  const active = calcId && ALL_CALC_IDS.includes(calcId) ? calcId : DEFAULT_CALC;

  // Redirect bare `/calculators` to the default calculator for a stable URL.
  useEffect(() => {
    if (!calcId) {
      navigate(`/calculators/${DEFAULT_CALC}`, { replace: true });
    }
  }, [calcId, navigate]);

  const showLocationBar = isLocationAware(active);

  return (
    <Box sx={{ display: "flex", height: "100%" }}>
      <CalculatorSidebar
        selected={active}
        onSelect={(id) => navigate(`/calculators/${id}`)}
      />
      <Box sx={{ flex: 1, overflow: "auto", p: 3 }}>
        {showLocationBar && <CalculatorLocationBar />}
        {renderCalculator(active)}
      </Box>
    </Box>
  );
}
