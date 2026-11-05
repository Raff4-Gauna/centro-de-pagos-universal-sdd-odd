"use client";

import Alert from "@mui/material/Alert";
import AlertTitle from "@mui/material/AlertTitle";
import Button from "@mui/material/Button";

// Recoverable error (07 §2): an MUI Alert whose "Reintentar" repeats the same request through
// `onRetry` (a query's refetch, or `reset` in a route's error.tsx). Never a silent console.error.
export type ErrorNoticeProps = Readonly<{
  message: string;
  onRetry: () => void;
  title?: string;
  retrying?: boolean;
}>;

export const DEFAULT_ERROR_TITLE = "No se pudo cargar";
export const RETRY_LABEL = "Reintentar";

export function ErrorNotice({
  message,
  onRetry,
  title = DEFAULT_ERROR_TITLE,
  retrying = false,
}: ErrorNoticeProps) {
  return (
    <Alert
      severity="error"
      className="tw-m-4"
      action={
        <Button color="inherit" size="small" onClick={onRetry} loading={retrying}>
          {RETRY_LABEL}
        </Button>
      }
    >
      <AlertTitle>{title}</AlertTitle>
      {message}
    </Alert>
  );
}
