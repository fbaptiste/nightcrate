import Button from "@mui/material/Button";
import ArrowBackIcon from "@mui/icons-material/ArrowBack";
import { useNavigate, useSearchParams } from "react-router-dom";

function validReturnPath(value: string | null): value is string {
  return value !== null && value.startsWith("/") && !value.startsWith("//") && !value.includes("://") && !value.includes("\\");
}

export default function BackToPlateSolve() {
  const navigate = useNavigate();
  const [searchParams] = useSearchParams();
  const returnTo = searchParams.get("returnTo");

  if (!validReturnPath(returnTo)) return null;

  return (
    <Button
      variant="contained"
      startIcon={<ArrowBackIcon />}
      onClick={() => navigate(returnTo)}
      sx={{ mb: 2 }}
    >
      Back to plate solve
    </Button>
  );
}
