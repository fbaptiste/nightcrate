import { useMemo, useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import Box from "@mui/material/Box";
import Button from "@mui/material/Button";
import FormControl from "@mui/material/FormControl";
import IconButton from "@mui/material/IconButton";
import InputLabel from "@mui/material/InputLabel";
import MenuItem from "@mui/material/MenuItem";
import Select from "@mui/material/Select";
import Snackbar from "@mui/material/Snackbar";
import TextField from "@mui/material/TextField";
import Tooltip from "@mui/material/Tooltip";
import Typography from "@mui/material/Typography";
import FormControlLabel from "@mui/material/FormControlLabel";
import Switch from "@mui/material/Switch";
import AddIcon from "@mui/icons-material/Add";
import GridViewIcon from "@mui/icons-material/GridView";
import ViewListIcon from "@mui/icons-material/ViewList";
import ViewCompactIcon from "@mui/icons-material/ViewCompact";
import {
  fetchProjects,
  createProject,
  type ProjectCreate,
} from "@/api/projects";
import ProjectCard from "@/components/projects/ProjectCard";
import ProjectGalleryCard from "@/components/projects/ProjectGalleryCard";
import ProjectFormDialog from "@/components/projects/ProjectFormDialog";

type ViewMode = "compact" | "list" | "gallery";

export default function ProjectsPage() {
  const queryClient = useQueryClient();
  const [search, setSearch] = useState("");
  const [sortBy, setSortBy] = useState("updated_at");
  const [viewMode, setViewMode] = useState<ViewMode>("gallery");
  const [showRetired, setShowRetired] = useState(false);
  const [dialogOpen, setDialogOpen] = useState(false);
  const [snack, setSnack] = useState<string | null>(null);

  const { data: projects = [], isLoading } = useQuery({
    queryKey: ["projects", { sort: sortBy, showRetired }],
    queryFn: () => fetchProjects({ sort: sortBy, include_retired: showRetired }),
  });

  const createMutation = useMutation({
    mutationFn: (data: ProjectCreate) => createProject(data),
    onSuccess: (p) => {
      queryClient.invalidateQueries({ queryKey: ["projects"] });
      setDialogOpen(false);
      setSnack(`Created "${p.name}"`);
    },
    onError: (err) => setSnack(String(err)),
  });

  const filtered = useMemo(() => {
    if (!search) return projects;
    const q = search.toLowerCase();
    return projects.filter(
      (p) =>
        p.name.toLowerCase().includes(q) ||
        p.description?.toLowerCase().includes(q),
    );
  }, [projects, search]);

  return (
    <Box sx={{ p: 3, height: "100%", overflow: "auto" }}>
      <Box
        sx={{
          display: "flex",
          alignItems: "center",
          gap: 2,
          mb: 3,
          flexWrap: "wrap",
        }}
      >
        <Typography variant="h5" sx={{ flexGrow: 1, fontWeight: 600 }}>
          Projects
        </Typography>
        <TextField
          size="small"
          placeholder="Search projects..."
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          sx={{ width: 240 }}
        />
        <FormControl size="small" sx={{ minWidth: 140 }}>
          <InputLabel>Sort by</InputLabel>
          <Select
            value={sortBy}
            label="Sort by"
            onChange={(e) => setSortBy(e.target.value)}
          >
            <MenuItem value="updated_at">Last Modified</MenuItem>
            <MenuItem value="created_at">Date Created</MenuItem>
            <MenuItem value="name">Name</MenuItem>
          </Select>
        </FormControl>
        <FormControlLabel
          control={
            <Switch
              size="small"
              checked={showRetired}
              onChange={(e) => setShowRetired(e.target.checked)}
            />
          }
          label={<Typography variant="caption">Show retired</Typography>}
          sx={{ mr: 0 }}
        />
        <Box sx={{ display: "flex", border: 1, borderColor: "divider", borderRadius: 1 }}>
          <Tooltip title="Gallery">
            <IconButton
              size="small"
              onClick={() => setViewMode("gallery")}
              color={viewMode === "gallery" ? "primary" : "default"}
            >
              <GridViewIcon fontSize="small" />
            </IconButton>
          </Tooltip>
          <Tooltip title="List">
            <IconButton
              size="small"
              onClick={() => setViewMode("list")}
              color={viewMode === "list" ? "primary" : "default"}
            >
              <ViewListIcon fontSize="small" />
            </IconButton>
          </Tooltip>
          <Tooltip title="Compact">
            <IconButton
              size="small"
              onClick={() => setViewMode("compact")}
              color={viewMode === "compact" ? "primary" : "default"}
            >
              <ViewCompactIcon fontSize="small" />
            </IconButton>
          </Tooltip>
        </Box>
        <Button
          variant="contained"
          startIcon={<AddIcon />}
          onClick={() => setDialogOpen(true)}
        >
          New Project
        </Button>
      </Box>

      {isLoading && (
        <Typography color="text.secondary">Loading projects...</Typography>
      )}

      {!isLoading && filtered.length === 0 && (
        <Box sx={{ textAlign: "center", py: 8 }}>
          <Typography variant="h6" color="text.secondary" gutterBottom>
            {search ? "No matching projects" : "No projects yet"}
          </Typography>
          {!search && (
            <Typography variant="body2" color="text.secondary">
              Create your first project to start organizing your imaging work.
            </Typography>
          )}
        </Box>
      )}

      <Box
        sx={{
          display: "grid",
          gridTemplateColumns: {
            gallery: "repeat(auto-fill, minmax(220px, 1fr))",
            list: "repeat(auto-fill, minmax(320px, 1fr))",
            compact: "repeat(auto-fill, minmax(280px, 1fr))",
          }[viewMode],
          gap: viewMode === "gallery" ? 2 : 1,
        }}
      >
        {filtered.map((p) =>
          viewMode === "gallery" ? (
            <ProjectGalleryCard key={p.id} project={p} />
          ) : (
            <ProjectCard
              key={p.id}
              project={p}
              variant={viewMode === "list" ? "expanded" : "compact"}
            />
          ),
        )}
      </Box>

      <ProjectFormDialog
        open={dialogOpen}
        onClose={() => setDialogOpen(false)}
        onSave={(data) => createMutation.mutate(data)}
      />

      <Snackbar
        open={!!snack}
        autoHideDuration={3000}
        onClose={() => setSnack(null)}
        message={snack}
      />
    </Box>
  );
}
