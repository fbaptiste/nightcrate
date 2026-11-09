import Box from "@mui/material/Box";
import ButtonBase from "@mui/material/ButtonBase";

interface Props {
  solvedAt: string | null;
  objectCount?: number;
  onOpen: () => void;
}

function formatSolvedDate(solvedAt: string): string {
  const dateOnly = solvedAt.slice(0, 10);
  const [year, month, day] = dateOnly.split("-").map(Number);
  return new Intl.DateTimeFormat("en-GB", {
    day: "numeric",
    month: "short",
    year: "numeric",
    timeZone: "UTC",
  }).format(new Date(Date.UTC(year, month - 1, day)));
}

export default function PlateSolveLine({ solvedAt, objectCount, onOpen }: Props) {
  const solved = solvedAt !== null;

  return (
    <ButtonBase
      onClick={onOpen}
      sx={(theme) => {
        const teal = theme.palette.mode === "dark" ? "#4db6ac" : "#00695c";
        const tealText = theme.palette.mode === "dark" ? "#10201e" : "#ffffff";
        const fieldOutline = theme.palette.mode === "dark"
          ? "rgba(255,255,255,0.23)"
          : "#c4c1bb";
        return {
          display: "flex",
          width: "100%",
          alignItems: "center",
          gap: "10px",
          mt: "10px",
          px: "12px",
          py: "8px",
          borderRadius: "8px",
          border: solved ? "1px solid transparent" : `1px dashed ${fieldOutline}`,
          bgcolor: solved ? `color-mix(in srgb, ${teal} 12%, transparent)` : "transparent",
          textAlign: "left",
          fontSize: "13px",
          lineHeight: 1.45,
          "&:hover": {
            bgcolor: solved
              ? `color-mix(in srgb, ${teal} 18%, transparent)`
              : "action.hover",
          },
          "& .solve-mark": {
            width: "20px",
            height: "20px",
            flex: "0 0 20px",
            display: "grid",
            placeItems: "center",
            borderRadius: "50%",
            border: solved ? 0 : `1.5px dashed ${theme.palette.text.disabled}`,
            bgcolor: solved ? teal : "transparent",
            color: solved ? tealText : "transparent",
            fontSize: "12px",
            fontWeight: 700,
          },
        };
      }}
    >
      <Box className="solve-mark" component="span" aria-hidden="true">
        {solved ? "✓" : ""}
      </Box>
      <Box component="span" sx={{ minWidth: 0 }}>
        {solved ? (
          <>
            <Box component="strong" sx={{ fontWeight: 600 }}>
              Plate solved
            </Box>{" "}
            on {formatSolvedDate(solvedAt)}
            {objectCount !== undefined
              ? `: ${objectCount.toLocaleString()} catalog objects in the image`
              : ""}
          </>
        ) : (
          "Not plate solved yet"
        )}
      </Box>
      <Box
        component="span"
        sx={{ ml: "auto", color: "primary.main", whiteSpace: "nowrap" }}
      >
        Open
      </Box>
    </ButtonBase>
  );
}
