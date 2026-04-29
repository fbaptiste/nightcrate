import { useQuery } from "@tanstack/react-query";
import { useNavigate } from "react-router-dom";
import Box from "@mui/material/Box";
import Button from "@mui/material/Button";
import Chip from "@mui/material/Chip";
import Divider from "@mui/material/Divider";
import Stack from "@mui/material/Stack";
import Typography from "@mui/material/Typography";

import type { AnnotatedDso, ImageAnnotationResult, WcsParams } from "@/api/plateSolve";
import { fetchDso } from "@/api/dsos";
import { formatDistance } from "@/lib/distanceFormat";
import { SidebarSection } from "@/components/SidebarSection";
import { useDsoCatalogStore } from "@/stores/dsoCatalogStore";
import { monoFontFamily } from "@/theme/theme";

interface Props {
  dso: AnnotatedDso | null;
  annotationResult: ImageAnnotationResult | null;
  wcs: WcsParams | null | undefined;
}

const gridSx = {
  px: 1.5,
  py: 0.5,
  display: "grid",
  gridTemplateColumns: "auto 1fr",
  columnGap: 1,
  rowGap: 0.125,
  fontSize: "0.65rem",
  fontFamily: monoFontFamily,
} as const;

const labelCellSx = { fontSize: "inherit", fontFamily: "inherit", color: "text.secondary", whiteSpace: "nowrap" } as const;
const valueCellSx = { fontSize: "inherit", fontFamily: "inherit" } as const;

export function PlateSolveDetailPanel({ dso, annotationResult, wcs }: Props) {
  return (
    <>
      {(annotationResult || wcs) && (
        <AstrometricSolutionSection result={annotationResult} wcs={wcs ?? undefined} />
      )}
      {dso ? <DsoDetailSection dso={dso} /> : (
        <Typography variant="caption" color="text.secondary" sx={{ px: 1.5, py: 1.5, fontSize: "0.65rem", display: "block" }}>
          Click an object in the image or grid to see details.
        </Typography>
      )}
    </>
  );
}


function GridRow({ label, value }: { label: string; value: React.ReactNode }) {
  return (
    <>
      <Typography sx={labelCellSx}>{label}</Typography>
      <Typography sx={valueCellSx}>{value}</Typography>
    </>
  );
}


function AstrometricSolutionSection({ result, wcs }: { result: ImageAnnotationResult | null; wcs?: WcsParams }) {
  const centerRa = result?.center_ra_deg ?? (wcs ? wcs.crval1 : 0);
  const centerDec = result?.center_dec_deg ?? (wcs ? wcs.crval2 : 0);
  const pixelScale = result?.pixel_scale_arcsec ?? (wcs ? Math.sqrt(wcs.cd2_1 ** 2 + wcs.cd2_2 ** 2) * 3600 : null);
  const rotation = result?.rotation_deg ?? (wcs ? Math.atan2(wcs.cd2_1, wcs.cd2_2) * (180 / Math.PI) : null);
  const naxis1 = result?.wcs.naxis1 ?? wcs?.naxis1;
  const naxis2 = result?.wcs.naxis2 ?? wcs?.naxis2;

  const raH = centerRa / 15;
  const raHours = Math.floor(raH);
  const raMin = Math.floor((raH - raHours) * 60);
  const raSec = ((raH - raHours) * 60 - raMin) * 60;

  const decAbs = Math.abs(centerDec);
  const decDeg = Math.floor(decAbs);
  const decMin = Math.floor((decAbs - decDeg) * 60);
  const decSec = ((decAbs - decDeg) * 60 - decMin) * 60;
  const decSign = centerDec >= 0 ? "+" : "-";

  return (
    <SidebarSection label="Astrometric Solution">
      <Box sx={gridSx}>
        <GridRow label="Center RA" value={`${String(raHours).padStart(2, "0")}h ${String(raMin).padStart(2, "0")}m ${raSec.toFixed(1)}s`} />
        <GridRow label="Center Dec" value={`${decSign}${String(decDeg).padStart(2, "0")}° ${String(decMin).padStart(2, "0")}′ ${decSec.toFixed(1)}″`} />
        {pixelScale != null && <GridRow label="Pixel scale" value={`${pixelScale.toFixed(3)} ″/px`} />}
        {rotation != null && <GridRow label="Rotation" value={`${rotation.toFixed(2)}°`} />}
        {result && <GridRow label="FOV" value={`${result.fov_width_arcmin.toFixed(1)}′ × ${result.fov_height_arcmin.toFixed(1)}′`} />}
        {naxis1 != null && naxis2 != null && <GridRow label="Image" value={`${naxis1} × ${naxis2} px`} />}
        {result && <GridRow label="Objects" value={`${result.dsos.length}`} />}
      </Box>
    </SidebarSection>
  );
}


function DsoDetailSection({ dso }: { dso: AnnotatedDso }) {
  const navigate = useNavigate();
  const setDsoCatalogQuery = useDsoCatalogStore((s) => s.setQuery);
  const detailQuery = useQuery({
    queryKey: ["dso-detail", dso.id],
    queryFn: () => fetchDso(dso.id),
    enabled: true,
    staleTime: 5 * 60_000,
  });

  const detail = detailQuery.data;
  const dist = dso.distance_pc != null ? formatDistance(dso.distance_pc) : null;

  const designations: string[] = [];
  if (detail?.designations) {
    for (const d of detail.designations) {
      const label = `${d.catalog} ${d.identifier}`;
      if (label !== dso.primary_designation && designations.length < 6) {
        designations.push(label);
      }
    }
  }

  const refs = detail?.external_refs ?? [];

  return (
    <SidebarSection label="Selected Object">
      <Box sx={{ px: 1.5, py: 0.5 }}>
        <Typography sx={{ fontSize: "0.75rem", fontWeight: 600, mb: 0.25 }}>
          {dso.primary_designation}
        </Typography>
        {dso.common_name && (
          <Typography sx={{ fontSize: "0.65rem", color: "text.secondary", mb: 0.75 }}>
            {dso.common_name}
          </Typography>
        )}

        <Chip label={dso.type_group} size="small" variant="outlined" sx={{ mb: 1, fontSize: "0.6rem", height: 20 }} />

        <Box sx={gridSx}>
          {dso.constellation && <GridRow label="Constellation" value={dso.constellation} />}
          {dso.maj_axis_arcmin != null && (
            <GridRow
              label="Size"
              value={
                dso.min_axis_arcmin != null
                  ? `${dso.maj_axis_arcmin.toFixed(1)}′ × ${dso.min_axis_arcmin.toFixed(1)}′`
                  : `${dso.maj_axis_arcmin.toFixed(1)}′`
              }
            />
          )}
          {dso.mag_b != null && <GridRow label="B-Mag" value={dso.mag_b.toFixed(1)} />}
          {dist && <GridRow label="Distance" value={dist.compact} />}
          <GridRow label="RA" value={`${dso.ra_deg.toFixed(4)}°`} />
          <GridRow label="Dec" value={`${dso.dec_deg.toFixed(4)}°`} />
        </Box>

        {designations.length > 0 && (
          <>
            <Divider sx={{ my: 1 }} />
            <Typography sx={{ fontSize: "0.6rem", color: "text.secondary", mb: 0.5 }}>
              Also known as
            </Typography>
            <Stack direction="row" spacing={0.5} flexWrap="wrap" useFlexGap>
              {designations.map((d) => (
                <Chip key={d} label={d} size="small" variant="outlined" sx={{ fontSize: "0.6rem", height: 20 }} />
              ))}
            </Stack>
          </>
        )}

        {refs.length > 0 && (
          <>
            <Divider sx={{ my: 1 }} />
            <Stack direction="row" spacing={0.5} flexWrap="wrap" useFlexGap>
              {refs
                .filter((r) => r.provider !== "wikidata" && r.url)
                .map((r) => (
                  <Chip
                    key={`${r.provider}-${r.url}`}
                    label={r.provider}
                    size="small"
                    variant="outlined"
                    component="a"
                    href={r.url!}
                    target="_blank"
                    clickable
                    sx={{ fontSize: "0.6rem", height: 20, textTransform: "capitalize" }}
                  />
                ))}
            </Stack>
          </>
        )}

        <Divider sx={{ my: 1 }} />
        <Button
          size="small"
          variant="outlined"
          onClick={() => {
            setDsoCatalogQuery(dso.primary_designation);
            navigate("/catalog/dso");
          }}
          sx={{ textTransform: "none", fontSize: "0.65rem" }}
        >
          View in DSO Catalog
        </Button>
      </Box>
    </SidebarSection>
  );
}
