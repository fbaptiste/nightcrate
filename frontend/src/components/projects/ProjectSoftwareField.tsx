import { useMemo, useState, type MouseEvent } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import Autocomplete from "@mui/material/Autocomplete";
import Box from "@mui/material/Box";
import Button from "@mui/material/Button";
import Chip from "@mui/material/Chip";
import Divider from "@mui/material/Divider";
import Menu from "@mui/material/Menu";
import MenuItem from "@mui/material/MenuItem";
import TextField from "@mui/material/TextField";
import Typography from "@mui/material/Typography";
import {
  createSoftwareVersion,
  fetchSoftwares,
  type Software,
} from "@/api/equipment";
import {
  setProjectSoftware,
  type Project,
  type ProjectSoftwareRef,
} from "@/api/projects";
import { orderSoftwareOptions } from "@/components/shared/softwareOrder";
import { formatSnakeCase } from "@/lib/formUtils";
import { CHIP_ROW_GAP } from "./chipRow";

interface Props {
  project: Project;
  onUpdated: (project: Project) => void;
  onChanged: () => void;
}

interface VersionMenuState {
  index: number;
  anchor: HTMLElement;
}

export default function ProjectSoftwareField({ project, onUpdated, onChanged }: Props) {
  const queryClient = useQueryClient();
  const { data: allSoftware = [] } = useQuery({
    queryKey: ["software", "project-options"],
    queryFn: () => fetchSoftwares(true),
  });
  const [versionMenu, setVersionMenu] = useState<VersionMenuState | null>(null);
  const [addingVersion, setAddingVersion] = useState(false);
  const [newVersion, setNewVersion] = useState("");
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const selectedIds = useMemo(
    () => new Set(project.software.map((entry) => entry.software_id)),
    [project.software],
  );
  const options = useMemo(
    () => orderSoftwareOptions(
      allSoftware.filter((software) => software.active || selectedIds.has(software.id)),
      "project",
    ),
    [allSoftware, selectedIds],
  );
  const save = async (
    entries: { software_id: number; software_version_id: number | null }[],
  ) => {
    setSaving(true);
    setError(null);
    try {
      const updated = await setProjectSoftware(project.id, entries);
      onUpdated(updated);
      onChanged();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to save project software");
    } finally {
      setSaving(false);
    }
  };

  const currentEntries = () => project.software.map((entry) => ({
    software_id: entry.software_id,
    software_version_id: entry.software_version_id,
  }));

  const addSoftware = (software: Software) => {
    const entries = currentEntries();
    const same = entries.filter((entry) => entry.software_id === software.id);
    let versionId: number | null = null;
    if (same.some((entry) => entry.software_version_id == null)) {
      const used = new Set(same.map((entry) => entry.software_version_id));
      versionId = software.versions.find((version) => !used.has(version.id))?.id ?? null;
      if (versionId == null) {
        setError("Add another version to this program before selecting it again.");
        return;
      }
    }
    void save([...entries, { software_id: software.id, software_version_id: versionId }]);
  };

  const removeEntry = (index: number) => {
    void save(currentEntries().filter((_entry, entryIndex) => entryIndex !== index));
  };

  const setVersion = (index: number, versionId: number | null) => {
    const entries = currentEntries();
    const selected = entries[index];
    if (!selected) return;
    const duplicate = entries.some(
      (entry, entryIndex) =>
        entryIndex !== index &&
        entry.software_id === selected.software_id &&
        entry.software_version_id === versionId,
    );
    if (duplicate) {
      setError("The same software and version may appear only once.");
      return;
    }
    entries[index] = { ...selected, software_version_id: versionId };
    setVersionMenu(null);
    setAddingVersion(false);
    void save(entries);
  };

  const addVersion = async () => {
    const text = newVersion.trim();
    const index = versionMenu?.index;
    if (!text || index == null) return;
    const entry = project.software[index];
    if (!entry) return;
    setSaving(true);
    setError(null);
    try {
      const version = await createSoftwareVersion(entry.software_id, text);
      await queryClient.invalidateQueries({ queryKey: ["software"] });
      setNewVersion("");
      setAddingVersion(false);
      setVersion(index, version.id);
    } catch (err) {
      setSaving(false);
      setError(err instanceof Error ? err.message : "Failed to add the software version");
    }
  };

  const menuEntry: ProjectSoftwareRef | undefined = versionMenu
    ? project.software[versionMenu.index]
    : undefined;
  const menuSoftware = menuEntry
    ? allSoftware.find((software) => software.id === menuEntry.software_id)
    : undefined;
  const usedVersionIds = new Set(
    project.software
      .filter((entry, index) =>
        entry.software_id === menuEntry?.software_id && index !== versionMenu?.index,
      )
      .map((entry) => entry.software_version_id),
  );

  const openVersionMenu = (event: MouseEvent<HTMLElement>, index: number) => {
    event.preventDefault();
    event.stopPropagation();
    setAddingVersion(false);
    setNewVersion("");
    setVersionMenu({ index, anchor: event.currentTarget });
  };

  return (
    <Box sx={{ minWidth: 0 }}>
      <Box
        sx={{
          display: "flex",
          flexFlow: "row wrap",
          alignItems: "center",
          gap: CHIP_ROW_GAP,
          width: "100%",
          "& > .MuiChip-root": { flex: "0 0 auto", m: 0 },
        }}
      >
        {project.software.map((entry, index) => (
          <Chip
            key={entry.id}
            size="small"
            disabled={saving}
            label={
              <Box
                component="span"
                sx={{ display: "inline-flex", alignItems: "center", gap: "6px" }}
              >
                <span>
                  {entry.name}
                  {!entry.active ? " (retired)" : ""}
                </span>
                <Box
                  component="button"
                  type="button"
                  aria-label={`Choose a version of ${entry.name}`}
                  onClick={(event) => openVersionMenu(event, index)}
                  sx={(theme) => ({
                    border: 0,
                    px: "6px",
                    height: "18px",
                    borderRadius: "9px",
                    bgcolor: theme.palette.mode === "dark" ? "#24272c" : "#ffffff",
                    color:
                      entry.version == null
                        ? theme.palette.mode === "dark"
                          ? "#6a6863"
                          : "#a3a3a3"
                        : "text.secondary",
                    font: "inherit",
                    fontSize: "12px",
                    cursor: "pointer",
                  })}
                >
                  {entry.version ?? "No version"} ▾
                </Box>
              </Box>
            }
            onDelete={() => removeEntry(index)}
            sx={(theme) => ({
              height: "26px",
              bgcolor: theme.palette.mode === "dark" ? "#31343a" : "#ebe8e3",
              fontSize: "13px",
              "& .MuiChip-label": { pl: "11px", pr: "5px" },
            })}
          />
        ))}

        <Autocomplete<Software, false, false, false>
          size="small"
          openOnFocus
          options={options}
          value={null}
          disabled={saving}
          onChange={(_event, value) => {
            if (value) addSoftware(value);
          }}
          groupBy={(option) => formatSnakeCase(option.category)}
          getOptionLabel={(option) => option.name}
          isOptionEqualToValue={(option, selected) => option.id === selected.id}
          renderOption={(props, option) => {
            const { key, ...optionProps } = props;
            return (
              <li key={key} {...optionProps}>
                <Box
                  sx={{
                    display: "flex",
                    justifyContent: "space-between",
                    gap: 2,
                    width: "100%",
                  }}
                >
                  <span>
                    {option.name}
                    {!option.active ? " (retired)" : ""}
                  </span>
                  <Typography
                    component="span"
                    sx={(theme) => ({
                      color: theme.palette.mode === "dark" ? "#6a6863" : "#a3a3a3",
                      fontSize: "12px",
                    })}
                  >
                    {option.manufacturer?.name ?? "—"}
                  </Typography>
                </Box>
              </li>
            );
          }}
          sx={{ width: 142, flex: "0 0 142px" }}
          renderInput={(params) => (
            <TextField
              {...params}
              placeholder="+ Add software"
              inputProps={{ ...params.inputProps, "aria-label": "Add software" }}
              sx={(theme) => {
                const amber = theme.palette.mode === "dark" ? "#d4993f" : "#c07b2b";
                return {
                  "& .MuiOutlinedInput-root": {
                    height: "26px",
                    minHeight: "26px",
                    p: "0 !important",
                    borderRadius: "13px",
                    color: amber,
                    fontSize: "13px",
                    "& fieldset": {
                      borderStyle: "dashed",
                      borderColor:
                        theme.palette.mode === "dark"
                          ? "rgba(255,255,255,0.23)"
                          : "#c4c1bb",
                    },
                    "& input": {
                      height: "26px",
                      p: "0 11px !important",
                      color: amber,
                      "&::placeholder": { color: amber, opacity: 1 },
                    },
                    "& .MuiAutocomplete-popupIndicator": { color: amber },
                  },
                };
              }}
            />
          )}
        />
      </Box>

      {error && (
        <Typography role="alert" sx={{ mt: "4px", color: "error.main", fontSize: "12px" }}>
          {error}
        </Typography>
      )}

      <Menu
        anchorEl={versionMenu?.anchor ?? null}
        open={versionMenu != null}
        onClose={() => {
          setVersionMenu(null);
          setAddingVersion(false);
        }}
      >
        <MenuItem
          selected={menuEntry?.software_version_id == null}
          disabled={usedVersionIds.has(null)}
          onClick={() => versionMenu && setVersion(versionMenu.index, null)}
        >
          No version
        </MenuItem>
        {(menuSoftware?.versions ?? []).map((version) => (
          <MenuItem
            key={version.id}
            selected={menuEntry?.software_version_id === version.id}
            disabled={usedVersionIds.has(version.id)}
            onClick={() => versionMenu && setVersion(versionMenu.index, version.id)}
          >
            {version.version}
          </MenuItem>
        ))}
        <Divider />
        {addingVersion ? (
          <Box sx={{ display: "flex", gap: 1, px: 1.5, py: 0.75 }}>
            <TextField
              size="small"
              autoFocus
              value={newVersion}
              onChange={(event) => setNewVersion(event.target.value)}
              onKeyDown={(event) => {
                event.stopPropagation();
                if (event.key === "Enter") void addVersion();
              }}
              placeholder="Version"
            />
            <Button size="small" onClick={() => void addVersion()} disabled={!newVersion.trim()}>
              Add
            </Button>
          </Box>
        ) : (
          <MenuItem
            onClick={() => setAddingVersion(true)}
            sx={(theme) => ({ color: theme.palette.mode === "dark" ? "#d4993f" : "#c07b2b" })}
          >
            Add a version
          </MenuItem>
        )}
      </Menu>
    </Box>
  );
}
