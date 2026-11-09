import { useRef, useState } from "react";
import DeleteIcon from "@mui/icons-material/Delete";
import Box from "@mui/material/Box";
import Button from "@mui/material/Button";
import IconButton from "@mui/material/IconButton";
import TextField from "@mui/material/TextField";
import Typography from "@mui/material/Typography";

export interface SoftwareVersionDraft {
  id?: number;
  version: string;
  project_count: number;
  project_names: string[];
}

interface SoftwareVersionsFieldProps {
  value: SoftwareVersionDraft[];
  onChange: (versions: SoftwareVersionDraft[]) => void;
  disabled?: boolean;
}

function usageLabel(version: SoftwareVersionDraft): string {
  if (version.project_count === 0) return "Not used";
  if (version.project_count === 1 && version.project_names[0]) {
    return `Used by ${version.project_names[0]}`;
  }
  return `Used by ${version.project_count} projects`;
}

export default function SoftwareVersionsField({
  value,
  onChange,
  disabled = false,
}: SoftwareVersionsFieldProps) {
  const [newVersion, setNewVersion] = useState("");
  const [editingIndex, setEditingIndex] = useState<number | null>(null);
  const [editValue, setEditValue] = useState("");
  const [error, setError] = useState<string | null>(null);
  const renameCancelled = useRef(false);

  const validateVersion = (candidate: string, exceptIndex?: number): string | null => {
    const trimmed = candidate.trim();
    if (!trimmed) return "Enter a version";
    if (trimmed.length > 50) return "Versions can be at most 50 characters";
    if (value.some((item, index) => index !== exceptIndex && item.version === trimmed)) {
      return "That version is already listed";
    }
    return null;
  };

  const addVersion = () => {
    const nextError = validateVersion(newVersion);
    if (nextError) {
      setError(nextError);
      return;
    }
    onChange([
      { version: newVersion.trim(), project_count: 0, project_names: [] },
      ...value,
    ]);
    setNewVersion("");
    setError(null);
  };

  const saveRename = (index: number) => {
    const nextError = validateVersion(editValue, index);
    if (nextError) {
      setError(nextError);
      return;
    }
    onChange(value.map((item, itemIndex) =>
      itemIndex === index ? { ...item, version: editValue.trim() } : item,
    ));
    setEditingIndex(null);
    setError(null);
  };

  return (
    <Box>
      <Box
        component="fieldset"
        sx={(theme) => ({
          m: 0,
          minWidth: 0,
          border: "1px solid",
          borderColor: theme.palette.mode === "dark" ? "rgba(255, 255, 255, 0.23)" : "#c4c1bb",
          borderRadius: "6px",
          px: "12px",
          pt: "8px",
          pb: "10px",
        })}
      >
        <Typography
          component="legend"
          sx={{ px: "4px", fontSize: "12px", lineHeight: "18px", color: "text.secondary" }}
        >
          Versions
        </Typography>

        {value.map((item, index) => {
          const used = item.project_count > 0;
          const use = usageLabel(item);
          return (
            <Box
              key={item.id ?? `new-${index}-${item.version}`}
              sx={{
                display: "flex",
                alignItems: "center",
                gap: "10px",
                py: "4px",
                borderBottom: index === value.length - 1 ? 0 : "1px solid",
                borderColor: (theme) => theme.palette.mode === "dark" ? "#34373d" : "#dcd9d4",
              }}
            >
              {editingIndex === index ? (
                <TextField
                  autoFocus
                  size="small"
                  value={editValue}
                  onChange={(event) => setEditValue(event.target.value)}
                  onBlur={() => {
                    if (renameCancelled.current) {
                      renameCancelled.current = false;
                      return;
                    }
                    saveRename(index);
                  }}
                  onKeyDown={(event) => {
                    if (event.key === "Enter") saveRename(index);
                    if (event.key === "Escape") {
                      event.preventDefault();
                      renameCancelled.current = true;
                      setEditingIndex(null);
                      setEditValue(item.version);
                      setError(null);
                    }
                  }}
                  slotProps={{ htmlInput: { "aria-label": `Rename ${item.version}` } }}
                  sx={{ width: 150 }}
                />
              ) : (
                <Button
                  variant="text"
                  disabled={disabled}
                  onClick={() => {
                    renameCancelled.current = false;
                    setEditingIndex(index);
                    setEditValue(item.version);
                    setError(null);
                  }}
                  sx={{
                    minWidth: 90,
                    justifyContent: "flex-start",
                    p: 0,
                    color: "text.primary",
                    fontWeight: 500,
                    textTransform: "none",
                  }}
                >
                  {item.version}
                </Button>
              )}
              <Typography sx={{ flex: 1, fontSize: "12.5px", color: "text.secondary" }}>
                {use}
              </Typography>
              <IconButton
                size="small"
                disabled={disabled || used}
                aria-label={
                  used
                    ? `Remove ${item.version} (${use.toLowerCase()})`
                    : `Remove ${item.version}`
                }
                onClick={() => onChange(value.filter((_, itemIndex) => itemIndex !== index))}
              >
                <DeleteIcon fontSize="small" />
              </IconButton>
            </Box>
          );
        })}

        <Box sx={{ display: "flex", gap: 1, mt: 1 }}>
          <TextField
            size="small"
            fullWidth
            placeholder="Add a version, e.g. 1.9.4"
            value={newVersion}
            disabled={disabled}
            onChange={(event) => {
              setNewVersion(event.target.value);
              setError(null);
            }}
            onKeyDown={(event) => {
              if (event.key === "Enter") {
                event.preventDefault();
                addVersion();
              }
            }}
            error={Boolean(error)}
            helperText={error}
          />
          <Button
            variant="outlined"
            size="small"
            disabled={disabled}
            onClick={addVersion}
            sx={{ height: 40 }}
          >
            Add
          </Button>
        </Box>
      </Box>
      <Typography sx={{ mt: "6px", fontSize: "12.5px", color: "text.secondary" }}>
        Newest added first. Click a version to rename it.
      </Typography>
    </Box>
  );
}
