import Alert from "@mui/material/Alert";
import Button from "@mui/material/Button";

import { LOGIN_ERROR_TEXTS, type LoginErrorCode } from "../lib/login-errors";

export const RETRY_LABEL = "Reintentar";

// Why the last login did not finish (spec §14). Only a code of the allowlist gets here, and only
// its fixed text is shown. "Reintentar" (only `google_unavailable`, Q-127) is a full navigation to
// the same start: the login has to leave the page for Google, never a fetch.
export type LoginErrorAlertProps = Readonly<{ code: LoginErrorCode; retryHref: string }>;

export function LoginErrorAlert({ code, retryHref }: LoginErrorAlertProps) {
  const { message, severity, retry } = LOGIN_ERROR_TEXTS[code];
  return (
    <Alert
      severity={severity}
      action={
        retry ? (
          <Button color="inherit" size="small" component="a" href={retryHref}>
            {RETRY_LABEL}
          </Button>
        ) : undefined
      }
    >
      {message}
    </Alert>
  );
}
