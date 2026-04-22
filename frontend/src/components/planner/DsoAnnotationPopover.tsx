/**
 * Popover shown when the user clicks a DSO annotation in the FOV
 * simulator. Fetches full DSO detail on mount (no prefetch — most
 * users won't click every label) and shows a curated summary: common
 * name, primary + Messier/NGC/IC cross-refs, object type.
 *
 * A "Show details" button hands control up the chain via
 * ``onSelectDso`` — the parent page swaps the detail dialog to the
 * clicked DSO, preserving the user's rig + location preview.
 */
import { useQuery } from "@tanstack/react-query";
import Box from "@mui/material/Box";
import Button from "@mui/material/Button";
import Chip from "@mui/material/Chip";
import CircularProgress from "@mui/material/CircularProgress";
import Divider from "@mui/material/Divider";
import Popover from "@mui/material/Popover";
import Stack from "@mui/material/Stack";
import Typography from "@mui/material/Typography";
import { fetchDso, type DsoDetail } from "@/api/dsos";
import { displayDsoType, dsoTypeColor } from "@/lib/dsoTypeNames";

interface Props {
  anchorEl: Element | null;
  dsoId: number | null;
  fallbackDesignation: string;
  fallbackObjType: string | null;
  onClose: () => void;
  onSelectDso: (id: number) => void;
}

// Curated catalogs — those worth showing in a one-glance popover.
// Rest (PGC / UGC / MCG / 2MASS / HD / etc.) are elided — too many,
// too noisy, and users asking for full designations can "Show
// details" to see everything.
const CURATED_CATALOGS = new Set(["M", "NGC", "IC"]);

function curatedDesignations(detail: DsoDetail): string[] {
  const seen = new Set<string>();
  const out: string[] = [];
  // Primary first, whatever catalog it's in.
  if (detail.primary_designation) {
    out.push(detail.primary_designation);
    seen.add(detail.primary_designation);
  }
  for (const d of detail.designations ?? []) {
    if (!CURATED_CATALOGS.has(d.catalog)) continue;
    if (seen.has(d.display_form)) continue;
    out.push(d.display_form);
    seen.add(d.display_form);
  }
  return out;
}

export default function DsoAnnotationPopover({
  anchorEl,
  dsoId,
  fallbackDesignation,
  fallbackObjType,
  onClose,
  onSelectDso,
}: Props) {
  const open = anchorEl != null && dsoId != null;

  const detailQuery = useQuery({
    queryKey: ["dso", dsoId],
    queryFn: () => fetchDso(dsoId as number),
    enabled: open,
    staleTime: 5 * 60_000,
  });

  const detail = detailQuery.data;
  const designations = detail ? curatedDesignations(detail) : [fallbackDesignation];
  const objType = detail?.obj_type ?? fallbackObjType;
  const commonName = detail?.common_name ?? null;

  return (
    <Popover
      open={open}
      anchorEl={anchorEl}
      onClose={onClose}
      anchorOrigin={{ vertical: "bottom", horizontal: "center" }}
      transformOrigin={{ vertical: "top", horizontal: "center" }}
      disableRestoreFocus
    >
      <Box sx={{ p: 1.5, minWidth: 220, maxWidth: 300 }}>
        {/* Catalog designation(s) with the object-type pill inline —
            same visual language as the detail panel header. */}
        <Stack direction="row" gap={0.75} alignItems="center" flexWrap="wrap">
          {designations.map((d) => (
            <Typography
              key={d}
              variant="body2"
              sx={{ fontFamily: "monospace", fontSize: "0.85rem", fontWeight: 600 }}
            >
              {d}
            </Typography>
          ))}
          {objType && (
            <Chip
              label={displayDsoType(objType)}
              size="small"
              sx={{
                bgcolor: dsoTypeColor(objType),
                color: "#ffffff",
                fontWeight: 500,
                height: 20,
                fontSize: "0.7rem",
              }}
            />
          )}
        </Stack>

        {commonName && (
          <Typography
            variant="body2"
            color="text.secondary"
            sx={{ mt: 0.5, lineHeight: 1.3 }}
          >
            {commonName}
          </Typography>
        )}

        {detailQuery.isLoading && (
          <Box sx={{ display: "flex", justifyContent: "center", mt: 1 }}>
            <CircularProgress size={16} />
          </Box>
        )}

        <Divider sx={{ my: 1.25 }} />
        <Button
          size="small"
          fullWidth
          variant="outlined"
          onClick={() => {
            if (dsoId != null) onSelectDso(dsoId);
            onClose();
          }}
        >
          Switch to object
        </Button>
      </Box>
    </Popover>
  );
}
