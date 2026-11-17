import { Component, type ReactNode } from "react";
import { isRouteErrorResponse, useRouteError } from "react-router-dom";
import Box from "@mui/material/Box";
import Button from "@mui/material/Button";
import Paper from "@mui/material/Paper";
import Typography from "@mui/material/Typography";

function errorMessage(error: unknown): string {
  if (error instanceof Error) return error.message || "Something went wrong.";
  if (isRouteErrorResponse(error)) {
    if (typeof error.data === "string" && error.data) return error.data;
    if (
      typeof error.data === "object"
      && error.data !== null
      && "message" in error.data
      && typeof error.data.message === "string"
    ) {
      return error.data.message;
    }
    return error.statusText || `Request failed (${error.status}).`;
  }
  return typeof error === "string" && error ? error : "Something went wrong.";
}

function errorDetails(error: unknown): string {
  if (error instanceof Error) return error.stack ?? error.toString();
  try {
    return JSON.stringify(error, null, 2) ?? String(error);
  } catch {
    return String(error);
  }
}

export function PageErrorPanel({
  error,
  onReload,
}: {
  error: unknown;
  onReload?: () => void;
}) {
  const reload = onReload ?? (() => window.location.reload());
  return (
    <Box sx={{ flex: 1, display: "flex", alignItems: "center", justifyContent: "center", p: 3 }}>
      <Paper variant="outlined" sx={{ width: "100%", maxWidth: 640, p: 3 }}>
        <Typography variant="h5" component="h1" gutterBottom>
          This page ran into a problem
        </Typography>
        <Typography color="text.secondary" sx={{ mb: 2 }}>
          {errorMessage(error)}
        </Typography>
        <Button variant="contained" onClick={reload}>
          Reload
        </Button>
        <Box component="details" sx={{ mt: 2 }}>
          <Box component="summary" sx={{ cursor: "pointer", color: "text.secondary" }}>
            Details
          </Box>
          <Box
            component="pre"
            sx={{ mt: 1, mb: 0, p: 1.5, overflow: "auto", bgcolor: "action.hover", whiteSpace: "pre-wrap" }}
          >
            {errorDetails(error)}
          </Box>
        </Box>
      </Paper>
    </Box>
  );
}

export function RouteErrorPage() {
  return <PageErrorPanel error={useRouteError()} />;
}

interface PageErrorBoundaryProps {
  children: ReactNode;
  resetKey?: string;
}

interface PageErrorBoundaryState {
  error: unknown | null;
}

export class PageErrorBoundary extends Component<
  PageErrorBoundaryProps,
  PageErrorBoundaryState
> {
  state: PageErrorBoundaryState = { error: null };

  static getDerivedStateFromError(error: unknown): PageErrorBoundaryState {
    return { error };
  }

  componentDidUpdate(previousProps: PageErrorBoundaryProps) {
    if (this.state.error !== null && previousProps.resetKey !== this.props.resetKey) {
      this.setState({ error: null });
    }
  }

  render() {
    return this.state.error === null
      ? this.props.children
      : <PageErrorPanel error={this.state.error} />;
  }
}
