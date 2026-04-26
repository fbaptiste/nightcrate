import Box from "@mui/material/Box";
import CalculatorLocationBar from "@/components/calculators/CalculatorLocationBar";
import TonightCalc from "@/components/calculators/TonightCalc";

export default function TonightPage() {
  return (
    <Box sx={{ p: 3, height: "100%", overflow: "auto" }}>
      <CalculatorLocationBar />
      <TonightCalc />
    </Box>
  );
}
