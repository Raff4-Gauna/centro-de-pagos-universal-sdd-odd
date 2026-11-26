"use client";

import PersonAddAlt from "@mui/icons-material/PersonAddAlt";
import Button from "@mui/material/Button";
import Tab from "@mui/material/Tab";
import Tabs from "@mui/material/Tabs";
import ToggleButton from "@mui/material/ToggleButton";
import ToggleButtonGroup from "@mui/material/ToggleButtonGroup";
import Typography from "@mui/material/Typography";
import { useId, useState } from "react";

import { useActiveOrganization } from "../context/ActiveOrgProvider";
import {
  allowedActionsOf,
  useCurrentOrganizationDetails,
} from "../hooks/useCurrentOrganizationDetails";
import { MEMBER_STATUSES, type MemberStatus } from "../hooks/useMembers";
import { ResendInvitationDialog, RevokeInvitationDialog } from "./InvitationDialogs";
import { InvitationsBody, type OpenInvitation } from "./InvitationsTable";
import { InviteDialog } from "./InviteDialog";
import { LeaveOrganizationDialog, RevokeMemberDialog } from "./MemberExitDialog";
import { MemberRoleDialog } from "./MemberRoleDialog";
import { MEMBERS_TEXTS, MembersBody, type OpenAction } from "./MembersTable";

// Configuración → Colaboradores (RF-TEN-04, RF-TEN-05, spec §14, design.md §3.9): the tabs
// "Miembros" (MembersTable.tsx) and "Invitaciones pendientes" (InvitationsTable.tsx), and
// "Invitar" (InviteDialog.tsx). "Invitar" shows only when the company's `allowed_actions` bring
// `invitation.create` and its `invitable_roles` are not empty; while they load or if they failed,
// it does not (fail closed). The backend checks every request again.
export const COLLABORATORS_TEXTS = {
  tabs: { members: "Miembros", invitations: "Invitaciones pendientes" },
  tabsLabel: "Colaboradores",
  invite: "Invitar",
} as const;

type CollaboratorsTab = keyof typeof COLLABORATORS_TEXTS.tabs;
const TABS: readonly CollaboratorsTab[] = ["members", "invitations"];

type Opened =
  | Readonly<{ kind: "member"; action: OpenAction }>
  | Readonly<{ kind: "invitation"; action: OpenInvitation }>
  | Readonly<{ kind: "invite" }>;

function InviteButton({
  organizationId,
  onInvite,
}: Readonly<{ organizationId: string | null; onInvite: () => void }>) {
  const details = useCurrentOrganizationDetails(organizationId);
  const canInvite =
    allowedActionsOf(details.data).has("invitation.create") &&
    (details.data?.invitable_roles.length ?? 0) > 0;
  if (!canInvite) {
    return null;
  }
  return (
    <Button variant="contained" startIcon={<PersonAddAlt />} onClick={onInvite}>
      {COLLABORATORS_TEXTS.invite}
    </Button>
  );
}

function MembersFilter({
  status,
  onChange,
}: Readonly<{ status: MemberStatus; onChange: (status: MemberStatus) => void }>) {
  return (
    <ToggleButtonGroup
      exclusive
      size="small"
      aria-label={MEMBERS_TEXTS.filterLabel}
      value={status}
      onChange={(_event, value: MemberStatus | null) => {
        if (value !== null) onChange(value);
      }}
      className="tw-self-start"
    >
      {MEMBER_STATUSES.map((value) => (
        <ToggleButton key={value} value={value}>
          {MEMBERS_TEXTS.filters[value]}
        </ToggleButton>
      ))}
    </ToggleButtonGroup>
  );
}

// The dialog open on the screen, if any: each one writes to the company it was opened for.
function OpenDialog({
  organizationId,
  opened,
  onClose,
}: Readonly<{ organizationId: string; opened: Opened; onClose: () => void }>) {
  const details = useCurrentOrganizationDetails(organizationId);
  if (opened.kind === "invite") {
    // The roles are the backend's for this person now; "Invitar" was offered only with some.
    const roles = details.data?.invitable_roles ?? [];
    return (
      <InviteDialog organizationId={organizationId} invitableRoles={roles} onClose={onClose} />
    );
  }
  if (opened.kind === "invitation") {
    const { invitation } = opened.action;
    const Dialog =
      opened.action.kind === "resend" ? ResendInvitationDialog : RevokeInvitationDialog;
    return <Dialog organizationId={organizationId} invitation={invitation} onClose={onClose} />;
  }
  const { kind, member } = opened.action;
  if (kind === "role") {
    return <MemberRoleDialog organizationId={organizationId} member={member} onClose={onClose} />;
  }
  if (kind === "revoke") {
    return <RevokeMemberDialog organizationId={organizationId} member={member} onClose={onClose} />;
  }
  return <LeaveOrganizationDialog organizationId={organizationId} onClose={onClose} />;
}

// The screen of one company: the tab, the filter and the open dialog live here, so they never
// outlive it. When the tab changes company this component is replaced (keyed by the company), so a
// dialog opened for A is gone, also if the tab later comes back to A, and with it an invitation
// link shown once (AC-TEN-24); a write never names a company the screen no longer shows.
function CompanyCollaborators({ organizationId }: Readonly<{ organizationId: string | null }>) {
  const idPrefix = useId();
  const [tab, setTab] = useState<CollaboratorsTab>("members");
  const [status, setStatus] = useState<MemberStatus>("active");
  const [opened, setOpened] = useState<Opened | null>(null);
  const tabId = (value: CollaboratorsTab) => `${idPrefix}-tab-${value}`;
  const panelId = `${idPrefix}-panel`;
  return (
    <div className="tw-flex tw-flex-col tw-gap-4">
      <div className="tw-flex tw-flex-wrap tw-items-center tw-justify-between tw-gap-3">
        <Typography component="h1" variant="h5">
          {MEMBERS_TEXTS.title}
        </Typography>
        <InviteButton
          organizationId={organizationId}
          onInvite={() => setOpened({ kind: "invite" })}
        />
      </div>
      <Tabs
        value={tab}
        onChange={(_event, value: CollaboratorsTab) => setTab(value)}
        aria-label={COLLABORATORS_TEXTS.tabsLabel}
      >
        {TABS.map((value) => (
          <Tab
            key={value}
            value={value}
            id={tabId(value)}
            aria-controls={panelId}
            label={COLLABORATORS_TEXTS.tabs[value]}
          />
        ))}
      </Tabs>
      <div
        role="tabpanel"
        id={panelId}
        aria-labelledby={tabId(tab)}
        className="tw-flex tw-flex-col tw-gap-4"
      >
        {tab === "members" ? (
          <>
            <MembersFilter status={status} onChange={setStatus} />
            <MembersBody
              organizationId={organizationId}
              status={status}
              onOpen={(action) => setOpened({ kind: "member", action })}
            />
          </>
        ) : (
          <InvitationsBody
            organizationId={organizationId}
            onOpen={(action) => setOpened({ kind: "invitation", action })}
          />
        )}
      </div>
      {organizationId !== null && opened !== null ? (
        <OpenDialog
          organizationId={organizationId}
          opened={opened}
          onClose={() => setOpened(null)}
        />
      ) : null}
    </div>
  );
}

export function MembersScreen() {
  const { organizationId } = useActiveOrganization();
  return <CompanyCollaborators key={organizationId ?? ""} organizationId={organizationId} />;
}
