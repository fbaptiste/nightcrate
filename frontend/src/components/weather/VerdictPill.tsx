import Box from "@mui/material/Box";
import type { Verdict } from "@/api/weather";
import { weatherPalette } from "@/lib/weatherPalette";
import { GO_MARK } from "@/lib/weatherVerdict";

const CONTENT: Record<Verdict, { icon: string; label: string }> = {
  go: { icon: GO_MARK, label: "Go" },
  uncertain: { icon: "?", label: "Uncertain" },
  no: { icon: "✕", label: "No" },
  not_enough_data: { icon: "–", label: "Not enough data" },
  night_over: { icon: "", label: "Night over" },
};

export default function VerdictPill({
  verdict,
  size = "medium",
  notCurrent = false,
}: {
  verdict: Verdict;
  size?: "small" | "medium";
  notCurrent?: boolean;
}) {
  const content = CONTENT[verdict];
  const small = size === "small";
  return (
    <Box
      component="span"
      sx={(theme) => {
        const p = weatherPalette(theme);
        const outlined = notCurrent || verdict === "uncertain" || verdict === "not_enough_data";
        return {
          display: "inline-flex",
          alignItems: "center",
          gap: 0.75,
          width: "fit-content",
          maxWidth: "100%",
          borderRadius: 99,
          // Outlined pills lose 2px to the border; keep every pill the same height.
          px: outlined ? (small ? "7px" : "9px") : small ? "9px" : "11px",
          py: outlined ? (small ? "0px" : "1px") : small ? "2px" : "3px",
          fontSize: small ? "0.8125rem" : "0.875rem",
          lineHeight: 1.45,
          fontWeight: 700,
          whiteSpace: notCurrent ? "normal" : "nowrap",
          textAlign: "center",
          ...(!notCurrent && verdict === "go" && { color: p.onClearCell, backgroundColor: p.clearCell }),
          ...(!notCurrent && verdict === "uncertain" && { color: p.uncertain, border: `2px solid ${p.uncertain}` }),
          ...(!notCurrent && verdict === "no" && { color: p.onNo, backgroundColor: p.noGround }),
          ...(!notCurrent && verdict === "not_enough_data" && {
            color: p.neutralText,
            border: `2px dashed ${p.neutralText}`,
          }),
          ...(!notCurrent && verdict === "night_over" && { color: p.neutralText, px: 0 }),
          ...(notCurrent && {
            color: p.neutralText,
            border: `2px solid ${p.unknownBorder}`,
          }),
        };
      }}
    >
      {!notCurrent && content.icon && <span aria-hidden="true">{content.icon}</span>}
      {notCurrent ? `Last result: ${content.label} — not current` : content.label}
    </Box>
  );
}
