import { useQuery } from "@tanstack/react-query";
import Alert from "@mui/material/Alert";
import Box from "@mui/material/Box";
import CircularProgress from "@mui/material/CircularProgress";
import Typography from "@mui/material/Typography";
import { fetchHome } from "@/api/home";
import { FortnightForecast } from "@/components/home/FortnightForecast";
import { LatestAndYear } from "@/components/home/LatestAndYear";
import { RecentProjects } from "@/components/home/RecentProjects";
import { StageOverview } from "@/components/home/StageOverview";
import { SummaryPanels } from "@/components/home/SummaryPanels";
import { formatDate } from "@/lib/home";

export function HomePage() {
  const home = useQuery({
    queryKey: ["home"],
    queryFn: fetchHome,
    staleTime: 0,
  });

  if (home.isPending) {
    return (
      <Box sx={{ display: "grid", placeItems: "center", flexGrow: 1 }}>
        <CircularProgress size={28} aria-label="Loading Home" />
      </Box>
    );
  }

  if (home.isError) {
    return (
      <Box sx={{ p: "30px 36px" }}>
        <Alert severity="error">Couldn't load Home.</Alert>
      </Box>
    );
  }

  const summary = home.data;
  return (
    <Box sx={{ p: "30px 36px 48px", minWidth: 0 }}>
      <Box sx={{ maxWidth: 1180 }}>
        <Typography sx={{ color: "text.secondary", fontSize: 14, mb: "6px" }}>
          {formatDate(summary.today, {
            weekday: "long",
            day: "numeric",
            month: "long",
          })}
        </Typography>
        <Typography component="h1" sx={{ m: 0, fontSize: 28, lineHeight: 1.22, fontWeight: 600, letterSpacing: "-0.012em" }}>
          Projects
          <Typography component="span" sx={{ ml: "10px", color: "text.secondary", fontSize: 16, fontWeight: 400, letterSpacing: 0 }}>
            {summary.total_projects} in all
          </Typography>
        </Typography>
        <StageOverview stages={summary.stages} total={summary.total_projects} />
        <RecentProjects projects={summary.recent} workspaceKey={summary.workspace_key} />
        <FortnightForecast locations={summary.forecast_locations} />
        <LatestAndYear
          picture={summary.latest_picture}
          year={summary.year}
          workspaceKey={summary.workspace_key}
        />
        <SummaryPanels rigs={summary.rigs} locations={summary.locations} />
      </Box>
    </Box>
  );
}
