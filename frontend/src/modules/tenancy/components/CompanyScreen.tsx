"use client";

import Alert from "@mui/material/Alert";
import Button from "@mui/material/Button";
import Paper from "@mui/material/Paper";
import Skeleton from "@mui/material/Skeleton";
import Typography from "@mui/material/Typography";
import { useId, useState } from "react";

import { EmptyState } from "@/components/EmptyState";
import { ErrorNotice, RETRY_LABEL } from "@/components/ErrorNotice";

import { useActiveOrganization } from "../context/ActiveOrgProvider";
import {
  allowedActionsOf,
  type CurrentOrganizationDetails,
  useCurrentOrganizationDetails,
} from "../hooks/useCurrentOrganizationDetails";
import { COMPANY_FIELDS } from "../lib/company-form";
import { CompanyDataForm } from "./CompanyDataForm";
import { LeaveOrganizationDialog } from "./MemberExitDialog";

// Configuración → Datos de la empresa (RF-TEN-03, RF-TEN-04, spec §14, design.md §3.9): every role
// reads the company's name, legal name, CUIT and time zone (`GET /api/organizations/current/`).
// The form shows only if the company's `allowed_actions` bring `org.update` (owner and admin, never
// while it is suspended): the UI hides, the backend decides. Until those actions are known, or if
// rereading them failed, the data is read-only. "Abandonar la empresa" shows with `member.leave`
// (every role, also while suspended, Q-221). States: loading (skeleton), error ("Reintentar"), no
// permission (`403`); a field not informed reads "—". Everything below the title belongs to the
// company it was built for (`key={organizationId}`): switching company discards the form and the
// dialog, so a write never names a company the screen no longer shows.
export const COMPANY_TEXTS = {
  title: "Datos de la empresa",
  labels: { name: "Nombre", legal_name: "Razón social", tax_id: "CUIT", timezone: "Zona horaria" },
  missing: "—",
  loading: "Cargando los datos de la empresa",
  forbidden: "No tenés permiso para ver los datos de la empresa",
  stale: "No se pudieron actualizar los datos de la empresa.",
  leaveTitle: "Abandonar la empresa",
  leaveText:
    "Dejás de ver esta empresa y todo lo que tiene. Para volver necesitás una invitación nueva.",
  leave: "Abandonar la empresa",
} as const;

export function CompanyDataView({ details }: Readonly<{ details: CurrentOrganizationDetails }>) {
  return (
    <dl className="tw-m-0 tw-grid tw-grid-cols-1 tw-gap-x-6 tw-gap-y-3 sm:tw-grid-cols-[max-content_1fr]">
      {COMPANY_FIELDS.map((field) => (
        <div key={field} className="tw-contents">
          <Typography component="dt" variant="body2" color="text.secondary">
            {COMPANY_TEXTS.labels[field]}
          </Typography>
          <Typography component="dd" variant="body1" className="tw-m-0">
            {details[field] || COMPANY_TEXTS.missing}
          </Typography>
        </div>
      ))}
    </dl>
  );
}

function CompanySkeleton() {
  return (
    <div
      role="status"
      aria-busy="true"
      aria-label={COMPANY_TEXTS.loading}
      className="tw-flex tw-flex-col tw-gap-3"
    >
      {COMPANY_FIELDS.map((field) => (
        <Skeleton key={field} variant="rectangular" height={56} data-skeleton="field" />
      ))}
    </div>
  );
}

function CompanyPanel({
  organizationId,
  details,
  canEdit,
  canLeave,
}: Readonly<{
  organizationId: string;
  details: CurrentOrganizationDetails;
  canEdit: boolean;
  canLeave: boolean;
}>) {
  const leaveId = useId();
  const [leaving, setLeaving] = useState(false);
  return (
    <>
      <Paper variant="outlined" className="tw-p-4">
        {canEdit ? (
          <CompanyDataForm organizationId={organizationId} details={details} />
        ) : (
          <CompanyDataView details={details} />
        )}
      </Paper>
      {canLeave ? (
        <section aria-labelledby={leaveId} className="tw-flex tw-flex-col tw-items-start tw-gap-2">
          <Typography id={leaveId} component="h2" variant="h6">
            {COMPANY_TEXTS.leaveTitle}
          </Typography>
          <Typography variant="body2" color="text.secondary">
            {COMPANY_TEXTS.leaveText}
          </Typography>
          <Button variant="outlined" color="error" onClick={() => setLeaving(true)}>
            {COMPANY_TEXTS.leave}
          </Button>
        </section>
      ) : null}
      {leaving ? (
        <LeaveOrganizationDialog
          organizationId={organizationId}
          onClose={() => setLeaving(false)}
        />
      ) : null}
    </>
  );
}

function CompanyBody({ organizationId }: Readonly<{ organizationId: string | null }>) {
  const details = useCurrentOrganizationDetails(organizationId);
  if (organizationId === null || details.isPending) {
    return <CompanySkeleton />;
  }
  if (details.data === undefined) {
    return details.error.status === 403 ? (
      <EmptyState title={COMPANY_TEXTS.forbidden} />
    ) : (
      <ErrorNotice
        message={details.error.title}
        onRetry={() => void details.refetch()}
        retrying={details.isFetching}
      />
    );
  }
  // A failed reread keeps the data it had, read-only: the actions it brought may be gone.
  const fresh = !details.isError;
  const allowed = allowedActionsOf(fresh ? details.data : undefined);
  return (
    <>
      {fresh ? null : (
        <Alert
          severity="warning"
          action={
            <Button
              color="inherit"
              size="small"
              onClick={() => void details.refetch()}
              loading={details.isFetching}
            >
              {RETRY_LABEL}
            </Button>
          }
        >
          {COMPANY_TEXTS.stale}
        </Alert>
      )}
      <CompanyPanel
        key={organizationId}
        organizationId={organizationId}
        details={details.data}
        canEdit={allowed.has("org.update")}
        canLeave={allowed.has("member.leave")}
      />
    </>
  );
}

export function CompanyScreen() {
  const { organizationId } = useActiveOrganization();
  return (
    <div className="tw-flex tw-max-w-2xl tw-flex-col tw-gap-4">
      <Typography component="h1" variant="h5">
        {COMPANY_TEXTS.title}
      </Typography>
      <CompanyBody organizationId={organizationId} />
    </div>
  );
}
