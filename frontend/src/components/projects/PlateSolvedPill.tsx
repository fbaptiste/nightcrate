import CheckCircleIcon from "@mui/icons-material/CheckCircle";
import RadioButtonUncheckedIcon from "@mui/icons-material/RadioButtonUnchecked";
import ButtonBase from "@mui/material/ButtonBase";
import Tooltip from "@mui/material/Tooltip";

interface Props {
  solvedAt: string | null;
  onOpen: () => void;
}

function formatSolvedDate(solvedAt: string): string {
  const calendarDate = new Date(`${solvedAt.slice(0, 10)}T12:00:00`);
  return calendarDate.toLocaleDateString(undefined, {
    year: "numeric",
    month: "short",
    day: "numeric",
  });
}

export default function PlateSolvedPill({ solvedAt, onOpen }: Props) {
  const solved = solvedAt !== null;
  const tooltip = solved
    ? `Plate solved on ${formatSolvedDate(solvedAt)}`
    : "Not plate solved yet";
  const Icon = solved ? CheckCircleIcon : RadioButtonUncheckedIcon;

  return (
    <Tooltip title={tooltip}>
      <ButtonBase
        onClick={onOpen}
        sx={(theme) => {
          const solvedBackground = theme.palette.mode === "dark" ? "#4db6ac" : "#00695c";
          const solvedText = theme.palette.mode === "dark" ? "#10201e" : "#ffffff";
          return {
            display: "inline-flex",
            alignItems: "center",
            gap: "6px",
            height: "26px",
            pl: "8px",
            pr: "12px",
            borderRadius: "13px",
            border: "1px solid",
            borderStyle: solved ? "solid" : "dashed",
            borderColor: solved ? "transparent" : "text.disabled",
            bgcolor: solved ? solvedBackground : "transparent",
            color: solved ? solvedText : "text.disabled",
            fontSize: "13px",
            fontWeight: solved ? 600 : 500,
            "&:hover": solved
              ? { bgcolor: solvedBackground }
              : { color: "text.secondary", borderColor: "text.secondary" },
          };
        }}
      >
        <Icon sx={{ fontSize: "16px" }} />
        Plate solved
      </ButtonBase>
    </Tooltip>
  );
}
