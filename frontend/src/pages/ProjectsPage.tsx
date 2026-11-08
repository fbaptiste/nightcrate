import { useMemo, useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import Box from "@mui/material/Box";
import Button from "@mui/material/Button";
import FormControl from "@mui/material/FormControl";
import InputLabel from "@mui/material/InputLabel";
import MenuItem from "@mui/material/MenuItem";
import Select from "@mui/material/Select";
import Snackbar from "@mui/material/Snackbar";
import TextField from "@mui/material/TextField";
import Typography from "@mui/material/Typography";
import FormControlLabel from "@mui/material/FormControlLabel";
import Switch from "@mui/material/Switch";
import AddIcon from "@mui/icons-material/Add";
import GridViewIcon from "@mui/icons-material/GridView";
import ViewListIcon from "@mui/icons-material/ViewList";
import ViewHeadlineIcon from "@mui/icons-material/ViewHeadline";
import {
  fetchProjects,
  createProject,
  type ProjectCreate,
} from "@/api/projects";
import ProjectCard from "@/components/projects/ProjectCard";
import ProjectGalleryCard from "@/components/projects/ProjectGalleryCard";
import ProjectFormDialog from "@/components/projects/ProjectFormDialog";
import ViewToggle, { type ViewToggleOption } from "@/components/common/ViewToggle";

type ViewMode = "compact" | "list" | "pictures";

const VIEW_OPTIONS: ViewToggleOption<ViewMode>[] = [
  { value: "compact", label: "Compact", icon: <ViewHeadlineIcon /> },
  { value: "list", label: "List", icon: <ViewListIcon /> },
  { value: "pictures", label: "Pictures", icon: <GridViewIcon /> },
];

export default function ProjectsPage() {
  const queryClient = useQueryClient();
  const [search, setSearch] = useState("");
  const [sortBy, setSortBy] = useState("updated_at");
  const [viewMode, setViewMode] = useState<ViewMode>("pictures");
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
        <ViewToggle
          options={VIEW_OPTIONS}
          value={viewMode}
          onChange={setViewMode}
          ariaLabel="Projects view"
        />
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
            pictures: "repeat(auto-fill, minmax(220px, 1fr))",
            list: "repeat(auto-fill, minmax(320px, 1fr))",
            compact: "repeat(auto-fill, minmax(280px, 1fr))",
          }[viewMode],
          gap: viewMode === "pictures" ? 2 : 1,
        }}
      >
        {filtered.map((p) =>
          viewMode === "pictures" ? (
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
