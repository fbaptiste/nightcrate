import Box from "@mui/material/Box";
import Typography from "@mui/material/Typography";
import { Link } from "react-router-dom";
import type { RecentProject } from "@/api/home";
import { projectThumbnailUrl } from "@/api/projects";
import FilterSwatch from "@/components/projects/FilterSwatch";
import { formatHoursMinutes } from "@/components/projects/IntegrationBars";
import { notRecordedFilter, resolveFilterLabel } from "@/components/projects/filterColors";
import { displayConstellation } from "@/lib/constellations";
import { formatDate, STAGE_LABELS } from "@/lib/home";
import { stageAppearance } from "./stageAppearance";

function targetLine(project: RecentProject): string | null {
  if (!project.target_label) return null;
  return project.constellation
    ? `${project.target_label} in ${displayConstellation(project.constellation)}`
    : project.target_label;
}

export function RecentProjects({
  projects,
  workspaceKey,
}: {
  projects: RecentProject[];
  workspaceKey: string;
}) {
  return (
    <Box component="section" sx={{ mt: "34px" }}>
      <Typography component="h2" sx={{ fontSize: 16, fontWeight: 600 }}>
        Recent projects
        <Typography component="span" sx={{ ml: 1, color: "text.secondary", fontSize: 13 }}>
          by last night imaged
        </Typography>
      </Typography>
      {projects.length === 0 ? (
        <Typography sx={{ mt: "12px", color: "text.secondary", fontSize: 14 }}>
          Nothing imaged yet. Projects you capture data for show up here.
        </Typography>
      ) : (
        <Box sx={{ display: "grid", gridTemplateColumns: "1fr", gap: "20px", mt: "12px", "@media (min-width: 1000px)": { gridTemplateColumns: "repeat(3, minmax(0, 1fr))" } }}>
          {projects.map((project) => {
            const maximum = Math.max(1, ...project.lines.map((line) => line.minutes));
            const target = targetLine(project);
            return (
              <Box
                component={Link}
                to={`/projects/${project.project_id}`}
                key={project.project_id}
                sx={{ display: "flex", flexDirection: "column", overflow: "hidden", color: "inherit", textDecoration: "none", bgcolor: "background.paper", border: 1, borderColor: "divider", borderRadius: "10px", "&:hover": { borderColor: "text.secondary" } }}
              >
                <Box sx={{ position: "relative", overflow: "hidden", height: 150, flexShrink: 0, bgcolor: "#0b0d12", display: "grid", placeItems: "center", color: "#8e8c88", fontSize: 13 }}>
                  {project.has_image ? (
                    <Box
                      component="img"
                      src={projectThumbnailUrl(project.project_id, "medium", project.thumbnail_version, workspaceKey)}
                      alt=""
                      sx={{ position: "absolute", inset: 0, display: "block", width: "100%", height: "100%", objectFit: "cover" }}
                    />
                  ) : "No picture yet"}
                </Box>
                <Box sx={{ p: "12px 14px 14px" }}>
                  <Box sx={{ display: "flex", alignItems: "center", gap: 1, flexWrap: "wrap", fontSize: 15, fontWeight: 600 }}>
                    {project.name}
                    <Box component="span" sx={[{ px: 1, py: "1px", borderRadius: "10px", fontSize: 12, fontWeight: 600 }, stageAppearance(project.stage)]}>
                      {STAGE_LABELS[project.stage]}
                    </Box>
                  </Box>
                  {target && <Typography sx={{ color: "text.secondary", fontSize: 13 }}>{target}</Typography>}
                  <Typography sx={{ mt: "10px", fontSize: 13 }}>
                    <Box component="strong" sx={{ fontWeight: 600 }}>{formatHoursMinutes(project.total_minutes)}</Box> collected
                  </Typography>
                  <Box sx={{ display: "grid", gridTemplateColumns: "minmax(38px, max-content) minmax(0, 1fr) auto", gap: "4px 8px", alignItems: "center", mt: "6px" }}>
                    {project.lines.map((line) => (
                      <Box key={`${line.label}:${line.not_recorded}`} sx={{ display: "contents" }}>
                        <Typography noWrap title={line.label} sx={{ minWidth: 0, maxWidth: 96, overflow: "hidden", textOverflow: "ellipsis", color: "text.secondary", fontSize: 12 }}>{line.label}</Typography>
                        <Box sx={{ height: 5, bgcolor: "action.hover", borderRadius: "3px", overflow: "hidden" }}>
                          <FilterSwatch
                            filter={line.not_recorded ? notRecordedFilter() : resolveFilterLabel(line.label)}
                            width={`${(line.minutes / maximum) * 100}%`}
                            height="100%"
                            borderRadius="3px"
                            outlineWidth={1}
                            display="block"
                          />
                        </Box>
                        <Typography sx={{ color: "text.secondary", fontSize: 12, fontVariantNumeric: "tabular-nums" }}>{formatHoursMinutes(line.minutes)}</Typography>
                      </Box>
                    ))}
                  </Box>
                  <Typography sx={{ color: "text.secondary", fontSize: "12.5px", mt: "10px" }}>
                    Last imaged {formatDate(project.last_date)}, {project.nights} {project.nights === 1 ? "night" : "nights"} so far
                  </Typography>
                </Box>
              </Box>
            );
          })}
        </Box>
      )}
    </Box>
  );
}
