import Box from "@mui/material/Box";
import Typography from "@mui/material/Typography";
import type { AnalysisResult } from "@/api/aberration";
import { SidebarSection } from "@/components/SidebarSection";
import { monoFontFamily } from "@/theme/theme";

function StatRow({ label, value }: { label: string; value: string }) {
  return (
    <>
      <Typography sx={{ fontSize: "inherit", fontFamily: "inherit", color: "text.secondary" }}>{label}</Typography>
      <Typography sx={{ fontSize: "inherit", fontFamily: "inherit" }}>{value}</Typography>
    </>
  );
}

function rangeStr(values: number[], decimals: number): string {
  if (values.length === 0) return "—";
  const min = Math.min(...values);
  const max = Math.max(...values);
  return `${min.toFixed(decimals)} – ${max.toFixed(decimals)}`;
}

interface Props {
  analysis: AnalysisResult | null;
}

export function AberrationSidebar({ analysis }: Props) {
  if (!analysis) {
    return (
      <Box sx={{ p: 1.5 }}>
        <Typography variant="caption" color="text.secondary" sx={{ fontSize: "0.65rem" }}>
          Open an image and switch to the Aberration tab to analyze star shapes.
        </Typography>
      </Box>
    );
  }

  const stars = analysis.stars;
  const fwhms = stars.map((s) => s.fwhm);
  const eccs = stars.map((s) => s.eccentricity);
  const hfrs = stars.map((s) => s.hfr);
  const snrs = stars.map((s) => s.snr);

  return (
    <Box sx={{ display: "flex", flexDirection: "column", flexGrow: 1, overflowY: "auto" }}>
      <SidebarSection label="Global Stats">
        <Box sx={{ px: 1.5, display: "grid", gridTemplateColumns: "auto 1fr", columnGap: 1, rowGap: 0.125, fontSize: "0.65rem", fontFamily: monoFontFamily }}>
          <StatRow label="Stars" value={String(analysis.star_count)} />
          <StatRow label="Med FWHM" value={analysis.median_fwhm?.toFixed(2) ?? "—"} />
          <StatRow label="FWHM range" value={rangeStr(fwhms, 2)} />
          <StatRow label="Med Ecc" value={analysis.median_eccentricity?.toFixed(3) ?? "—"} />
          <StatRow label="Ecc range" value={rangeStr(eccs, 3)} />
          <StatRow label="Med HFR" value={analysis.median_hfr?.toFixed(2) ?? "—"} />
          <StatRow label="HFR range" value={rangeStr(hfrs, 2)} />
          <StatRow label="SNR range" value={rangeStr(snrs, 0)} />
        </Box>
      </SidebarSection>

      {/* Spacer */}
      <Box sx={{ flexGrow: 1 }} />

      <SidebarSection label="Help" defaultOpen={false}>
        <Box sx={{ px: 1.5, pb: 1.5 }}>
          <Typography variant="caption" color="text.secondary" sx={{ fontSize: "0.6rem", fontWeight: 600, display: "block", mb: 0.25 }}>
            Grid View
          </Typography>
          <Box component="ul" sx={{ m: 0, pl: 2, fontSize: "0.6rem", color: "text.secondary", lineHeight: 1.8, mb: 1 }}>
            <li>Click a tile to open the preview</li>
            <li>Drag squares on the thumbnail to reposition</li>
            <li>Reset button appears when squares are moved</li>
          </Box>
          <Typography variant="caption" color="text.secondary" sx={{ fontSize: "0.6rem", fontWeight: 600, display: "block", mb: 0.25 }}>
            Tile Preview
          </Typography>
          <Box component="ul" sx={{ m: 0, pl: 2, fontSize: "0.6rem", color: "text.secondary", lineHeight: 1.8 }}>
            <li>Toggle star markers with the circle button</li>
            <li>Hover a star ellipse for detailed metrics</li>
            <li>Click backdrop or X to close</li>
          </Box>
        </Box>
      </SidebarSection>
    </Box>
  );
}
