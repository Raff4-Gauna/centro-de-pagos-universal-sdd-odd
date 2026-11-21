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
import ToggleButton from "@mui/material/ToggleButton";
import ToggleButtonGroup from "@mui/material/ToggleButtonGroup";
import Typography from "@mui/material/Typography";
import { useId, useState } from "react";

import { EmptyState } from "@/components/EmptyState";
import { ErrorNotice } from "@/components/ErrorNotice";
import { formatDateTime } from "@/modules/identity/lib/format-dates";
import type { components } from "@/types/api";

import { useActiveOrganization } from "../context/ActiveOrgProvider";
import { MEMBER_STATUSES, type Member, type MemberStatus, useMembers } from "../hooks/useMembers";
import { roleLabel } from "../lib/role-labels";
import { LeaveOrganizationDialog, RevokeMemberDialog } from "./MemberExitDialog";
import { MemberRoleDialog } from "./MemberRoleDialog";

// Configuración → Colaboradores, members (RF-TEN-04, spec §14, design.md §3.9): the people of the
// active company with their name, email, role (Q-232 labels) and since when, active or ended
// (`?status=`). Only owner and admin list them (Q-218): anyone else gets `403` and the screen says
// so (AC-TEN-34). Each row offers only what its own `allowed_actions` and `assignable_roles` bring
// (change role, revoke someone else's access, leave on one's own row): the UI hides, the backend
// decides. The pending invitations belong to T-TEN-35. States: loading (skeleton rows), error
// ("Reintentar"), no permission (`403`), empty (per filter).
export type EndedReason = components["schemas"]["EndedReasonEnum"];

export const MEMBERS_TEXTS = {
  title: "Colaboradores",
  filterLabel: "Mostrar",
  filters: { active: "Activos", revoked: "Dados de baja" },
  name: "Nombre",
  email: "Email",
  role: "Rol",
  since: "Desde",
  ended: "Baja",
  actions: "Acciones",
  changeRole: "Cambiar rol",
  revoke: "Revocar acceso",
  leave: "Abandonar la empresa",
  endedReasons: { revoked: "Revocado", left: "Abandonó" } satisfies Record<EndedReason, string>,
  missing: "—",
  loading: "Cargando colaboradores",
  emptyActive: "Aún no hay colaboradores",
  emptyRevoked: "No hay colaboradores dados de baja",
  forbidden: "No tenés permiso para ver los colaboradores",
} as const;

export const MEMBERS_SKELETON_ROWS = 5;

type MemberAction = "role" | "revoke" | "leave";
type OpenAction = Readonly<{ kind: MemberAction; member: Member }>;

function MemberRow({
  member,
  hasActions,
  showEnded,
  onOpen,
}: Readonly<{
  member: Member;
  hasActions: boolean;
  showEnded: boolean;
  onOpen: (action: OpenAction) => void;
}>) {
  // The action buttons repeat their label on every row: the name cell describes each one.
  const nameId = useId();
  const allowed = new Set(member.allowed_actions);
  const canChangeRole = allowed.has("member.change_role") && member.assignable_roles.length > 0;
  const button = (kind: MemberAction, label: string, danger: boolean) => (
    <Button
      size="small"
      color={danger ? "error" : "primary"}
      aria-describedby={nameId}
      onClick={() => onOpen({ kind, member })}
    >
      {label}
    </Button>
  );
  return (
    <TableRow>
      <TableCell id={nameId}>{member.user.name || MEMBERS_TEXTS.missing}</TableCell>
      <TableCell>{member.user.email}</TableCell>
      <TableCell>
        <Chip size="small" variant="outlined" label={roleLabel(member.role)} />
      </TableCell>
      <TableCell>{formatDateTime(member.created_at)}</TableCell>
      {showEnded ? (
        <TableCell>
          {member.ended_reason === null
            ? MEMBERS_TEXTS.missing
            : MEMBERS_TEXTS.endedReasons[member.ended_reason]}
        </TableCell>
      ) : null}
      {hasActions ? (
        <TableCell align="right" className="tw-whitespace-nowrap">
          {canChangeRole ? button("role", MEMBERS_TEXTS.changeRole, false) : null}
          {allowed.has("member.revoke") ? button("revoke", MEMBERS_TEXTS.revoke, true) : null}
          {allowed.has("member.leave") ? button("leave", MEMBERS_TEXTS.leave, true) : null}
        </TableCell>
      ) : null}
    </TableRow>
  );
}

export function MembersTable({
  members,
  showEnded,
  onOpen,
}: Readonly<{
  members: readonly Member[];
  showEnded: boolean;
  onOpen: (action: OpenAction) => void;
}>) {
  const hasActions = members.some(({ allowed_actions }) => allowed_actions.length > 0);
  return (
    <TableContainer component={Paper} variant="outlined">
      <Table size="small">
        <TableHead>
          <TableRow>
            <TableCell>{MEMBERS_TEXTS.name}</TableCell>
            <TableCell>{MEMBERS_TEXTS.email}</TableCell>
            <TableCell>{MEMBERS_TEXTS.role}</TableCell>
            <TableCell>{MEMBERS_TEXTS.since}</TableCell>
            {showEnded ? <TableCell>{MEMBERS_TEXTS.ended}</TableCell> : null}
            {hasActions ? (
              <TableCell align="right">
                <span className="tw-sr-only">{MEMBERS_TEXTS.actions}</span>
              </TableCell>
            ) : null}
          </TableRow>
        </TableHead>
        <TableBody>
          {members.map((member) => (
            <MemberRow
              key={member.id}
              member={member}
              hasActions={hasActions}
              showEnded={showEnded}
              onOpen={onOpen}
            />
          ))}
        </TableBody>
      </Table>
    </TableContainer>
  );
}

function MembersSkeleton() {
  return (
    <div
      role="status"
      aria-busy="true"
      aria-label={MEMBERS_TEXTS.loading}
      className="tw-flex tw-flex-col tw-gap-2"
    >
      <Skeleton variant="rectangular" height={56} data-skeleton="header" />
      {Array.from({ length: MEMBERS_SKELETON_ROWS }, (_, index) => (
        <Skeleton key={index} variant="rectangular" height={52} data-skeleton="row" />
      ))}
    </div>
  );
}

function MembersBody({
  organizationId,
  status,
  onOpen,
}: Readonly<{
  organizationId: string | null;
  status: MemberStatus;
  onOpen: (action: OpenAction) => void;
}>) {
  const members = useMembers(organizationId, status);
  if (members.isPending) {
    return <MembersSkeleton />;
  }
  if (members.isError) {
    return members.error.status === 403 ? (
      <EmptyState title={MEMBERS_TEXTS.forbidden} />
    ) : (
      <ErrorNotice
        message={members.error.title}
        onRetry={() => void members.refetch()}
        retrying={members.isFetching}
      />
    );
  }
  if (members.data.length === 0) {
    const title = status === "active" ? MEMBERS_TEXTS.emptyActive : MEMBERS_TEXTS.emptyRevoked;
    return <EmptyState title={title} />;
  }
  // An ended membership brings no actions: the backend gives it none.
  return <MembersTable members={members.data} showEnded={status === "revoked"} onOpen={onOpen} />;
}

// The screen of one company: the filter and the open dialog live here, so they never outlive it.
// When the tab changes company this component is replaced (keyed by the company), so a dialog
// opened for A is gone, also if the tab later comes back to A, and a write never names a company
// the screen no longer shows.
function CompanyMembers({ organizationId }: Readonly<{ organizationId: string | null }>) {
  const [status, setStatus] = useState<MemberStatus>("active");
  const [opened, setOpened] = useState<OpenAction | null>(null);
  const close = () => setOpened(null);
  return (
    <div className="tw-flex tw-flex-col tw-gap-4">
      <div className="tw-flex tw-flex-wrap tw-items-center tw-justify-between tw-gap-3">
        <Typography component="h1" variant="h5">
          {MEMBERS_TEXTS.title}
        </Typography>
        <ToggleButtonGroup
          exclusive
          size="small"
          aria-label={MEMBERS_TEXTS.filterLabel}
          value={status}
          onChange={(_event, value: MemberStatus | null) => {
            if (value !== null) setStatus(value);
          }}
        >
          {MEMBER_STATUSES.map((value) => (
            <ToggleButton key={value} value={value}>
              {MEMBERS_TEXTS.filters[value]}
            </ToggleButton>
          ))}
        </ToggleButtonGroup>
      </div>
      <MembersBody organizationId={organizationId} status={status} onOpen={setOpened} />
      {organizationId !== null && opened?.kind === "role" ? (
        <MemberRoleDialog organizationId={organizationId} member={opened.member} onClose={close} />
      ) : null}
      {organizationId !== null && opened?.kind === "revoke" ? (
        <RevokeMemberDialog
          organizationId={organizationId}
          member={opened.member}
          onClose={close}
        />
      ) : null}
      {organizationId !== null && opened?.kind === "leave" ? (
        <LeaveOrganizationDialog
          organizationId={organizationId}
          member={opened.member}
          onClose={close}
        />
      ) : null}
    </div>
  );
}

export function MembersScreen() {
  const { organizationId } = useActiveOrganization();
  return <CompanyMembers key={organizationId ?? ""} organizationId={organizationId} />;
}
