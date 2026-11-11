import Box from "@mui/material/Box";
import FormControl from "@mui/material/FormControl";
import FormControlLabel from "@mui/material/FormControlLabel";
import MenuItem from "@mui/material/MenuItem";
import Select from "@mui/material/Select";
import Switch from "@mui/material/Switch";
import ToggleButton from "@mui/material/ToggleButton";
import ToggleButtonGroup from "@mui/material/ToggleButtonGroup";
import AppsIcon from "@mui/icons-material/Apps";
import GridViewIcon from "@mui/icons-material/GridView";
import CropLandscapeIcon from "@mui/icons-material/CropLandscape";
import type { MessierView } from "@/api/settings";
import type { Rig } from "@/api/rigs";
import { formatField } from "@/lib/messierFormat";

export type MessierShow = "all" | "imaged" | "not";

interface Props {
  show: MessierShow;
  imagedStyle: "own" | "sky";
  unimagedStyle: "sky" | "blank";
  rigId: number | null;
  rigs: Rig[];
  rigField: { major: number; minor: number } | null;
  rigUnavailable: boolean;
  showProjects: boolean;
  view: MessierView;
  onShow: (value: MessierShow) => void;
  onImagedStyle: (value: "own" | "sky") => void;
  onUnimagedStyle: (value: "sky" | "blank") => void;
  onRig: (value: number | null) => void;
  onShowProjects: (value: boolean) => void;
  onView: (value: MessierView) => void;
}

const groupSx = { height: 30, "& .MuiToggleButton-root": { px: "11px", py: "4px", fontSize: 13, lineHeight: 1.2, textTransform: "none" } };
const controlSx = { display: "flex", flexDirection: "column", alignItems: "flex-start", gap: "4px" } as const;
const captionSx = { color: "text.secondary", fontSize: 12, lineHeight: 1.2 } as const;

export default function MessierToolbar(props: Props) {
  return (
    <Box sx={{ gridArea: "controls", display: "grid", gridTemplateColumns: "repeat(2, max-content)", gap: "10px 28px", alignContent: "start", "@container (max-width: 949.99px)": { display: "flex", flexWrap: "wrap", alignItems: "flex-start", gap: "10px 28px" } }}>
      <Box sx={controlSx}>
        <Box id="messier-show-label" sx={captionSx}>Show</Box>
        <ToggleButtonGroup aria-labelledby="messier-show-label" exclusive value={props.show} onChange={(_, value) => value && props.onShow(value)} sx={groupSx}><ToggleButton value="all">All</ToggleButton><ToggleButton value="imaged">Imaged</ToggleButton><ToggleButton value="not">Not imaged</ToggleButton></ToggleButtonGroup>
      </Box>
      <Box sx={controlSx}>
        <Box id="messier-tile-size-label" sx={captionSx}>Tile size</Box>
        <ToggleButtonGroup aria-labelledby="messier-tile-size-label" exclusive value={props.view} onChange={(_, value) => value && props.onView(value)} sx={{ ...groupSx, "& .MuiToggleButton-root": { px: "9px", py: "4px" }, "& .MuiSvgIcon-root": { fontSize: 18 } }}>
          <ToggleButton value="small" aria-label="Small pictures" title="Small pictures"><AppsIcon /></ToggleButton>
          <ToggleButton value="medium" aria-label="Medium pictures" title="Medium pictures"><GridViewIcon /></ToggleButton>
          <ToggleButton value="large" aria-label="Large pictures" title="Large pictures"><CropLandscapeIcon /></ToggleButton>
        </ToggleButtonGroup>
      </Box>
      <Box sx={controlSx}>
        <Box id="messier-imaged-style-label" sx={captionSx}>Imaged as</Box>
        <ToggleButtonGroup aria-labelledby="messier-imaged-style-label" exclusive value={props.imagedStyle} onChange={(_, value) => value && props.onImagedStyle(value)} sx={groupSx}><ToggleButton value="own">Own image</ToggleButton><ToggleButton value="sky">Sky survey</ToggleButton></ToggleButtonGroup>
      </Box>
      <Box sx={controlSx}>
        <Box id="messier-unimaged-style-label" sx={captionSx}>Not imaged as</Box>
        <ToggleButtonGroup aria-labelledby="messier-unimaged-style-label" exclusive value={props.unimagedStyle} onChange={(_, value) => value && props.onUnimagedStyle(value)} sx={groupSx}><ToggleButton value="sky">Sky survey</ToggleButton><ToggleButton value="blank">Blank</ToggleButton></ToggleButtonGroup>
      </Box>
      <Box sx={{ ...controlSx, width: 260, "@container (min-width: 950px) and (max-width: 1099.99px)": { width: 200 } }}>
        <Box id="messier-rig-field-label" sx={captionSx}>Rig field</Box>
        <FormControl size="small" sx={{ width: 240, "@container (min-width: 950px) and (max-width: 1099.99px)": { width: 200 } }}><Select id="messier-rig-field-select" labelId="messier-rig-field-label" value={props.rigId ?? "none"} onChange={(event) => props.onRig(event.target.value === "none" ? null : Number(event.target.value))} sx={{ height: 30, fontSize: 13, "& .MuiSelect-select": { py: "4px", pl: "10px", pr: "32px !important", overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" } }}><MenuItem value="none">No rig</MenuItem>{props.rigs.map((rig) => <MenuItem key={rig.id} value={rig.id}>{rig.name}</MenuItem>)}</Select></FormControl>
        {props.rigField && <Box sx={{ color: "text.secondary", fontSize: 11.5, lineHeight: 1.35 }}>Field {formatField(props.rigField.major, props.rigField.minor)}, centred on each picture</Box>}
        {props.rigUnavailable && <Box sx={{ color: "text.secondary", fontSize: 11.5, lineHeight: 1.35 }}>This rig's field can't be worked out: it needs a focal length and a camera.</Box>}
      </Box>
      <Box sx={{ display: "flex", alignItems: "center", minHeight: 50 }}>
        <FormControlLabel control={<Switch checked={props.showProjects} onChange={(event) => props.onShowProjects(event.target.checked)} size="small" />} label="Projects under images" sx={{ m: 0, "& .MuiFormControlLabel-label": { fontSize: 13, whiteSpace: "nowrap" } }} />
      </Box>
    </Box>
  );
}
