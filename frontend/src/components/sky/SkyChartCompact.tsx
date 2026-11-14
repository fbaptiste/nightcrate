import Box from "@mui/material/Box";
import Typography from "@mui/material/Typography";
import { useTheme } from "@mui/material/styles";
import type { SolveField } from "@/api/projectInfo";
import { fitConstellationView } from "@/lib/skyChart/geometry";
import { useSkyData } from "@/lib/skyChart/data";
import { SKY_PALETTES } from "@/lib/skyChart/palette";
import SkyChartCanvas from "./SkyChartCanvas";

interface Props {
  field: SolveField;
  projectId: number;
  projectName: string;
  onOpen: () => void;
}

export default function SkyChartCompact({ field, projectId, projectName, onOpen }: Props) {
  const theme = useTheme();
  const query = useSkyData();
  const sky = theme.palette.mode === "dark" ? SKY_PALETTES.night.sky : SKY_PALETTES.paper.sky;
  const boxSx = {
    width: "100%",
    "@media (max-width: 1099.95px)": { maxWidth: 480 },
    aspectRatio: "4 / 3",
    mt: "14px",
    bgcolor: sky,
  } as const;

  if (query.isPending) return <Box aria-hidden sx={boxSx} />;
  if (query.isError || !query.data) {
    return (
      <Box aria-hidden sx={{ ...boxSx, display: "grid", placeItems: "center", px: 2 }}>
        <Typography sx={{ color: "text.secondary", fontSize: 13, textAlign: "center" }}>
          The sky chart couldn&apos;t load. Reload the page to try again.
        </Typography>
      </Box>
    );
  }
  const view = fitConstellationView(
    query.data.boundaries[field.constellation] ?? [],
    [field.centre_ra_deg, field.centre_dec_deg],
    312,
    234,
  );
  return (
    <Box
      aria-hidden
      tabIndex={-1}
      onClick={onOpen}
      sx={{ ...boxSx, cursor: "pointer", overflow: "hidden" }}
    >
      <SkyChartCanvas
        data={query.data}
        view={view}
        mode="compact"
        field={field}
        projectId={projectId}
        projectName={projectName}
        canvasProps={{ style: { display: "block", width: "100%", height: "100%", pointerEvents: "none" } }}
      />
    </Box>
  );
}
