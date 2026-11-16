"use client";

import Button from "@mui/material/Button";
import Paper from "@mui/material/Paper";
import Typography from "@mui/material/Typography";
import { useEffect, useState } from "react";

import type { LoginErrorCode } from "../lib/login-errors";
import { LoginErrorAlert } from "./LoginErrorAlert";

export const START_LABEL = "Ingresar con Google";
export const REDIRECTING_LABEL = "Redirigiendo a Google…";

// "Ingresar" (spec §14, design.md §3.4): one button, a plain link to the BFF's start route, so the
// browser navigates to it and from there to Google (the login cannot be a fetch). After the click
// it shows "Redirigiendo a Google…" and refuses a second click. Coming back with "Atrás" restores
// the page from the bfcache with that state frozen, so `pageshow` puts the button back.
export type LoginCardProps = Readonly<{ startHref: string; error: LoginErrorCode | null }>;

export function LoginCard({ startHref, error }: LoginCardProps) {
  const [redirecting, setRedirecting] = useState(false);

  useEffect(() => {
    const restore = (event: PageTransitionEvent) => {
      if (event.persisted) {
        setRedirecting(false);
      }
    };
    window.addEventListener("pageshow", restore);
    return () => window.removeEventListener("pageshow", restore);
  }, []);

  return (
    <main className="tw-flex tw-min-h-screen tw-items-center tw-justify-center tw-p-4">
      <Paper
        variant="outlined"
        className="tw-flex tw-w-full tw-max-w-sm tw-flex-col tw-gap-4 tw-p-6"
      >
        <div>
          <Typography variant="h5" component="h1">
            Ingresar
          </Typography>
          <Typography variant="body2" color="text.secondary">
            Centro de Pagos Universal
          </Typography>
        </div>
        {error === null ? null : <LoginErrorAlert code={error} retryHref={startHref} />}
        <Button
          variant="contained"
          size="large"
          component="a"
          href={startHref}
          loading={redirecting}
          loadingPosition="start"
          onClick={() => setRedirecting(true)}
        >
          {redirecting ? REDIRECTING_LABEL : START_LABEL}
        </Button>
      </Paper>
    </main>
  );
}
