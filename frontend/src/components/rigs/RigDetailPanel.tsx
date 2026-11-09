import Box from "@mui/material/Box";
import Typography from "@mui/material/Typography";
import { useQuery } from "@tanstack/react-query";
import CalculatorPanel from "@/components/rigs/CalculatorPanel";
import EarlierSetupsList from "@/components/rigs/EarlierSetupsList";
import { fetchEquipmentOptions, fetchRigSetups, type Rig } from "@/api/rigs";

/**
 * Everything about one rig, opened by clicking its card.
 *
 * Deliberately thin: the heading and any warnings, then the tabbed panel. The
 * Equipment tab already lays out the whole rig — cameras, OTA, every filter
 * slot with its passbands and notes, mount, focuser, OAG, computer — so
 * summarising the same fields above it only produced two versions of the same
 * information, disagreeing in detail and format.
 */
export default function RigDetailPanel({
  rig,
  onCorrected,
}: {
  rig: Rig;
  onCorrected: () => void;
}) {
  const { data: setups = [] } = useQuery({
    queryKey: ["rig-setups", rig.id],
    queryFn: () => fetchRigSetups(rig.id),
  });
  const { data: options } = useQuery({
    queryKey: ["equipment-options"],
    queryFn: fetchEquipmentOptions,
  });

  return (
    <Box sx={{ pr: 4 }}>
      <Typography variant="h6" sx={{ mb: 0.25 }}>
        {rig.name}
      </Typography>
      {rig.description && (
        <Typography variant="body2" sx={{ color: "text.secondary", mb: 2 }}>
          {rig.description}
        </Typography>
      )}

      {rig.warnings.length > 0 && (
        <Box sx={{ mb: 2 }}>
          {rig.warnings.map((w, i) => (
            <Typography key={i} variant="body2" sx={{ color: "warning.main" }}>
              {w.message}
            </Typography>
          ))}
        </Box>
      )}

      <CalculatorPanel rig={rig} />
      {options && (
        <EarlierSetupsList
          rig={rig}
          setups={setups}
          options={options}
          onCorrected={onCorrected}
        />
      )}
    </Box>
  );
}
