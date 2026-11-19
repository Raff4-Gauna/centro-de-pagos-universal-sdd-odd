"use client";

import Button from "@mui/material/Button";
import Chip from "@mui/material/Chip";
import Paper from "@mui/material/Paper";
import Skeleton from "@mui/material/Skeleton";
import Table from "@mui/material/Table";
import TableBody from "@mui/material/TableBody";
import TableCell from "@mui/material/TableCell";
import TableContainer from "@mui/material/TableContainer";
import TableHead from "@mui/material/TableHead";
import TableRow from "@mui/material/TableRow";
import Typography from "@mui/material/Typography";
import { useId, useState } from "react";

import { EmptyState } from "@/components/EmptyState";
import { ErrorNotice } from "@/components/ErrorNotice";

import { type Session, useSessions } from "../hooks/useSessions";
import { formatDateTime } from "../lib/format-dates";
import { RevokeOthersDialog } from "./RevokeOthersDialog";
import { RevokeSessionDialog } from "./RevokeSessionDialog";

// "Seguridad" (RF-IDA-07, AC-IDA-33, spec §14, design.md §3.4, 07 §5.3): the person's own active
// sessions with browser · OS, start and last use (es-AR, Buenos Aires time), the current one
// marked, and no IP nor password (Q-113). Each row closes its session after a confirmation; the
// current one through the BFF logout. "Cerrar las demás" is disabled when there is no other.
// Texts: spec §14, design.md §3.4 and Q-129 a). Session ids never reach the page: not in the URL,
// not in the DOM, not in a log.
export const SECURITY_TEXTS = {
  title: "Seguridad",
  device: "Dispositivo",
  started: "Iniciada",
  lastUsed: "Último uso",
  actions: "Acciones",
  current: "Esta sesión",
  revoke: "Cerrar sesión",
  revokeCurrent: "Cerrar esta sesión",
  revokeOthers: "Cerrar las demás",
  unknownBrowser: "Navegador desconocido",
  unknownOs: "Sistema desconocido",
  empty: "No hay sesiones activas",
  loading: "Cargando",
} as const;

export const SESSIONS_SKELETON_ROWS = 5;

function orUnknown(value: string | null, unknown: string): string {
  const trimmed = value?.trim();
  return trimmed ? trimmed : unknown;
}

export function deviceLabel(session: Pick<Session, "browser" | "os">): string {
  const browser = orUnknown(session.browser, SECURITY_TEXTS.unknownBrowser);
  const os = orUnknown(session.os, SECURITY_TEXTS.unknownOs);
  return `${browser} · ${os}`;
}

function SessionsSkeleton() {
  return (
    <div
      role="status"
      aria-busy="true"
      aria-label={SECURITY_TEXTS.loading}
      className="tw-flex tw-flex-col tw-gap-6 tw-p-4"
    >
      <Skeleton variant="text" width="35%" height={40} data-skeleton="title" />
      <div className="tw-flex tw-flex-col tw-gap-2">
        <Skeleton variant="rectangular" height={56} data-skeleton="header" />
        {Array.from({ length: SESSIONS_SKELETON_ROWS }, (_, index) => (
          <Skeleton key={index} variant="rectangular" height={52} data-skeleton="row" />
        ))}
      </div>
    </div>
  );
}

function SessionRow({
  session,
  onRevoke,
}: Readonly<{ session: Session; onRevoke: (session: Session) => void }>) {
  // The action buttons repeat their label on every row: the device cell describes each one.
  const deviceId = useId();
  return (
    <TableRow>
      <TableCell>
        <div className="tw-flex tw-flex-wrap tw-items-center tw-gap-2">
          <span id={deviceId}>{deviceLabel(session)}</span>
          {session.is_current ? (
            <Chip size="small" color="primary" label={SECURITY_TEXTS.current} />
          ) : null}
        </div>
      </TableCell>
      <TableCell>{formatDateTime(session.created_at)}</TableCell>
      <TableCell>{formatDateTime(session.last_used_at)}</TableCell>
      <TableCell align="right">
        <Button size="small" aria-describedby={deviceId} onClick={() => onRevoke(session)}>
          {session.is_current ? SECURITY_TEXTS.revokeCurrent : SECURITY_TEXTS.revoke}
        </Button>
      </TableCell>
    </TableRow>
  );
}

export function SessionsTable({
  sessions,
  onRevoke,
}: Readonly<{ sessions: readonly Session[]; onRevoke: (session: Session) => void }>) {
  return (
    <TableContainer component={Paper} variant="outlined">
      <Table size="small">
        <TableHead>
          <TableRow>
            <TableCell>{SECURITY_TEXTS.device}</TableCell>
            <TableCell>{SECURITY_TEXTS.started}</TableCell>
            <TableCell>{SECURITY_TEXTS.lastUsed}</TableCell>
            <TableCell align="right">
              <span className="tw-sr-only">{SECURITY_TEXTS.actions}</span>
            </TableCell>
          </TableRow>
        </TableHead>
        <TableBody>
          {sessions.map((session) => (
            // A React key, never rendered: the id does not reach the DOM.
            <SessionRow key={session.id} session={session} onRevoke={onRevoke} />
          ))}
        </TableBody>
      </Table>
    </TableContainer>
  );
}

function SessionsContent({ sessions }: Readonly<{ sessions: readonly Session[] }>) {
  const [target, setTarget] = useState<Session | null>(null);
  const [othersOpen, setOthersOpen] = useState(false);
  if (sessions.length === 0) {
    return <EmptyState title={SECURITY_TEXTS.empty} />;
  }
  const hasOthers = sessions.some((session) => !session.is_current);
  return (
    <>
      <div className="tw-flex tw-justify-end">
        <Button variant="outlined" disabled={!hasOthers} onClick={() => setOthersOpen(true)}>
          {SECURITY_TEXTS.revokeOthers}
        </Button>
      </div>
      <SessionsTable sessions={sessions} onRevoke={setTarget} />
      {target ? (
        <RevokeSessionDialog
          session={target}
          device={deviceLabel(target)}
          onClose={() => setTarget(null)}
        />
      ) : null}
      {othersOpen ? <RevokeOthersDialog onClose={() => setOthersOpen(false)} /> : null}
    </>
  );
}

export function SecurityScreen() {
  const sessions = useSessions();
  if (sessions.isPending) {
    return <SessionsSkeleton />;
  }
  return (
    <div className="tw-flex tw-flex-col tw-gap-4">
      <Typography component="h1" variant="h5">
        {SECURITY_TEXTS.title}
      </Typography>
      {sessions.isError ? (
        <ErrorNotice
          message={sessions.error.title}
          onRetry={() => void sessions.refetch()}
          retrying={sessions.isFetching}
        />
      ) : (
        <SessionsContent sessions={sessions.data} />
      )}
    </div>
  );
}
