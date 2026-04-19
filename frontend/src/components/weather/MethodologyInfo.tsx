import Accordion from "@mui/material/Accordion";
import AccordionSummary from "@mui/material/AccordionSummary";
import AccordionDetails from "@mui/material/AccordionDetails";
import Box from "@mui/material/Box";
import Table from "@mui/material/Table";
import TableBody from "@mui/material/TableBody";
import TableCell from "@mui/material/TableCell";
import TableHead from "@mui/material/TableHead";
import TableRow from "@mui/material/TableRow";
import Typography from "@mui/material/Typography";
import Stack from "@mui/material/Stack";
import ExpandMoreIcon from "@mui/icons-material/ExpandMore";
import InfoIcon from "@mui/icons-material/Info";
import { Inline } from "@/components/calculators/Math";

const FACTORS = [
  {
    name: "Sky Clarity",
    weightMoon: "35%",
    weightNoMoon: "40%",
    description:
      "Cloud-weighted sky openness. Low, mid, and high clouds are weighted 1.0 / 0.9 / 0.6 \u2014 thin cirrus hurts less than thick stratus. Also acts as a gating multiplier on all other factors.",
  },
  {
    name: "Seeing",
    weightMoon: "25%",
    weightNoMoon: "25%",
    description:
      "Atmospheric turbulence estimate. Uses upper-atmosphere wind shear at 200/300/500 hPa when available, surface wind/humidity/stability as fallback.",
  },
  {
    name: "Transparency",
    weightMoon: "15%",
    weightNoMoon: "25%",
    description:
      "Total-column water vapor (PWV), aerosol optical depth (wildfire smoke, dust, pollution), surface humidity, and visibility combined. Lower PWV and AOD = better narrowband and broadband transparency.",
  },
  {
    name: "Moon",
    weightMoon: "15%",
    weightNoMoon: "n/a",
    description:
      "Penalty based on how long the moon is above the horizon during darkness and how bright it is. Disable for narrowband imaging.",
  },
  {
    name: "Wind Calm",
    weightMoon: "10%",
    weightNoMoon: "10%",
    description: "Surface wind penalty. Calm (< 5 km/h) is ideal; strong wind (> 25 km/h) scores poorly.",
  },
];

const LABELS = [
  { range: "80 \u2013 100", label: "Excellent" },
  { range: "55 \u2013 79", label: "Good" },
  { range: "30 \u2013 54", label: "Marginal" },
  { range: "0 \u2013 29", label: "Poor" },
];

const DEW_RISK_ITEMS = [
  { label: "Low", description: "spread > 5 \u00b0C" },
  { label: "Moderate", description: "spread 3\u20135 \u00b0C" },
  { label: "High", description: "spread 1\u20133 \u00b0C (dew heaters recommended)" },
  { label: "Critical", description: "spread < 1 \u00b0C (active dew formation likely)" },
];

const cellSx = { py: 0.5, px: 1, fontSize: "0.8rem" };
const headerSx = { ...cellSx, fontWeight: 600 };

export default function MethodologyInfo() {
  return (
    <Accordion
      disableGutters
      elevation={0}
      sx={{
        maxWidth: 720,
        background: "transparent",
        "&::before": { display: "none" },
      }}
    >
      <AccordionSummary
        expandIcon={<ExpandMoreIcon />}
        sx={{ "& .MuiAccordionSummary-content": { flexGrow: 0 } }}
      >
        <Stack direction="row" alignItems="center" spacing={1}>
          <InfoIcon fontSize="small" color="action" />
          <Typography variant="body2" color="text.secondary">
            How are scores calculated?
          </Typography>
        </Stack>
      </AccordionSummary>
      <AccordionDetails>
        <Box>
          <Typography variant="body2" color="text.secondary" sx={{ mb: 2 }}>
            The imaging quality score (0&ndash;100) rates each night&rsquo;s suitability for
            deep-sky imaging. Higher is always better. Sky clarity acts as a cloud gating
            factor &mdash; heavy clouds suppress the contribution of all other factors.
          </Typography>

          <Typography variant="subtitle2" sx={{ mb: 0.5 }}>
            Factors &amp; Weights
          </Typography>
          <Table size="small" sx={{ mb: 2 }}>
            <TableHead>
              <TableRow>
                <TableCell sx={headerSx}>Factor</TableCell>
                <TableCell sx={headerSx} align="center">Weight</TableCell>
                <TableCell sx={headerSx} align="center">No Moon</TableCell>
                <TableCell sx={headerSx}>Description</TableCell>
              </TableRow>
            </TableHead>
            <TableBody>
              {FACTORS.map((f) => (
                <TableRow key={f.name}>
                  <TableCell sx={cellSx}>{f.name}</TableCell>
                  <TableCell sx={cellSx} align="center">{f.weightMoon}</TableCell>
                  <TableCell sx={cellSx} align="center">{f.weightNoMoon}</TableCell>
                  <TableCell sx={cellSx}>{f.description}</TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>

          <Typography variant="subtitle2" sx={{ mb: 0.5 }}>
            Cloud Gating
          </Typography>
          <Typography variant="body2" color="text.secondary" sx={{ mb: 2 }}>
            Other factors are multiplied by{" "}
            <Inline>{String.raw`\sqrt{\text{sky clarity} / 100}`}</Inline>. At
            50% cloud cover, other factors contribute 71% of their normal
            weight. At 90% cloud cover, 32%. At 100% cloud, 0. Perfect seeing
            can&rsquo;t save a cloudy night.
          </Typography>

          <Typography variant="subtitle2" sx={{ mb: 0.5 }}>
            Quality Labels
          </Typography>
          <Table size="small" sx={{ mb: 2, maxWidth: 220 }}>
            <TableHead>
              <TableRow>
                <TableCell sx={headerSx}>Score</TableCell>
                <TableCell sx={headerSx}>Label</TableCell>
              </TableRow>
            </TableHead>
            <TableBody>
              {LABELS.map((l) => (
                <TableRow key={l.label}>
                  <TableCell sx={cellSx}>{l.range}</TableCell>
                  <TableCell sx={cellSx}>{l.label}</TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>

          <Typography variant="subtitle2" sx={{ mb: 0.5 }}>
            Dew Risk
          </Typography>
          <Typography variant="body2" color="text.secondary" sx={{ mb: 1 }}>
            Classified from temperature minus dew point spread:
          </Typography>
          <Box component="ul" sx={{ mt: 0, mb: 2, pl: 2 }}>
            {DEW_RISK_ITEMS.map((item) => (
              <Typography
                key={item.label}
                component="li"
                variant="body2"
                color="text.secondary"
                sx={{ fontSize: "0.8rem" }}
              >
                <strong>{item.label}:</strong> {item.description}
              </Typography>
            ))}
          </Box>
          <Typography variant="body2" color="text.secondary" sx={{ mb: 2 }}>
            The &ldquo;Dew-safe&rdquo; line on daily cards reports when the spread stays
            above 3 &deg;C during darkness.
          </Typography>

          <Typography variant="caption" color="text.secondary">
            Data: Open-Meteo (weather, free API) &bull; Open-Meteo Air Quality API, CAMS
            Global (AOD) &bull; astropy (moon, twilight, elongation) &bull;
            Seeing model: Trinquet &amp; Vernin 2006, Cherubini &amp; Businger 2013
          </Typography>
        </Box>
      </AccordionDetails>
    </Accordion>
  );
}
