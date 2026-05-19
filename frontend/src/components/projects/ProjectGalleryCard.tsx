import Box from "@mui/material/Box";
import Card from "@mui/material/Card";
import CardActionArea from "@mui/material/CardActionArea";
import CardContent from "@mui/material/CardContent";
import Chip from "@mui/material/Chip";
import Typography from "@mui/material/Typography";
import CollectionsIcon from "@mui/icons-material/Collections";
import { useNavigate } from "react-router-dom";
import type { ProjectListItem } from "@/api/projects";
import { projectThumbnailUrl, PROJECT_STATUS_COLORS } from "@/api/projects";

interface Props {
  project: ProjectListItem;
}

export default function ProjectGalleryCard({ project }: Props) {
  const navigate = useNavigate();

  return (
    <Card variant="outlined" sx={{ opacity: project.active ? 1 : 0.5 }}>
      <CardActionArea onClick={() => navigate(`/projects/${project.id}`)}>
        <Box
          sx={{
            position: "relative",
            width: "100%",
            aspectRatio: "4 / 3",
            bgcolor: "action.hover",
            overflow: "hidden",
          }}
        >
          {project.main_image_path ? (
            <Box
              component="img"
              src={projectThumbnailUrl(project.id, "large", project.updated_at)}
              alt=""
              sx={{
                position: "absolute",
                inset: 0,
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
            <CollectionsIcon
              sx={{
                position: "absolute",
                top: "50%",
                left: "50%",
                transform: "translate(-50%, -50%)",
                fontSize: 40,
                opacity: 0.3,
              }}
            />
          )}
        </Box>
        <CardContent sx={{ py: 1, px: 1.5, "&:last-child": { pb: 1 } }}>
          <Typography variant="subtitle2" noWrap fontWeight={600}>
            {project.name}
          </Typography>
          <Box sx={{ display: "flex", alignItems: "center", gap: 1, mt: 0.25 }}>
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
        </CardContent>
      </CardActionArea>
    </Card>
  );
}
