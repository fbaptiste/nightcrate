import Box from "@mui/material/Box";
import Card from "@mui/material/Card";
import CardActionArea from "@mui/material/CardActionArea";
import Chip from "@mui/material/Chip";
import Typography from "@mui/material/Typography";
import CollectionsIcon from "@mui/icons-material/Collections";
import { useNavigate } from "react-router-dom";
import type { ProjectListItem } from "@/api/projects";
import { projectThumbnailUrl, PROJECT_STATUS_COLORS } from "@/api/projects";
import NearViewportImage from "@/components/common/NearViewportImage";

const SIZES = {
  compact: { width: 76, height: 57, thumbSize: "small" as const, icon: 24 },
  expanded: { width: 160, height: 120, thumbSize: "medium" as const, icon: 36 },
};

interface Props {
  project: ProjectListItem;
  variant?: "compact" | "expanded";
}

export default function ProjectCard({ project, variant = "compact" }: Props) {
  const navigate = useNavigate();
  const s = SIZES[variant];
  const src = projectThumbnailUrl(
    project.id,
    s.thumbSize,
    project.thumbnail_version,
    project.workspace_key,
  );

  return (
    <Card variant="outlined" sx={{ opacity: project.active ? 1 : 0.5 }}>
      <CardActionArea
        onClick={() => navigate(`/projects/${project.id}`)}
        sx={{ display: "flex", alignItems: "center", p: 1, gap: 1.5 }}
      >
        <Box
          sx={{
            width: s.width,
            height: s.height,
            flexShrink: 0,
            borderRadius: 1,
            overflow: "hidden",
            bgcolor: project.main_image_path ? "common.black" : "action.hover",
            display: "flex",
            alignItems: "center",
            justifyContent: "center",
          }}
        >
          {project.main_image_path ? (
            <NearViewportImage
              src={src}
              alt=""
              sx={{
                width: "100%",
                height: "100%",
                objectFit: "contain",
                display: "block",
              }}
              fallback={
                <Box
                  sx={{
                    display: "grid",
                    placeItems: "center",
                    width: "100%",
                    height: "100%",
                  }}
                >
                  <CollectionsIcon
                    sx={{ color: "common.white", fontSize: s.icon, opacity: 0.45 }}
                  />
                </Box>
              }
            />
          ) : (
            <CollectionsIcon
              sx={{ color: "text.secondary", fontSize: s.icon, opacity: 0.6 }}
            />
          )}
        </Box>

        <Box sx={{ minWidth: 0, flexGrow: 1 }}>
          <Typography
            variant={variant === "expanded" ? "subtitle1" : "subtitle2"}
            noWrap
            fontWeight={600}
          >
            {project.name}
          </Typography>
          {variant === "expanded" && project.description && (
            <Typography variant="body2" color="text.secondary" noWrap>
              {project.description}
            </Typography>
          )}
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
