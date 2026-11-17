import Box from "@mui/material/Box";
import Tooltip from "@mui/material/Tooltip";
import Typography from "@mui/material/Typography";
import { Link } from "react-router-dom";
import type { LatestPicture, YearSummary } from "@/api/home";
import { projectThumbnailUrl, renderedImageUrl } from "@/api/projects";
import { homeFramingSize, pickRendition } from "@/lib/galleryRendition";
import { displayConstellation } from "@/lib/constellations";
import { projectStatusLabel } from "@/lib/projectStatus";
import {
  formatDate,
  formatHoursMinutes,
  monthBars,
  yearSentence,
} from "@/lib/home";

function targetText(picture: LatestPicture): string | null {
  if (!picture.target_label) return null;
  return picture.constellation
    ? `${picture.target_label} in ${displayConstellation(picture.constellation)}`
    : picture.target_label;
}

function monthHours(minutes: number): string {
  return `${Number((minutes / 60).toFixed(1))} h`;
}

function LatestPicturePanel({
  picture,
  workspaceKey,
}: {
  picture: LatestPicture | null;
  workspaceKey: string;
}) {
  const target = picture ? targetText(picture) : null;
  const dpr = typeof window === "undefined" ? 1 : window.devicePixelRatio || 1;
  const framingSize = picture
    ? homeFramingSize(picture.crops, picture.image_id)
    : null;
  const framing = picture && framingSize ? picture.crops[framingSize] : null;
  return (
    <Box component="section">
      <Typography component="h2" sx={{ fontSize: 16, fontWeight: 600 }}>
        Latest picture
      </Typography>
      {!picture ? (
        <Typography sx={{ mt: "10px", color: "text.secondary", fontSize: 14 }}>
          No pictures yet. Add a picture to a project to see it here.
        </Typography>
      ) : (
        <Box
          component={Link}
          to={`/projects/${picture.project_id}`}
          sx={{ display: "block", position: "relative", overflow: "hidden", mt: "10px", borderRadius: "10px", bgcolor: "#000", color: "#f0eee9", textDecoration: "none" }}
        >
          <Box
            component="img"
            alt=""
            src={framingSize && framing
              ? projectThumbnailUrl(picture.project_id, framingSize, String(framing.id), workspaceKey)
              : renderedImageUrl(picture.project_id, picture.image_id, pickRendition(700, dpr), workspaceKey)}
            sx={{ display: "block", width: "100%", height: 340, objectFit: "cover" }}
          />
          <Box sx={{ position: "absolute", left: 0, right: 0, bottom: 0, p: "26px 14px 12px", background: "linear-gradient(transparent, rgba(0,0,0,0.78))", fontSize: 13 }}>
            <Typography component="strong" sx={{ display: "block", color: "inherit", fontSize: 16, fontWeight: 600 }}>
              {picture.project_name}
            </Typography>
            {target && <>{target}. </>}
            {projectStatusLabel(picture.status)}, {formatDate(picture.added)}.
          </Box>
        </Box>
      )}
    </Box>
  );
}

function YearPanel({ year }: { year: YearSummary }) {
  const sentence = yearSentence(year);
  const bars = monthBars(year.months);
  return (
    <Box component="section">
      <Typography component="h2" sx={{ fontSize: 16, fontWeight: 600 }}>
        The last 12 months
        <Typography component="span" sx={{ ml: 1, color: "text.secondary", fontSize: 13 }}>
          since {formatDate(year.since, { day: "numeric", month: "long", year: "numeric" })}
        </Typography>
      </Typography>
      {year.minutes > 0 ? (
        <Typography sx={{ mt: "8px", fontSize: 15, lineHeight: 1.55 }}>
          <Box component="strong" sx={{ fontWeight: 600 }}>{sentence.hours}</Box> of light frames across{" "}
          <Box component="strong" sx={{ fontWeight: 600 }}>{sentence.nights}</Box>, and{" "}
          <Box component="strong" sx={{ fontWeight: 600 }}>{sentence.pictures}</Box>.
        </Typography>
      ) : (
        <Typography sx={{ mt: "8px", color: "text.secondary", fontSize: 14 }}>
          No light frames in the last 12 months.
        </Typography>
      )}
      {year.best_night && (
        <Typography sx={{ mt: 1, fontSize: 14 }}>
          Your best night was {formatDate(year.best_night.date)}: {formatHoursMinutes(year.best_night.minutes)} of light frames on{" "}
          <Box component={Link} to={`/projects/${year.best_night.project_id}`} sx={{ color: "primary.main", textDecoration: "none" }}>
            {year.best_night.project_name}
          </Box>
          {year.best_night.other_projects > 0 && ` and ${year.best_night.other_projects} ${year.best_night.other_projects === 1 ? "other" : "others"}`}.
        </Typography>
      )}
      <Box
        role="group"
        aria-label="Light-frame hours by month for the last 12 months"
        sx={{ display: "grid", gridTemplateColumns: "repeat(12, minmax(0, 1fr))", gap: "5px", alignItems: "end", height: 74, mt: "12px" }}
      >
        {bars.map((bar) => (
          <Tooltip key={bar.label} title={`${bar.label}: ${monthHours(bar.minutes)}`} arrow>
            <Box role="img" aria-label={`${bar.label}: ${monthHours(bar.minutes)}`} sx={{ display: "flex", flexDirection: "column", alignItems: "center", justifyContent: "flex-end", height: "100%", color: "text.secondary", fontSize: 11 }}>
              <Box sx={{ width: "100%", maxWidth: 22, height: bar.heightPx, bgcolor: bar.empty ? "action.hover" : "primary.main", borderRadius: "2px 2px 0 0", mb: "4px" }} />
              {bar.initial}
            </Box>
          </Tooltip>
        ))}
      </Box>
    </Box>
  );
}

export function LatestAndYear({
  picture,
  year,
  workspaceKey,
}: {
  picture: LatestPicture | null;
  year: YearSummary;
  workspaceKey: string;
}) {
  return (
    <Box sx={{ display: "grid", gridTemplateColumns: "1fr", gap: "28px", mt: "34px", "@media (min-width: 1000px)": { gridTemplateColumns: "minmax(0, 1.35fr) minmax(0, 1fr)" } }}>
      <LatestPicturePanel picture={picture} workspaceKey={workspaceKey} />
      <YearPanel year={year} />
    </Box>
  );
}
