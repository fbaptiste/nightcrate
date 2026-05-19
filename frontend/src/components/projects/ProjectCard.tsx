import Box from "@mui/material/Box";
import Card from "@mui/material/Card";
import CardActionArea from "@mui/material/CardActionArea";
import Chip from "@mui/material/Chip";
import Typography from "@mui/material/Typography";
import CollectionsIcon from "@mui/icons-material/Collections";
import { useNavigate } from "react-router-dom";
import type { ProjectListItem } from "@/api/projects";
import { projectThumbnailUrl, PROJECT_STATUS_COLORS } from "@/api/projects";

const THUMB = 56;

interface Props {
  project: ProjectListItem;
}

export default function ProjectCard({ project }: Props) {
  const navigate = useNavigate();

  return (
    <Card variant="outlined">
      <CardActionArea
        onClick={() => navigate(`/projects/${project.id}`)}
        sx={{ display: "flex", alignItems: "center", p: 1, gap: 1.5 }}
      >
        <Box
          sx={{
            width: THUMB,
            height: THUMB,
            flexShrink: 0,
            borderRadius: 1,
            overflow: "hidden",
            bgcolor: "action.hover",
            display: "flex",
            alignItems: "center",
            justifyContent: "center",
          }}
        >
          {project.main_image_path ? (
            <Box
              component="img"
              src={projectThumbnailUrl(project.id, project.updated_at)}
              alt=""
              sx={{
                width: "100%",
                height: "100%",
                objectFit: "cover",
                display: "block",
              }}
              onError={(e) => {
                (e.target as HTMLImageElement).style.display = "none";
              }}
            />
          ) : (
            <CollectionsIcon sx={{ fontSize: 24, opacity: 0.3 }} />
          )}
        </Box>

        <Box sx={{ minWidth: 0, flexGrow: 1 }}>
          <Typography variant="subtitle2" noWrap fontWeight={600}>
            {project.name}
          </Typography>
          <Box sx={{ display: "flex", alignItems: "center", gap: 1 }}>
            {project.status !== "active" && (
              <Chip
                label={project.status}
                size="small"
                color={PROJECT_STATUS_COLORS[project.status] ?? "default"}
                sx={{ height: 18, fontSize: 11 }}
              />
            )}
            <Typography variant="caption" color="text.secondary" noWrap>
              {project.image_count} image{project.image_count !== 1 ? "s" : ""}
            </Typography>
          </Box>
        </Box>
      </CardActionArea>
    </Card>
  );
}
