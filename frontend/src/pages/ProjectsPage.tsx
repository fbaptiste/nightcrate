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
import AddIcon from "@mui/icons-material/Add";
import {
  fetchProjects,
  createProject,
  type ProjectCreate,
} from "@/api/projects";
import ProjectCard from "@/components/projects/ProjectCard";
import ProjectFormDialog from "@/components/projects/ProjectFormDialog";

export default function ProjectsPage() {
  const queryClient = useQueryClient();
  const [search, setSearch] = useState("");
  const [sortBy, setSortBy] = useState("updated_at");
  const [dialogOpen, setDialogOpen] = useState(false);
  const [snack, setSnack] = useState<string | null>(null);

  const { data: projects = [], isLoading } = useQuery({
    queryKey: ["projects", { sort: sortBy }],
    queryFn: () => fetchProjects({ sort: sortBy }),
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
          gridTemplateColumns: "repeat(auto-fill, minmax(280px, 1fr))",
          gap: 1,
        }}
      >
        {filtered.map((p) => (
          <ProjectCard key={p.id} project={p} />
        ))}
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
