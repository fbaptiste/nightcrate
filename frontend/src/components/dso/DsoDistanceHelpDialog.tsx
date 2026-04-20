/**
 * Help dialog explaining how NightCrate computes DSO distances.
 *
 * Surfaces the three distance methods (curated, 50 MGC, redshift-derived)
 * with the underlying math rendered via KaTeX, plus caveats for the
 * redshift-derived values (peculiar velocities, H₀ uncertainty, no
 * relativistic correction).
 */
import Box from "@mui/material/Box";
import Dialog from "@mui/material/Dialog";
import DialogContent from "@mui/material/DialogContent";
import DialogTitle from "@mui/material/DialogTitle";
import IconButton from "@mui/material/IconButton";
import Typography from "@mui/material/Typography";
import CloseIcon from "@mui/icons-material/Close";
import { Block, Inline } from "@/components/calculators/Math";

interface Props {
  open: boolean;
  onClose: () => void;
}

export default function DsoDistanceHelpDialog({ open, onClose }: Props) {
  return (
    <Dialog open={open} onClose={onClose} fullWidth maxWidth="md">
      <DialogTitle sx={{ display: "flex", alignItems: "center" }}>
        <Box sx={{ flex: 1 }}>How distances are computed</Box>
        <IconButton onClick={onClose} size="small">
          <CloseIcon />
        </IconButton>
      </DialogTitle>
      <DialogContent dividers>
        <Typography variant="body2" sx={{ mb: 2 }}>
          NightCrate uses three sources for deep-sky object distances, in
          priority order.
        </Typography>

        <Typography variant="subtitle1" fontWeight={600} sx={{ mt: 2 }}>
          1. Curated — authoritative hand-picked values
        </Typography>
        <Typography variant="body2" sx={{ mb: 2 }}>
          For iconic targets where NightCrate ships a curated distance
          (Orion Nebula, Helix, etc.), the curated value is used directly.
          Source and uncertainty are documented in the augmentation CSV notes.
        </Typography>

        <Typography variant="subtitle1" fontWeight={600} sx={{ mt: 2 }}>
          2. 50 MGC — homogenized distances for nearby galaxies
        </Typography>
        <Typography variant="body2" sx={{ mb: 1 }}>
          For galaxies within ~50 Mpc, NightCrate uses the{" "}
          <em>50 Mpc Galaxy Catalog</em> (Ohlson et al. 2024), which
          homogenizes distances from multiple methods (Cepheid variables,
          tip of the red giant branch, surface brightness fluctuations,
          Tully-Fisher, flow-corrected redshifts).
        </Typography>
        <Typography variant="body2" sx={{ mb: 2 }}>
          Note that ~83% of 50 MGC entries are themselves flow-corrected
          redshift distances — only a few hundred galaxies have truly
          independent primary-distance measurements (Cepheids, TRGB, SBF).
          50 MGC values are still preferred over NightCrate's own
          redshift-derived distances (method 3 below) because the authors
          apply a flow-field correction; NightCrate's fallback applies
          Hubble's law directly to the OpenNGC redshift.
        </Typography>

        <Typography variant="subtitle1" fontWeight={600} sx={{ mt: 2 }}>
          3. Redshift-derived — approximate distances via Hubble's law
        </Typography>
        <Typography variant="body2">
          For galaxies without a measured distance but with a known redshift
          (from OpenNGC), NightCrate computes an approximate distance using
          Hubble's law:
        </Typography>
        <Block>{String.raw`d = \frac{c \cdot z}{H_0}`}</Block>
        <Typography variant="body2">where:</Typography>
        <Typography variant="body2" component="div" sx={{ pl: 2 }}>
          <Inline>{String.raw`c = 299{,}792.458 \text{ km/s}`}</Inline> (the
          speed of light)
          <br />
          <Inline>{String.raw`z`}</Inline> is the object's redshift
          <br />
          <Inline>{String.raw`H_0 = 70 \text{ km/s/Mpc}`}</Inline> (the Hubble
          constant)
        </Typography>
        <Typography variant="body2" sx={{ mt: 1.5 }}>
          For example, a galaxy at redshift{" "}
          <Inline>{String.raw`z = 0.02`}</Inline>:
        </Typography>
        <Block>
          {String.raw`d = \frac{299{,}792.458 \times 0.02}{70} \approx 85.7 \text{ Mpc} \approx 280 \text{ Mly}`}
        </Block>

        <Typography variant="subtitle2" fontWeight={600} sx={{ mt: 2 }}>
          Caveats on redshift-derived distances
        </Typography>
        <Box component="ul" sx={{ pl: 3, my: 1, "& li": { mb: 0.75 } }}>
          <Typography component="li" variant="body2">
            <strong>Peculiar velocities.</strong> Every galaxy has random
            motion (~hundreds of km/s) on top of the cosmic expansion. At low
            redshift, this motion can dominate, making Hubble-law distances
            unreliable. Galaxies at{" "}
            <Inline>{String.raw`z < 0.01`}</Inline> can have peculiar-velocity
            errors of 30% or more.
          </Typography>
          <Typography component="li" variant="body2">
            <strong>Hubble constant uncertainty.</strong> Different measurement
            methods give <Inline>{String.raw`H_0`}</Inline> between about 67
            and 73 km/s/Mpc. NightCrate uses 70 as a middle-ground value; your
            mileage may vary.
          </Typography>
          <Typography component="li" variant="body2">
            <strong>Not relativistic.</strong> At high redshift (
            <Inline>{String.raw`z \gtrsim 0.1`}</Inline>), the simple formula
            above diverges from cosmological distance. NightCrate does not
            apply relativistic corrections; the redshift method is a coarse
            approximation.
          </Typography>
        </Box>
        <Typography variant="body2" sx={{ mt: 1.5 }}>
          For precision work — photometry, angular-size-to-physical-size
          conversions, reproducibility — prefer curated or 50 MGC values and
          flag redshift-derived values appropriately.
        </Typography>

        <Typography variant="subtitle2" fontWeight={600} sx={{ mt: 3 }}>
          Distance modulus reference
        </Typography>
        <Typography variant="body2">
          When a source provides a distance modulus{" "}
          <Inline>{String.raw`\mu`}</Inline> instead of a linear distance,
          NightCrate converts using the standard formula:
        </Typography>
        <Block>{String.raw`d_{pc} = 10^{(\mu/5) + 1}`}</Block>
      </DialogContent>
    </Dialog>
  );
}
