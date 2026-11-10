import { useState, type MouseEvent } from "react";
import CollectionsIcon from "@mui/icons-material/Collections";
import Box from "@mui/material/Box";
import ButtonBase from "@mui/material/ButtonBase";
import Menu from "@mui/material/Menu";
import MenuItem from "@mui/material/MenuItem";
import Tooltip from "@mui/material/Tooltip";
import Typography from "@mui/material/Typography";
import { useNavigate } from "react-router-dom";
import type { ProjectTargetLink } from "@/api/projectTargetLinks";
import { formatImagingRuns } from "@/lib/galleryRendition";

interface Props {
  designation: string;
  links: ProjectTargetLink[];
}

function imagingDates(link: ProjectTargetLink): string {
  const runs = formatImagingRuns(link);
  return runs.length > 0
    ? `${runs.join(", ")}, ${link.nights} ${link.nights === 1 ? "night" : "nights"}`
    : "No imaging dates";
}

function statusLabel(status: string): string {
  return status.charAt(0).toUpperCase() + status.slice(1);
}

export default function ProjectPill({ designation, links }: Props) {
  const navigate = useNavigate();
  const [anchorEl, setAnchorEl] = useState<HTMLElement | null>(null);
  if (links.length === 0) return null;

  const multiple = links.length > 1;
  const tooltip = multiple
    ? `${links.length} projects have ${designation} as a main target`
    : `Open project: ${links[0].name}`;
  const label = multiple ? `${links.length} projects ▾` : links[0].name;

  const handleClick = (event: MouseEvent<HTMLElement>) => {
    if (multiple) setAnchorEl(event.currentTarget);
    else navigate(`/projects/${links[0].project_id}`);
  };

  return (
    <>
      <Tooltip title={tooltip} arrow>
        <ButtonBase
          onClick={handleClick}
          aria-haspopup={multiple ? "menu" : undefined}
          aria-expanded={multiple && anchorEl ? true : undefined}
          sx={(theme) => {
            const slate = theme.palette.mode === "dark" ? "#7d9ab8" : "#5b7a9e";
            return {
              display: "inline-flex",
              alignItems: "center",
              gap: "6px",
              height: 26,
              maxWidth: 220,
              pl: "9px",
              pr: "11px",
              borderRadius: "13px",
              border: "1px solid",
              borderColor: slate,
              color: slate,
              whiteSpace: "nowrap",
              fontSize: "12.5px",
              fontWeight: 600,
              "&:hover": { bgcolor: `${slate}1a` },
            };
          }}
        >
          <CollectionsIcon sx={{ width: 15, height: 15, flex: "0 0 15px" }} />
          <Box component="span" sx={{ overflow: "hidden", textOverflow: "ellipsis" }}>
            {label}
          </Box>
        </ButtonBase>
      </Tooltip>

      {multiple && (
        <Menu
          anchorEl={anchorEl}
          open={Boolean(anchorEl)}
          onClose={() => setAnchorEl(null)}
          slotProps={{ paper: { sx: { minWidth: 280 } } }}
        >
          {links.map((link) => (
            <MenuItem
              key={link.project_id}
              onClick={() => {
                setAnchorEl(null);
                navigate(`/projects/${link.project_id}`);
              }}
              sx={{ display: "block", px: "14px", py: "8px" }}
            >
              <Box sx={{ display: "flex", alignItems: "center", gap: 1 }}>
                <Typography sx={{ fontSize: "14px", fontWeight: 600 }}>
                  {link.name}
                </Typography>
                {link.status !== "active" && (
                  <Box
                    component="span"
                    sx={(theme) => ({
                      display: "inline-flex",
                      alignItems: "center",
                      height: 20,
                      px: "7px",
                      border: "1px solid currentColor",
                      borderRadius: "10px",
                      color:
                        link.status === "paused"
                          ? theme.palette.mode === "dark"
                            ? "#f0a35e"
                            : "#b85500"
                          : link.status === "complete"
                            ? theme.palette.mode === "dark"
                              ? "#7fb2ea"
                              : "#1f63b0"
                            : "text.secondary",
                      fontSize: "11px",
                      fontWeight: 600,
                    })}
                  >
                    {statusLabel(link.status)}
                  </Box>
                )}
              </Box>
              <Typography sx={{ color: "text.secondary", fontSize: "12.5px" }}>
                {imagingDates(link)}
              </Typography>
            </MenuItem>
          ))}
        </Menu>
      )}
    </>
  );
}
