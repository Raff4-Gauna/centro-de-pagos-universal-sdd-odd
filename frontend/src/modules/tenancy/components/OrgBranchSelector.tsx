"use client";

import Alert from "@mui/material/Alert";
import Button from "@mui/material/Button";
import Chip from "@mui/material/Chip";
import MenuItem from "@mui/material/MenuItem";
import Skeleton from "@mui/material/Skeleton";
import TextField from "@mui/material/TextField";

import { RETRY_LABEL } from "@/components/ErrorNotice";
import type { ApiError } from "@/lib/problem";

import { useActiveOrganization } from "../context/ActiveOrgProvider";
import { useOrganizations } from "../hooks/useOrganizations";
import type { MyOrganization } from "../lib/active-organization";

// Company and branch selector of the top bar (spec §14, 07 §5.1, design.md §3.9). "Empresa" lists
// the person's companies (RF-TEN-02) and marks a `suspended` one with a "Suspendida" chip; the
// choice is the tab's and travels as `X-Organization-Id`, it authorizes nothing (RN-TEN-03).
// "Sucursal" is a filter (`branch_id` on the screens that filter): until the active branches reach
// the shell (`GET /api/branches/`, RF-TEN-06), it only offers "Todas las sucursales", which is
// what a change of company resets it to. States: loading (skeletons), error ("Reintentar"), no
// company (empty and disabled; ActiveOrgProvider sends the person to "sin organización").
export const SELECTOR_GROUP_LABEL = "Empresa y sucursal";
export const ORGANIZATION_LABEL = "Empresa";
export const BRANCH_LABEL = "Sucursal";
export const ALL_BRANCHES_LABEL = "Todas las sucursales";
export const SUSPENDED_CHIP_LABEL = "Suspendida";
const ORGANIZATION_SELECT_ID = "org-selector";
const BRANCH_SELECT_ID = "branch-selector";
const ALL_BRANCHES = "all";
const FIELD_CLASS = "tw-w-36 sm:tw-w-52";

function OrganizationLabel({ organization }: Readonly<{ organization: MyOrganization }>) {
  return (
    <span className="tw-flex tw-min-w-0 tw-items-center tw-gap-1">
      <span className="tw-truncate">{organization.name}</span>
      {organization.status === "suspended" ? (
        <Chip size="small" color="warning" label={SUSPENDED_CHIP_LABEL} />
      ) : null}
    </span>
  );
}

function OrganizationSelect({
  organizations,
  value,
  onSelect,
}: Readonly<{
  organizations: readonly MyOrganization[];
  value: string | null;
  onSelect: (organizationId: string) => void;
}>) {
  const byId = new Map(organizations.map((organization) => [organization.id, organization]));
  return (
    <TextField
      id={ORGANIZATION_SELECT_ID}
      select
      size="small"
      label={ORGANIZATION_LABEL}
      value={value ?? ""}
      disabled={organizations.length === 0}
      onChange={(event) => onSelect(event.target.value)}
      className={FIELD_CLASS}
      slotProps={{
        select: {
          renderValue: (selected) => {
            const organization = byId.get(String(selected));
            return organization ? <OrganizationLabel organization={organization} /> : null;
          },
        },
      }}
    >
      {organizations.length === 0 ? <MenuItem value="" /> : null}
      {organizations.map((organization) => (
        <MenuItem key={organization.id} value={organization.id}>
          <OrganizationLabel organization={organization} />
        </MenuItem>
      ))}
    </TextField>
  );
}

function BranchSelect() {
  return (
    <TextField
      id={BRANCH_SELECT_ID}
      select
      disabled
      size="small"
      label={BRANCH_LABEL}
      value={ALL_BRANCHES}
      className={FIELD_CLASS}
    >
      <MenuItem value={ALL_BRANCHES}>{ALL_BRANCHES_LABEL}</MenuItem>
    </TextField>
  );
}

function OrganizationsError({
  error,
  onRetry,
  retrying,
}: Readonly<{ error: ApiError; onRetry: () => void; retrying: boolean }>) {
  return (
    <Alert
      severity="error"
      variant="outlined"
      className="tw-py-0"
      action={
        <Button color="inherit" size="small" onClick={onRetry} loading={retrying}>
          {RETRY_LABEL}
        </Button>
      }
    >
      {error.title}
    </Alert>
  );
}

function SelectSkeleton() {
  return <Skeleton variant="rounded" height={40} className={FIELD_CLASS} />;
}

export function OrgBranchSelector() {
  const organizations = useOrganizations();
  const { organizationId, selectOrganization } = useActiveOrganization();

  let content;
  if (organizations.isPending) {
    content = (
      <>
        <SelectSkeleton />
        <SelectSkeleton />
      </>
    );
  } else if (organizations.isError) {
    content = (
      <OrganizationsError
        error={organizations.error}
        onRetry={() => void organizations.refetch()}
        retrying={organizations.isFetching}
      />
    );
  } else {
    content = (
      <>
        <OrganizationSelect
          organizations={organizations.data}
          value={organizationId}
          onSelect={selectOrganization}
        />
        <BranchSelect />
      </>
    );
  }

  return (
    <div
      role="group"
      aria-label={SELECTOR_GROUP_LABEL}
      aria-busy={organizations.isPending}
      className="tw-flex tw-items-center tw-gap-2"
    >
      {content}
    </div>
  );
}
