"use client";

import Alert from "@mui/material/Alert";
import AlertTitle from "@mui/material/AlertTitle";
import Button from "@mui/material/Button";
import Paper from "@mui/material/Paper";
import Skeleton from "@mui/material/Skeleton";
import Typography from "@mui/material/Typography";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useRef, useState } from "react";

import { RETRY_LABEL } from "@/components/ErrorNotice";
import type { ApiError } from "@/lib/problem";

import { HOME_PATH } from "../context/ActiveOrgProvider";
import { type AcceptedInvitation } from "../hooks/useMyInvitations";
import { useAcceptInvitation } from "../hooks/useAcceptInvitation";
import { saveDefaultOrganization, writeTabOrganization } from "../lib/active-organization";
import { storeToken, takeInvitationToken } from "../lib/invitation-token";
import { roleLabel } from "../lib/role-labels";
import { PENDING_INVITATIONS_TEXTS } from "./PendingInvitationsNotice";

// "Aceptar invitación" (spec §14, RN-TEN-12, AC-TEN-17/18/19, design.md §3.9): the page of the
// link `/invitacion#token=<token>`. It takes the token out of the URL at once
// (lib/invitation-token.ts). Without a session it keeps the token in this tab's `sessionStorage`
// and goes to "Ingresar", which brings the person back here; with one it sends the token to
// `POST /api/invitations/accept/`. The invitation is shown as accepted only after the backend's
// `200`, with "Ir a la empresa", which picks that company for this tab. A refusal shows the fixed
// text of its state, from its `code` and `reason` (never `detail`, C-08); only a network or
// server failure offers "Reintentar"; every other refusal, and a link without token, offers "Ir a
// Inicio" (Q-233). The UI decides nothing: the backend checks the email, the expiry and the status
// of the organization. The role shows its label (Q-232).
// Texts: the states of spec §14 and design.md §3.9, in their words.
export const ACCEPT_INVITATION_TEXTS = {
  title: "Aceptar invitación",
  loading: "Cargando",
  accepted: "Invitación aceptada",
  expired: "Invitación vencida",
  revoked: "Invitación revocada",
  used: "Invitación ya usada",
  otherAccount: "Invitación para otra cuenta de Google",
  suspended: "Organización suspendida",
  notFound: "Invitación no encontrada",
  goToOrganization: PENDING_INVITATIONS_TEXTS.goToOrganization,
  goHome: "Ir a Inicio",
} as const;

export const INVITATION_PATH = "/invitacion";
// "Ingresar" comes back here: the path only, the token never travels in `return_to`.
export const LOGIN_FOR_INVITATION = `/login?${new URLSearchParams({ return_to: INVITATION_PATH })}`;

const REASON_TEXTS: ReadonlyMap<string, string> = new Map([
  ["expired", ACCEPT_INVITATION_TEXTS.expired],
  ["revoked", ACCEPT_INVITATION_TEXTS.revoked],
  ["used", ACCEPT_INVITATION_TEXTS.used],
  ["email_mismatch", ACCEPT_INVITATION_TEXTS.otherAccount],
  ["not_found", ACCEPT_INVITATION_TEXTS.notFound],
]);

// The text of a refusal. A code or a reason this screen does not know shows the fixed title of
// its code, as any other answer does (`already_member`, `validation_error`…).
export function refusalText(error: ApiError): string {
  if (error.code === "invitation_invalid" && error.reason !== undefined) {
    return REASON_TEXTS.get(error.reason) ?? error.title;
  }
  if (error.code === "organization_suspended") {
    return ACCEPT_INVITATION_TEXTS.suspended;
  }
  return error.title;
}

function isRetryable(error: ApiError): boolean {
  return error.status === 0 || error.status >= 500;
}

function Loading() {
  return (
    <div
      role="status"
      aria-busy="true"
      aria-label={ACCEPT_INVITATION_TEXTS.loading}
      className="tw-flex tw-flex-col tw-gap-2"
    >
      <Skeleton variant="rectangular" height={72} data-skeleton="state" />
      <Skeleton variant="rectangular" width="40%" height={36} data-skeleton="action" />
    </div>
  );
}

function Accepted({ result }: Readonly<{ result: AcceptedInvitation }>) {
  const router = useRouter();

  function goTo() {
    const organizationId = result.organization.id;
    writeTabOrganization(organizationId);
    saveDefaultOrganization(organizationId).catch(() => {
      // Only the default of new tabs is lost; this tab keeps its own value.
    });
    router.push(HOME_PATH);
  }

  return (
    <>
      <Alert severity="success">
        <AlertTitle>{ACCEPT_INVITATION_TEXTS.accepted}</AlertTitle>
        <div>{`${PENDING_INVITATIONS_TEXTS.organization}: ${result.organization.name}`}</div>
        <div>{`${PENDING_INVITATIONS_TEXTS.role}: ${roleLabel(result.role)}`}</div>
      </Alert>
      <Button variant="contained" onClick={goTo} className="tw-self-start">
        {ACCEPT_INVITATION_TEXTS.goToOrganization}
      </Button>
    </>
  );
}

type Refusal = Readonly<{ error: ApiError; onRetry: () => void; retrying: boolean }>;

// The way out of a refusal (Q-233): "Inicio". A person without a company is taken from there to
// "sin organización" by the provider, which lists their pending invitations.
function GoHome() {
  return (
    <Button component={Link} href={HOME_PATH} variant="contained" className="tw-self-start">
      {ACCEPT_INVITATION_TEXTS.goHome}
    </Button>
  );
}

function Refused({ error, onRetry, retrying }: Refusal) {
  if (isRetryable(error)) {
    return (
      <Alert
        severity="error"
        action={
          <Button color="inherit" size="small" onClick={onRetry} loading={retrying}>
            {RETRY_LABEL}
          </Button>
        }
      >
        {refusalText(error)}
      </Alert>
    );
  }
  return (
    <>
      <Alert severity="error">{refusalText(error)}</Alert>
      <GoHome />
    </>
  );
}

export type AcceptInvitationProps = Readonly<{
  // Whether the request brought the session cookie (read by the page on the server). Only a hint,
  // like the one of proxy.ts: a dead session answers `401` and the api-client goes to "Ingresar".
  hasSession: boolean;
}>;

export function AcceptInvitation({ hasSession }: AcceptInvitationProps) {
  const router = useRouter();
  const { mutate, data, error, isSuccess, isError, isPending } = useAcceptInvitation();
  // The token of this visit, for "Reintentar". It lives in the page's memory only.
  const tokenRef = useRef<string | null>(null);
  const startedRef = useRef(false);
  const [missing, setMissing] = useState(false);

  // The link is read once per visit, after hydration (the server never sees the fragment). The
  // read is a task the cleanup cancels, so a second run of the effect (Strict Mode) starts over
  // instead of finding the URL already without its fragment.
  useEffect(() => {
    if (startedRef.current) {
      return;
    }
    const start = window.setTimeout(() => {
      startedRef.current = true;
      const token = takeInvitationToken();
      if (token === null) {
        setMissing(true);
        return;
      }
      tokenRef.current = token;
      // Stored before anything else: "Ingresar", or a `401`, takes the person away from the page.
      storeToken(token);
      if (hasSession) {
        mutate(token);
      } else {
        router.replace(LOGIN_FOR_INVITATION);
      }
    }, 0);
    return () => window.clearTimeout(start);
  }, [hasSession, mutate, router]);

  function retry() {
    const token = tokenRef.current;
    if (token !== null) {
      storeToken(token);
      mutate(token);
    }
  }

  let body;
  if (missing) {
    body = (
      <>
        <Alert severity="error">{ACCEPT_INVITATION_TEXTS.notFound}</Alert>
        <GoHome />
      </>
    );
  } else if (isSuccess) {
    body = <Accepted result={data} />;
  } else if (isError && error.status !== 401) {
    body = <Refused error={error} onRetry={retry} retrying={isPending} />;
  } else {
    // Reading the link, sending it, or on the way to "Ingresar" (a `401` included).
    body = <Loading />;
  }

  return (
    <main className="tw-flex tw-min-h-screen tw-items-center tw-justify-center tw-p-4">
      <Paper
        variant="outlined"
        className="tw-flex tw-w-full tw-max-w-md tw-flex-col tw-gap-4 tw-p-6"
      >
        <Typography variant="h5" component="h1">
          {ACCEPT_INVITATION_TEXTS.title}
        </Typography>
        {body}
      </Paper>
    </main>
  );
}
