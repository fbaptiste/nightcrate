import Box from "@mui/material/Box";
import FormControl from "@mui/material/FormControl";
import InputLabel from "@mui/material/InputLabel";
import MenuItem from "@mui/material/MenuItem";
import Select from "@mui/material/Select";
import Tooltip from "@mui/material/Tooltip";
import Typography from "@mui/material/Typography";
import { useTheme } from "@mui/material/styles";
import type { ReactNode, RefObject } from "react";
import type { Location } from "@/api/locations";
import type { MessierResponse, MessierSlot } from "@/api/messier";
import { formatDateRange } from "@/lib/messierFormat";

interface Props {
  data: MessierResponse;
  locations: Location[];
  locationValue: number | "none";
  onLocation: (value: number | "none") => void;
  controls: ReactNode;
  headerRef: RefObject<HTMLDivElement | null>;
  shownNumbers: ReadonlySet<number>;
  onSlotClick: (number: number) => void;
}

function dateAndNights(slot: MessierSlot, index: number): string {
  const project = slot.projects[index];
  const dates = formatDateRange(project.first_date, project.last_date);
  if (!project.nights) return dates;
  return `${dates}, ${project.nights} ${project.nights === 1 ? "night" : "nights"}`;
}

function MapTooltip({ slot }: { slot: MessierSlot }) {
  const object = slot.object;
  if (!object) return null;
  return (
    <Box sx={{ fontSize: 12, lineHeight: 1.4 }}>
      <Box sx={{ fontWeight: 600, fontSize: 12.5 }}>{object.designation}{object.common_name ? ` ${object.common_name}` : ""}</Box>
      {slot.in_solved_pictures.length > 0 && slot.state === "none" ? (
        <>
          <Box sx={{ opacity: 0.85, mb: 0.5 }}>In a plate-solved picture</Box>
          {slot.in_solved_pictures.map((picture) => (
            <Box key={picture.project_id} sx={{ mt: 0.5, fontWeight: 600 }}>
              {picture.name}
            </Box>
          ))}
        </>
      ) : (
        <Box sx={{ opacity: 0.85, mb: 0.5 }}>{slot.state === "imaged" ? "Imaged" : "Project, no image yet"}</Box>
      )}
      {slot.in_solved_pictures.length === 0 && slot.projects.map((project, index) => (
        <Box key={project.project_id} sx={{ mt: 0.5 }}>
          <Box sx={{ fontWeight: 600 }}>{project.name}</Box>
          <Box sx={{ opacity: 0.85 }}>{dateAndNights(slot, index)}</Box>
          {project.main_image_id == null && <Box sx={{ color: "#ffcc80" }}>No image yet</Box>}
        </Box>
      ))}
    </Box>
  );
}

function MapCell({ slot, teal, shown, onClick }: { slot: MessierSlot; teal: string; shown: boolean; onClick: () => void }) {
  const inSolved = slot.state === "none" && slot.in_solved_pictures.length > 0;
  const tooltip = slot.projects.length || inSolved ? <MapTooltip slot={slot} /> : "";
  let background = "transparent";
  let borderColor = "divider";
  if (slot.state === "imaged") {
    background = teal;
    borderColor = teal;
  } else if (inSolved) {
    background = `radial-gradient(circle at center, ${teal} 0 2.5px, transparent 3px)`;
    borderColor = teal;
  } else if (slot.never_rises) {
    background = "linear-gradient(to top right, transparent calc(50% - 1px), currentColor calc(50% - 1px) calc(50% + 1px), transparent calc(50% + 1px))";
  } else if (slot.state === "project") {
    background = `repeating-linear-gradient(135deg, ${teal} 0 2px, transparent 2px 5px)`;
    borderColor = teal;
  }
  const clickable = Boolean(slot.object && shown);
  const cell = <Box component="button" type="button" tabIndex={-1} onClick={clickable ? onClick : undefined} className="messier-map-cell" sx={{ display: "inline-block", width: 13, height: 13, p: 0, borderRadius: "3px", border: "1.5px solid", borderColor, bgcolor: "transparent", background, color: "text.secondary", opacity: slot.never_rises && !inSolved ? 0.7 : 1, cursor: clickable ? "pointer" : "default", ...(slot.projects.length || inSolved ? { "&:hover": { outline: "2px solid", outlineColor: (theme) => theme.palette.mode === "dark" ? "#d4993f" : "#c07b2b", outlineOffset: "1px" } } : {}) }} />;
  return tooltip ? <Tooltip title={tooltip} arrow enterTouchDelay={600}>{cell}</Tooltip> : cell;
}

function LegendCell({ kind, teal }: { kind: "imaged" | "project" | "solved" | "empty" | "never"; teal: string }) {
  let background = "transparent";
  let borderColor = "divider";
  if (kind === "imaged") { background = teal; borderColor = teal; }
  if (kind === "project") { background = `repeating-linear-gradient(135deg, ${teal} 0 2px, transparent 2px 5px)`; borderColor = teal; }
  if (kind === "solved") { background = `radial-gradient(circle at center, ${teal} 0 2.5px, transparent 3px)`; borderColor = teal; }
  if (kind === "never") background = "linear-gradient(to top right, transparent calc(50% - 1px), currentColor calc(50% - 1px) calc(50% + 1px), transparent calc(50% + 1px))";
  return <Box component="i" className="messier-map-legend-cell" sx={{ width: 13, height: 13, borderRadius: "3px", border: "1.5px solid", borderColor, background, color: "text.secondary" }} />;
}

export default function MessierHeader({ data, locations, locationValue, onLocation, controls, headerRef, shownNumbers, onSlotClick }: Props) {
  const theme = useTheme();
  const teal = theme.palette.mode === "dark" ? "#4db6ac" : "#00695c";
  const rows = Array.from({ length: 6 }, (_, index) => data.slots.slice(index * 20, index * 20 + 20));
  return (
    <Box ref={headerRef} sx={{ position: "sticky", top: 0, zIndex: 10, bgcolor: "background.default", borderBottom: 1, borderColor: "divider", px: 3, pt: 2, pb: "14px", containerType: "inline-size" }}>
      <Box sx={{ maxWidth: 1552, display: "grid", gridTemplateColumns: "minmax(220px, 1fr) auto auto", gridTemplateAreas: '"text controls map"', columnGap: "40px", rowGap: "14px", alignItems: "start", "@container (min-width: 950px) and (max-width: 1099.99px)": { gridTemplateColumns: "minmax(200px, 1fr) auto auto", columnGap: "28px" }, "@container (max-width: 949.99px)": { gridTemplateColumns: "minmax(220px, 1fr) auto", gridTemplateAreas: '"text map" "controls controls"' } }}>
        <Box sx={{ gridArea: "text", minWidth: 0 }}>
          <Typography variant="h4" component="h1" sx={{ mb: "2px", fontSize: 24, fontWeight: 600, whiteSpace: "nowrap" }}>Messier checklist</Typography>
          <FormControl size="small" sx={{ minWidth: 220, my: "10px" }}>
            <InputLabel id="messier-location-label">Location</InputLabel>
            <Select id="messier-location-select" labelId="messier-location-label" label="Location" value={locationValue} onChange={(event) => onLocation(event.target.value as number | "none")}>
              <MenuItem value="none">None</MenuItem>
              {locations.map((location) => <MenuItem key={location.id} value={location.id}>{location.name}</MenuItem>)}
            </Select>
          </FormControl>
          <Box sx={{ color: "text.secondary", mt: "2px" }}>
            <Box component="span" sx={{ color: "text.primary", fontWeight: 600 }}>{data.counts.imaged} of 110 imaged.</Box>
            {data.counts.project > 0 && ` ${data.counts.project} more have a project but no image yet.`}
            {data.counts.in_solved > 0 && ` ${data.counts.in_solved === 1 ? "1 more is in one of your plate-solved pictures." : `${data.counts.in_solved} more are in your plate-solved pictures.`}`}
            {data.counts.never_rises > 0 && data.location && ` Of those not yet imaged, ${data.counts.never_rises} never rise at ${data.location.name}.`}
          </Box>
        </Box>
        {controls}
        <Box aria-hidden sx={{ gridArea: "map", width: 355, display: "flex", flexDirection: "column", alignItems: "flex-end", gap: "10px", "@container (min-width: 950px) and (max-width: 1099.99px)": { width: 269, "& .messier-map-cell, & .messier-map-legend-cell": { width: 10, height: 10 }, "& .messier-map-legend": { fontSize: 11 }, "& .messier-map-row": { gridTemplateColumns: "22px repeat(10, 10px) 5px repeat(10, 10px)", gap: "2px", marginBottom: "2px" } } }}>
          <Box className="messier-map-legend" sx={{ width: "100%", display: "flex", flexWrap: "wrap", justifyContent: "flex-end", gap: "6px 14px", color: "text.secondary", fontSize: 12 }}>
            {([["imaged", "Imaged"], ["project", "Project, no image yet"], ...(data.counts.in_solved ? [["solved", "In a solved picture"]] : []), ["empty", "Not imaged"], ...(data.counts.never_rises ? [["never", "Never rises"]] : [])] as ["imaged" | "project" | "solved" | "empty" | "never", string][]).map(([kind, label]) => <Box key={kind} component="span" sx={{ display: "inline-flex", alignItems: "center", gap: "6px" }}><LegendCell kind={kind} teal={teal} />{label}</Box>)}
          </Box>
          <Box>
            {rows.map((row, rowIndex) => row.length > 0 && (
              <Box key={rowIndex} className="messier-map-row" sx={{ display: "grid", gridTemplateColumns: "26px repeat(10, 13px) 6px repeat(10, 13px)", gap: "3px", alignItems: "center", mb: "3px" }}>
                <Box sx={{ fontSize: 10.5, color: "text.secondary", textAlign: "right", pr: "4px" }}>{row[0]?.number}</Box>
                {row.map((slot, index) => <Box key={slot.number} sx={index === 10 ? { gridColumn: 13 } : undefined}><MapCell slot={slot} teal={teal} shown={shownNumbers.has(slot.number)} onClick={() => onSlotClick(slot.number)} /></Box>)}
              </Box>
            ))}
          </Box>
        </Box>
      </Box>
    </Box>
  );
}
