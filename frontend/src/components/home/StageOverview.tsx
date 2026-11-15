import Box from "@mui/material/Box";
import MuiLink from "@mui/material/Link";
import Tooltip from "@mui/material/Tooltip";
import Typography from "@mui/material/Typography";
import { Link as RouterLink } from "react-router-dom";
import type { StageCounts } from "@/api/home";
import {
  STAGE_LABELS,
  STAGE_ORDER,
  stageSegments,
} from "@/lib/home";
import { stageAppearance } from "./stageAppearance";

export function StageOverview({ stages, total }: { stages: StageCounts; total: number }) {
  if (total === 0) {
    return (
      <Box sx={{ mt: "18px", color: "text.secondary", fontSize: 14 }}>
        No projects yet.{" "}
        <MuiLink component={RouterLink} to="/projects" color="primary.main">
          Create a project
        </MuiLink>
      </Box>
    );
  }

  return (
    <>
      <Box
        component="nav"
        role="list"
        aria-label="Projects by stage"
        sx={{ display: "flex", height: 40, borderRadius: "8px", overflow: "hidden", mt: "18px", gap: "2px" }}
      >
        {stageSegments(stages).map((stage) => (
          <Box
            key={stage.key}
            role="listitem"
            sx={{ display: "flex", flex: stage.count, minWidth: 34 }}
          >
            <Tooltip
              title={`${stage.label}: ${stage.count}. ${stage.description}.`}
              arrow
            >
              <Box
                component={RouterLink}
                aria-label={`${stage.label}: ${stage.count}`}
                to={`/projects?stage=${stage.key}`}
                sx={[
                  {
                    width: "100%",
                    px: "12px",
                    display: "flex",
                    alignItems: "center",
                    textDecoration: "none",
                    fontSize: "13.5px",
                    fontWeight: 600,
                    whiteSpace: "nowrap",
                    overflow: "hidden",
                    "&:hover": { filter: "brightness(1.08)" },
                  },
                  stageAppearance(stage.key),
                ]}
              >
                {stage.count}
              </Box>
            </Tooltip>
          </Box>
        ))}
      </Box>
      <Box sx={{ display: "flex", flexWrap: "wrap", gap: "6px 22px", mt: "10px" }}>
        {STAGE_ORDER.map((stage) => (
          <Box key={stage} sx={{ display: "inline-flex", alignItems: "center", gap: "7px", color: "text.secondary", fontSize: 13 }}>
            <Box sx={[{ width: 12, height: 12, borderRadius: "3px" }, stageAppearance(stage)]} />
            <Typography component="span" sx={{ color: "text.primary", fontWeight: 600, fontSize: "inherit" }}>
              {stages[stage]}
            </Typography>
            {STAGE_LABELS[stage].toLocaleLowerCase()}
          </Box>
        ))}
      </Box>
    </>
  );
}
