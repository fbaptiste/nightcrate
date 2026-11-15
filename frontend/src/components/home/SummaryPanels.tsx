import Box from "@mui/material/Box";
import Typography from "@mui/material/Typography";
import { Link } from "react-router-dom";
import type { LocationSummary, RigSummary } from "@/api/home";
import { formatDate, formatPanelHours } from "@/lib/home";

type SummaryRow = {
  id: number;
  name: string;
  minutes: number;
  nights: number;
  lastUsed: string | null;
  activeProjects: number;
  isDefault?: boolean;
};

function detail(row: SummaryRow): string {
  if (!row.lastUsed) return "Not used yet";
  const used = `Last used ${formatDate(row.lastUsed)}`;
  if (row.activeProjects === 0) return used;
  return `${used}, by ${row.activeProjects} active ${row.activeProjects === 1 ? "project" : "projects"}`;
}

function SummaryPanel({
  title,
  allLabel,
  path,
  rows,
  empty,
}: {
  title: string;
  allLabel: string;
  path: string;
  rows: SummaryRow[];
  empty: string;
}) {
  return (
    <Box component="section">
      <Box sx={{ display: "flex", alignItems: "baseline", justifyContent: "space-between" }}>
        <Typography component="h2" sx={{ fontSize: 16, fontWeight: 600 }}>{title}</Typography>
        <Box component={Link} to={path} sx={{ color: "primary.main", fontSize: "13.5px", fontWeight: 500, textDecoration: "none" }}>
          {allLabel}
        </Box>
      </Box>
      <Box component="ul" sx={{ listStyle: "none", p: 0, m: "8px 0 0" }}>
        {rows.length === 0 ? (
          <Box component="li" sx={{ borderTop: 1, borderColor: "divider", p: "12px 6px", color: "text.secondary", fontSize: "13.5px" }}>{empty}</Box>
        ) : rows.map((row) => (
          <Box component="li" key={row.id} sx={{ borderTop: 1, borderColor: "divider" }}>
            <Box component={Link} to={`${path}?select=${row.id}`} sx={{ display: "grid", gridTemplateColumns: "minmax(0, 1fr) auto", gap: "2px 14px", p: "10px 6px", color: "inherit", textDecoration: "none", borderRadius: "6px", "&:hover": { bgcolor: "action.hover" } }}>
              <Typography sx={{ fontWeight: 600, fontSize: 14 }}>
                {row.name}
                {row.isDefault && <Box component="span" sx={{ ml: "6px", px: "7px", border: 1, borderColor: "divider", borderRadius: "9px", color: "text.secondary", fontSize: "11.5px", verticalAlign: "1px" }}>Default</Box>}
              </Typography>
              <Typography sx={{ gridColumn: 1, color: "text.secondary", fontSize: "12.5px" }}>{detail(row)}</Typography>
              <Typography sx={{ gridColumn: 2, gridRow: "1 / span 2", alignSelf: "center", textAlign: "right", fontSize: 13, fontVariantNumeric: "tabular-nums" }}>
                {formatPanelHours(row.minutes)}
                <Typography component="small" sx={{ display: "block", color: "text.secondary", fontSize: 12 }}>
                  {row.nights === 0 ? "No nights" : `${row.nights} ${row.nights === 1 ? "night" : "nights"}`}
                </Typography>
              </Typography>
            </Box>
          </Box>
        ))}
      </Box>
    </Box>
  );
}

export function SummaryPanels({ rigs, locations }: { rigs: RigSummary[]; locations: LocationSummary[] }) {
  const rigRows: SummaryRow[] = rigs.map((rig) => ({
    id: rig.rig_id,
    name: rig.name,
    minutes: rig.minutes,
    nights: rig.nights,
    lastUsed: rig.last_used,
    activeProjects: rig.active_projects,
  }));
  const locationRows: SummaryRow[] = locations.map((location) => ({
    id: location.location_id,
    name: location.name,
    minutes: location.minutes,
    nights: location.nights,
    lastUsed: location.last_used,
    activeProjects: location.active_projects,
    isDefault: location.is_default,
  }));
  return (
    <>
      <Box sx={{ display: "grid", gridTemplateColumns: "1fr", gap: "28px", mt: "40px", "@media (min-width: 1000px)": { gridTemplateColumns: "repeat(2, minmax(0, 1fr))" } }}>
        <SummaryPanel title="Rigs" allLabel="All rigs" path="/rigs" rows={rigRows} empty="No rigs yet." />
        <SummaryPanel title="Locations" allLabel="All locations" path="/locations" rows={locationRows} empty="No locations yet." />
      </Box>
      <Typography sx={{ mt: "8px", color: "text.secondary", fontSize: "12.5px" }}>
        Hours and nights are for the last 12 months. A location's figures count the projects set to it.
      </Typography>
    </>
  );
}
