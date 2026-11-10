import { useEffect, useRef, useState, type RefObject } from "react";
import Box from "@mui/material/Box";
import Button from "@mui/material/Button";
import IconButton from "@mui/material/IconButton";
import CheckIcon from "@mui/icons-material/Check";
import ChevronLeftIcon from "@mui/icons-material/ChevronLeft";
import ChevronRightIcon from "@mui/icons-material/ChevronRight";
import { Link, useNavigate } from "react-router-dom";
import { useTheme } from "@mui/material/styles";
import type { MessierRig, MessierSlot, SlotProject } from "@/api/messier";
import type { MessierView } from "@/api/settings";
import type { CropSize } from "@/api/projects";
import FlipTile from "@/components/common/FlipTile";
import NameWithAlternates from "@/components/common/NameWithAlternates";
import ExpandButton from "@/components/gallery/ExpandButton";
import GalleryImage from "@/components/gallery/GalleryImage";
import { displayConstellation } from "@/lib/constellations";
import { displayDsoType } from "@/lib/dsoTypeNames";
import { tileImageUrl } from "@/lib/galleryRendition";
import { fovGeometry } from "@/lib/messierFov";
import { formatDateRange } from "@/lib/messierFormat";
import type { SurveyRequestQueue } from "@/lib/surveyRequestQueue";
import MessierSkyImage from "./MessierSkyImage";
import RigFieldBox from "./RigFieldBox";

interface Props {
  slot: MessierSlot;
  view: MessierView;
  ws: string;
  trackWidth: number;
  rig: MessierRig | null;
  imagedStyle: "own" | "sky";
  unimagedStyle: "sky" | "blank";
  showProjects: boolean;
  shownProjectIndex: number;
  onShownProjectIndex: (index: number) => void;
  active: boolean;
  requestKey: number;
  scrollRootRef: RefObject<HTMLDivElement | null>;
  requestQueue: SurveyRequestQueue;
  locationName: string | null;
  turned: boolean;
  onTurn: (next: boolean) => void;
  onExpand: () => void;
  expandRefs: RefObject<Map<string, HTMLButtonElement>>;
}

function objectSummary(slot: MessierSlot): string {
  if (!slot.object) return "Not in your catalog data";
  return `${displayDsoType(slot.object.obj_type)}${slot.object.constellation ? ` in ${displayConstellation(slot.object.constellation)}` : ""}`;
}

function projectDates(project: SlotProject): string {
  return formatDateRange(project.first_date, project.last_date);
}

function BlankSurface({ number, view }: { number: number; view: MessierView }) {
  const fontSize = view === "small" ? 44 : view === "medium" ? 72 : 112;
  return <Box sx={{ position: "absolute", inset: 0, display: "grid", placeItems: "center", bgcolor: (theme) => theme.palette.mode === "dark" ? "#202327" : "#ebe9e5", border: "1.5px dashed", borderColor: (theme) => theme.palette.mode === "dark" ? "#4a4d54" : "#c4c1bb", borderRadius: "6px", color: (theme) => theme.palette.mode === "dark" ? "#3f434a" : "#bdb8b0", fontSize, fontWeight: 600, letterSpacing: "-0.02em" }}>{number}</Box>;
}

function Cross() {
  return <Box component="svg" viewBox="0 0 100 100" preserveAspectRatio="none" aria-hidden sx={{ position: "absolute", inset: 0, width: "100%", height: "100%", pointerEvents: "none" }}><line x1="0" y1="0" x2="100" y2="100" /><line x1="100" y1="0" x2="0" y2="100" /><style>{"line{stroke:#ffffff;stroke-opacity:.45;stroke-width:1.5px;vector-effect:non-scaling-stroke}"}</style></Box>;
}

export default function MessierTile(props: Props) {
  const { slot, view, rig } = props;
  const theme = useTheme();
  const navigate = useNavigate();
  const frontRef = useRef<HTMLButtonElement>(null);
  const backRef = useRef<HTMLButtonElement>(null);
  const expandRef = useRef<HTMLButtonElement>(null);
  const [surveyReady, setSurveyReady] = useState(false);
  const object = slot.object;
  const imageProjects = slot.projects.filter((project) => project.main_image_id != null);
  const shownIndex = Math.min(props.shownProjectIndex, Math.max(0, imageProjects.length - 1));
  const shownProject = imageProjects[shownIndex] ?? null;
  const cropSize = view as CropSize;
  const small = view === "small";
  const rigShape = rig?.fov_major_deg != null && rig.fov_minor_deg != null ? { majorDeg: rig.fov_major_deg, minorDeg: rig.fov_minor_deg } : null;
  const skyStyle = (slot.state === "imaged" && props.imagedStyle === "sky") || (slot.state !== "imaged" && props.unimagedStyle === "sky");
  const showSky = Boolean(object && slot.survey && skyStyle);
  const ownPicture = shownProject?.picture_fields?.[cropSize];
  const surveyPicture = slot.survey ? { widthDeg: slot.survey.field_deg, heightDeg: slot.survey.field_deg * 0.75 } : null;
  const picture = skyStyle ? surveyPicture : ownPicture ? { widthDeg: ownPicture.width_deg, heightDeg: ownPicture.height_deg } : null;
  const geometry = picture && rigShape ? fovGeometry(picture, rigShape) : null;

  useEffect(() => {
    const registered = props.expandRefs.current;
    const button = expandRef.current;
    const key = `m${slot.number}`;
    if (button) registered.set(key, button);
    return () => { if (registered.get(key) === button) registered.delete(key); };
  }, [props.expandRefs, slot.number]);

  const src = shownProject ? tileImageUrl(shownProject, cropSize, props.trackWidth, window.devicePixelRatio || 1, props.ws) : null;
  const designation = object?.designation ?? `M ${slot.number}`;
  const label = object?.common_name ? `${designation} ${object.common_name}` : designation;
  const teal = theme.palette.mode === "dark" ? "#4db6ac" : "#00695c";

  const front = (
    <Box sx={{ position: "relative", width: "100%", height: "100%", overflow: "hidden", borderRadius: "6px", bgcolor: "#000000" }}>
      <Box ref={frontRef} component="button" type="button" aria-label={`Show details for ${designation}`} onClick={() => props.onTurn(true)} sx={{ position: "absolute", inset: 0, width: "100%", height: "100%", p: 0, border: 0, bgcolor: "transparent", cursor: "pointer", borderRadius: "6px", "&:focus-visible": { outlineOffset: "-3px" } }}>
        {skyStyle || !shownProject ? <BlankSurface number={slot.number} view={view} /> : (
          src ? <Box sx={{ position: "absolute", left: "50%", top: "50%", width: `${100 / (geometry?.scale ?? 1)}%`, height: `${100 / (geometry?.scale ?? 1)}%`, transform: "translate(-50%, -50%)" }}><GalleryImage src={src} alt={label} /></Box> : <Box sx={{ display: "grid", placeItems: "center", height: "100%", color: "#8e8c88", fontSize: 13 }}>No main image</Box>
        )}
        {showSky && surveyReady && <Box sx={{ position: "absolute", inset: 0, bgcolor: "#000000" }} />}
        {showSky && object && slot.survey && <MessierSkyImage dsoId={object.dso_id} ws={props.ws} renderKey={slot.survey.render_key} active={props.active} requestKey={props.requestKey} messierNumber={slot.number} scrollRootRef={props.scrollRootRef} requestQueue={props.requestQueue} alt={label} scale={geometry?.scale} onReadyChange={setSurveyReady} />}
      </Box>
      {showSky && surveyReady && slot.state !== "imaged" && <Cross />}
      {showSky && surveyReady && <Box sx={{ position: "absolute", right: small ? 6 : 8, bottom: small ? 5 : 7, fontSize: small ? 9.5 : 10.5, color: "rgba(255, 255, 255, 0.72)", pointerEvents: "none", textShadow: "0 0 3px #000000, 0 0 6px #000000" }}>Sky survey</Box>}
      {rigShape && ((showSky && surveyReady) || (!skyStyle && shownProject)) && <RigFieldBox picture={picture} rig={rigShape} showUnknown={!skyStyle && Boolean(shownProject)} small={small} />}
      {slot.state === "imaged" && <Box aria-label="Imaged" sx={{ position: "absolute", top: 8, left: 8, width: 26, height: 26, borderRadius: "50%", bgcolor: "rgba(0, 0, 0, 0.62)", border: "1px solid rgba(255, 255, 255, 0.28)", display: "grid", placeItems: "center", pointerEvents: "none" }}><CheckIcon sx={{ width: 16, height: 16, color: teal }} /></Box>}
      {slot.state === "project" && <Box sx={{ position: "absolute", left: small ? 6 : 8, bottom: small ? 6 : 8, maxWidth: "calc(100% - 16px)", height: small ? 22 : 24, px: small ? "8px" : "10px", borderRadius: 12, display: "inline-flex", alignItems: "center", bgcolor: showSky && surveyReady ? "rgba(0, 0, 0, 0.66)" : "background.paper", border: "1px solid", borderColor: showSky && surveyReady ? "rgba(255, 255, 255, 0.32)" : "divider", color: showSky && surveyReady ? "#ffffff" : "text.primary", fontSize: small ? 11 : 11.5, fontWeight: 600, pointerEvents: "none" }}>Project, no image yet</Box>}
      {shownProject && <ExpandButton buttonRef={expandRef} label={`View ${designation} full size`} onClick={props.onExpand} size={small ? "compact" : "regular"} />}
      {!skyStyle && imageProjects.length >= 2 && <>
        <IconButton aria-label="Previous project's image" title={imageProjects[shownIndex - 1]?.name ?? ""} disabled={shownIndex === 0} onClick={(event) => { event.stopPropagation(); props.onShownProjectIndex(shownIndex - 1); }} sx={{ position: "absolute", left: 8, top: "50%", transform: "translateY(-50%)", width: small ? 26 : 32, height: small ? 26 : 32, color: "#ffffff", bgcolor: "rgba(0, 0, 0, 0.55)", border: "1px solid rgba(255, 255, 255, 0.32)", "&:hover": { bgcolor: "rgba(0, 0, 0, 0.75)" }, "&.Mui-disabled": { color: "#ffffff", opacity: 0.3 } }}><ChevronLeftIcon sx={{ fontSize: small ? 18 : 22 }} /></IconButton>
        <IconButton aria-label="Next project's image" title={imageProjects[shownIndex + 1]?.name ?? ""} disabled={shownIndex === imageProjects.length - 1} onClick={(event) => { event.stopPropagation(); props.onShownProjectIndex(shownIndex + 1); }} sx={{ position: "absolute", right: 8, top: "50%", transform: "translateY(-50%)", width: small ? 26 : 32, height: small ? 26 : 32, color: "#ffffff", bgcolor: "rgba(0, 0, 0, 0.55)", border: "1px solid rgba(255, 255, 255, 0.32)", "&:hover": { bgcolor: "rgba(0, 0, 0, 0.75)" }, "&.Mui-disabled": { color: "#ffffff", opacity: 0.3 } }}><ChevronRightIcon sx={{ fontSize: small ? 18 : 22 }} /></IconButton>
        <Box sx={{ position: "absolute", left: "50%", bottom: small ? 6 : 8, transform: "translateX(-50%)", height: small ? 20 : 22, px: "9px", borderRadius: 11, display: "inline-flex", alignItems: "center", bgcolor: "rgba(0, 0, 0, 0.6)", border: "1px solid rgba(255, 255, 255, 0.28)", color: "#ffffff", fontSize: small ? 11 : 11.5, fontWeight: 600, pointerEvents: "none" }}>{shownIndex + 1} / {imageProjects.length}</Box>
      </>}
    </Box>
  );

  const facts = object ? [object.mag_v != null ? `mag ${object.mag_v.toFixed(1)}` : null, object.maj_axis_arcmin != null ? `${object.maj_axis_arcmin >= 10 ? object.maj_axis_arcmin.toFixed(0) : object.maj_axis_arcmin.toFixed(1)}′${object.min_axis_arcmin != null && object.min_axis_arcmin !== object.maj_axis_arcmin ? ` × ${object.min_axis_arcmin >= 10 ? object.min_axis_arcmin.toFixed(0) : object.min_axis_arcmin.toFixed(1)}′` : ""}` : null].filter(Boolean).join(" · ") : "";
  const back = (
    <Box onClick={(event) => { if (!(event.target as HTMLElement).closest("a,button")) props.onTurn(false); }} sx={{ position: "relative", width: "100%", height: "100%", bgcolor: "background.paper", border: 1, borderColor: "divider", borderRadius: "6px", display: "flex", flexDirection: "column", overflow: "hidden", cursor: "pointer" }}>
      <Box ref={backRef} component="button" type="button" aria-label={`Show image for ${designation}`} onClick={() => props.onTurn(false)} sx={{ position: "absolute", inset: 0, p: 0, border: 0, bgcolor: "transparent", cursor: "pointer", borderRadius: "6px", "&:focus-visible": { outlineOffset: "-3px" } }} />
      <Box sx={{ position: "relative", zIndex: 1, flex: 1, minHeight: 0, overflowY: "auto", scrollbarWidth: "none", "&::-webkit-scrollbar": { display: "none" }, p: small ? "10px 10px 4px" : "14px 16px 6px", fontSize: small ? 12 : 13, maskImage: "linear-gradient(to bottom, #000000 calc(100% - 22px), transparent)" }}>
        {!small && <Box sx={{ color: "text.secondary", mb: "10px" }}><Box sx={{ color: "text.primary", fontWeight: 600 }}>{objectSummary(slot)}</Box>{facts && <Box>{facts}</Box>}{slot.never_rises && props.locationName && <Box>Never rises at {props.locationName}</Box>}</Box>}
        {slot.object == null ? <Box sx={{ color: "text.secondary", fontStyle: "italic" }}>Not in your catalog data</Box> : <>
          <Box sx={{ color: "text.secondary", fontSize: 12, mb: "4px" }}>{slot.projects.length <= 1 ? "Project" : "Projects"}</Box>
          {slot.projects.length ? slot.projects.map((project) => <Box key={project.project_id} sx={{ mb: "6px", lineHeight: 1.35 }}><Box component={Link} to={`/projects/${project.project_id}`} onClick={(event) => event.stopPropagation()} sx={{ position: "relative", zIndex: 2, color: "primary.main", fontWeight: 600, textDecoration: "none", "&:hover": { textDecoration: "underline" } }}>{project.name}</Box><Box sx={{ color: "text.secondary", fontSize: 12.5 }}>{projectDates(project)}</Box>{project.main_image_id == null && <Box sx={{ color: theme.palette.mode === "dark" ? "#f0a35e" : "#b85500", fontSize: 12.5, fontWeight: 600 }}>No image yet</Box>}</Box>) : <Box sx={{ color: "text.secondary", fontStyle: "italic" }}>No project yet</Box>}
          {!small && slot.number === 102 && <Box sx={{ mt: 1, pl: 1, borderLeft: 2, borderColor: "divider", color: "text.secondary", fontSize: 12 }}>NightCrate uses NGC 5866 for M 102. Its historical identity is disputed; some lists identify it with M 101.</Box>}
        </>}
      </Box>
      {object && <Box sx={{ position: "relative", zIndex: 2, flex: "none", p: "6px 10px 10px", borderTop: 1, borderColor: "divider", display: "flex", justifyContent: "flex-end" }}><Button size="small" onClick={(event) => { event.stopPropagation(); navigate(`/planner?object=${object.dso_id}`); }}>Open in Planner</Button></Box>}
    </Box>
  );

  return (
    <Box sx={{ minWidth: 0 }}>
      <FlipTile turned={props.turned} onTurn={props.onTurn} front={front} back={back} frontButtonRef={frontRef} backButtonRef={backRef} />
      <Box sx={{ pt: "7px", px: "2px", minWidth: 0 }}>
        <Box sx={{ whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis" }}><Box component="span" sx={{ fontWeight: 600, mr: "6px" }}>{designation}</Box>{object?.common_name && <NameWithAlternates name={object.common_name} otherNames={object.other_names}><Box component="span" sx={{ color: "text.secondary" }}>{object.common_name}</Box></NameWithAlternates>}</Box>
        <Box sx={{ whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis", color: slot.never_rises ? "text.primary" : "text.secondary", fontSize: 12.5 }}>{slot.never_rises && props.locationName ? `↧ Never rises at ${props.locationName}` : objectSummary(slot)}</Box>
        {props.showProjects && slot.projects.length > 0 && <Box sx={{ mt: "6px", pt: "6px", borderTop: 1, borderColor: "divider", fontSize: small ? 12 : 12.5 }}>{slot.projects.map((project) => { const isShown = props.imagedStyle === "own" && slot.projects.length > 1 && project.project_id === shownProject?.project_id; return <Box key={project.project_id} sx={{ display: small ? "block" : "flex", alignItems: "baseline", gap: "10px", minWidth: 0, lineHeight: small ? 1.35 : 1.6, mb: small ? "4px" : 0 }}><Box component={Link} to={`/projects/${project.project_id}`} title={`Open project: ${project.name}`} sx={{ display: small ? "block" : "inline", minWidth: 0, whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis", fontWeight: 600, textDecoration: "none", color: "primary.main", "&:hover": { textDecoration: "underline" }, "&::before": isShown ? { content: '""', display: "inline-block", width: 7, height: 7, borderRadius: "50%", bgcolor: teal, mr: "6px", verticalAlign: "1px" } : undefined }}>{project.name}</Box><Box sx={{ display: small ? "block" : "inline", flex: "0 0 auto", ml: small ? 0 : "auto", color: "text.secondary", whiteSpace: "nowrap" }}>{projectDates(project)}</Box></Box>; })}</Box>}
      </Box>
    </Box>
  );
}
