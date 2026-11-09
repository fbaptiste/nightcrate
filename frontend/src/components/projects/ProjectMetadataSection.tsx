import { useMemo } from "react";
import { useMutation, useQuery } from "@tanstack/react-query";
import Autocomplete from "@mui/material/Autocomplete";
import Box from "@mui/material/Box";
import TextField from "@mui/material/TextField";
import Typography from "@mui/material/Typography";
import { type Location, fetchLocations } from "@/api/locations";
import { type Project, updateProject } from "@/api/projects";
import ProjectSoftwareField from "./ProjectSoftwareField";

interface Props {
  project: Project;
  imagingRuns: string[];
  nightCount: number;
  onUpdated: (project: Project) => void;
  onChanged: () => void;
}

export default function ProjectMetadataSection({
  project,
  imagingRuns,
  nightCount,
  onUpdated,
  onChanged,
}: Props) {
  const { data: locations = [] } = useQuery({
    queryKey: ["locations"],
    queryFn: fetchLocations,
  });

  const locationMut = useMutation({
    mutationFn: (locationId: number | null) =>
      updateProject(project.id, { location_id: locationId }),
    onSuccess: onUpdated,
  });

  const locationOptions = useMemo(() => {
    if (
      project.location_id != null &&
      !locations.some((location) => location.id === project.location_id)
    ) {
      return [
        ...locations,
        {
          id: project.location_id,
          name: `${project.location_name ?? "Unknown"} (retired)`,
        } as unknown as Location,
      ];
    }
    return locations;
  }, [locations, project.location_id, project.location_name]);
  const selectedLocation =
    locationOptions.find((location) => location.id === project.location_id) ?? null;

  const labelSx = {
    m: 0,
    color: "text.secondary",
    fontSize: "13px",
    lineHeight: 1.45,
  } as const;

  return (
    <Box
      component="dl"
      sx={{
        display: "grid",
        gridTemplateColumns: "112px minmax(0, 1fr)",
        columnGap: "14px",
        rowGap: "8px",
        alignItems: "center",
        m: 0,
        // The software chips need the column's full width when the side
        // column is narrow (e.g. a 1280 px window beside the sidebar);
        // otherwise two chips with version pills don't fit on one line.
        containerType: "inline-size",
      }}
    >
      <Typography component="dt" sx={labelSx}>
        Imaged
      </Typography>
      <Box component="dd" sx={{ m: 0, minWidth: 0, fontSize: "14px", lineHeight: 1.45 }}>
        {imagingRuns.length > 0 ? imagingRuns.join(", ") : "No imaging sessions yet"}
        {imagingRuns.length > 0 && (
          <Typography
            component="span"
            sx={{
              ml: "6px",
              color: "text.secondary",
              fontSize: "13px",
              lineHeight: "inherit",
            }}
          >
            {nightCount} {nightCount === 1 ? "night" : "nights"}
          </Typography>
        )}
      </Box>

      <Typography component="dt" sx={labelSx}>
        Location
      </Typography>
      <Box component="dd" sx={{ m: 0 }}>
        <Autocomplete
          size="small"
          options={locationOptions}
          value={selectedLocation}
          onChange={(_event, value) => locationMut.mutate(value?.id ?? null)}
          getOptionLabel={(location) => location.name}
          isOptionEqualToValue={(option, value) => option.id === value.id}
          sx={{ display: "inline-flex", minWidth: 180, maxWidth: "100%" }}
          renderInput={(params) => (
            <TextField
              {...params}
              placeholder="Set location"
              inputProps={{ ...params.inputProps, readOnly: true }}
              sx={(theme) => ({
                "& .MuiOutlinedInput-root": {
                  height: "32px",
                  borderRadius: "6px",
                  fontSize: "14px",
                  "& fieldset": {
                    borderColor:
                      theme.palette.mode === "dark"
                        ? "rgba(255,255,255,0.23)"
                        : "#c4c1bb",
                  },
                },
              })}
            />
          )}
        />
      </Box>

      <Typography
        component="dt"
        sx={{
          ...labelSx,
          alignSelf: "start",
          pt: "4px",
          "@container (max-width: 560px)": { gridColumn: "1 / -1", pt: "6px" },
        }}
      >
        Processed with
      </Typography>
      <Box
        component="dd"
        sx={{ m: 0, minWidth: 0, "@container (max-width: 560px)": { gridColumn: "1 / -1" } }}
      >
        <ProjectSoftwareField project={project} onUpdated={onUpdated} onChanged={onChanged} />
      </Box>
    </Box>
  );
}
