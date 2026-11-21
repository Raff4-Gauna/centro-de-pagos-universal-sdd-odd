"use client";

import Alert from "@mui/material/Alert";
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
import { ErrorNotice, RETRY_LABEL } from "@/components/ErrorNotice";

import { useActiveOrganization } from "../context/ActiveOrgProvider";
import {
  BRANCH_FILTERS,
  type Branch,
  type BranchFilter,
  type BranchTransition,
  useBranches,
} from "../hooks/useBranches";
import {
  allowedActionsOf,
  useCurrentOrganizationDetails,
} from "../hooks/useCurrentOrganizationDetails";
import { BranchFormDialog } from "./BranchFormDialog";
import { BranchStatusDialog } from "./BranchStatusDialog";

// Configuración → Sucursales (RF-TEN-06, spec §14, design.md §3.9): every branch of the active
// company, active and inactive (AC-TEN-30), with name, code, address and status, filtered by
// "Todas / Activas / Inactivas". Every role reads it (`branch.read`); creating, editing,
// deactivating and reactivating show only if the company's `allowed_actions` bring them (owner
// and admin, never while the company is suspended): the UI hides, the backend decides. Until the
// actions are known none is shown. States: loading (skeleton rows), error ("Reintentar"), no
// permission (`403`), empty (per filter). The cash registers of each branch belong to the module
// that owns them (Q-220): this screen only keeps their place.
export const BRANCHES_TEXTS = {
  title: "Sucursales",
  filterLabel: "Mostrar",
  filters: { all: "Todas", active: "Activas", inactive: "Inactivas" },
  create: "Nueva sucursal",
  name: "Nombre",
  code: "Código",
  address: "Dirección",
  status: "Estado",
  actions: "Acciones",
  active: "Activa",
  inactive: "Inactiva",
  edit: "Editar",
  deactivate: "Desactivar",
  reactivate: "Reactivar",
  missing: "—",
  loading: "Cargando sucursales",
  emptyCanCreate: "Creá tu primera sucursal",
  emptyReadOnly: "Aún no hay sucursales",
  emptyActive: "No hay sucursales activas",
  emptyInactive: "No hay sucursales inactivas",
  forbidden: "No tenés permiso para ver las sucursales",
  actionsUnknown: "No se pudo saber qué acciones podés hacer en esta empresa.",
  registersTitle: "Cajas",
  registersText: "Las cajas de cada sucursal todavía no están disponibles.",
} as const;

export const BRANCHES_SKELETON_ROWS = 5;

export type BranchRowActions = Readonly<{
  canEdit: boolean;
  canDeactivate: boolean;
  canReactivate: boolean;
}>;

type BranchesTableProps = Readonly<{
  branches: readonly Branch[];
  actions: BranchRowActions;
  onEdit: (branch: Branch) => void;
  onChangeState: (branch: Branch, transition: BranchTransition) => void;
}>;

function BranchRow({
  branch,
  actions,
  hasActions,
  onEdit,
  onChangeState,
}: Readonly<{ branch: Branch; hasActions: boolean }> & Omit<BranchesTableProps, "branches">) {
  // The action buttons repeat their label on every row: the name cell describes each one.
  const nameId = useId();
  const transition: BranchTransition = branch.is_active ? "deactivate" : "reactivate";
  const canChange = branch.is_active ? actions.canDeactivate : actions.canReactivate;
  return (
    <TableRow>
      <TableCell id={nameId}>{branch.name}</TableCell>
      <TableCell>{branch.code || BRANCHES_TEXTS.missing}</TableCell>
      <TableCell>{branch.address || BRANCHES_TEXTS.missing}</TableCell>
      <TableCell>
        <Chip
          size="small"
          color={branch.is_active ? "success" : "default"}
          label={branch.is_active ? BRANCHES_TEXTS.active : BRANCHES_TEXTS.inactive}
        />
      </TableCell>
      {hasActions ? (
        <TableCell align="right" className="tw-whitespace-nowrap">
          {actions.canEdit ? (
            <Button size="small" aria-describedby={nameId} onClick={() => onEdit(branch)}>
              {BRANCHES_TEXTS.edit}
            </Button>
          ) : null}
          {canChange ? (
            <Button
              size="small"
              color={branch.is_active ? "error" : "primary"}
              aria-describedby={nameId}
              onClick={() => onChangeState(branch, transition)}
            >
              {BRANCHES_TEXTS[transition]}
            </Button>
          ) : null}
        </TableCell>
      ) : null}
    </TableRow>
  );
}

export function BranchesTable({ branches, actions, onEdit, onChangeState }: BranchesTableProps) {
  const hasActions = actions.canEdit || actions.canDeactivate || actions.canReactivate;
  return (
    <TableContainer component={Paper} variant="outlined">
      <Table size="small">
        <TableHead>
          <TableRow>
            <TableCell>{BRANCHES_TEXTS.name}</TableCell>
            <TableCell>{BRANCHES_TEXTS.code}</TableCell>
            <TableCell>{BRANCHES_TEXTS.address}</TableCell>
            <TableCell>{BRANCHES_TEXTS.status}</TableCell>
            {hasActions ? (
              <TableCell align="right">
                <span className="tw-sr-only">{BRANCHES_TEXTS.actions}</span>
              </TableCell>
            ) : null}
          </TableRow>
        </TableHead>
        <TableBody>
          {branches.map((branch) => (
            <BranchRow
              key={branch.id}
              branch={branch}
              actions={actions}
              hasActions={hasActions}
              onEdit={onEdit}
              onChangeState={onChangeState}
            />
          ))}
        </TableBody>
      </Table>
    </TableContainer>
  );
}

function BranchesSkeleton() {
  return (
    <div
      role="status"
      aria-busy="true"
      aria-label={BRANCHES_TEXTS.loading}
      className="tw-flex tw-flex-col tw-gap-2"
    >
      <Skeleton variant="rectangular" height={56} data-skeleton="header" />
      {Array.from({ length: BRANCHES_SKELETON_ROWS }, (_, index) => (
        <Skeleton key={index} variant="rectangular" height={52} data-skeleton="row" />
      ))}
    </div>
  );
}

function emptyTitle(filter: BranchFilter, canCreate: boolean): string {
  if (filter === "active") return BRANCHES_TEXTS.emptyActive;
  if (filter === "inactive") return BRANCHES_TEXTS.emptyInactive;
  return canCreate ? BRANCHES_TEXTS.emptyCanCreate : BRANCHES_TEXTS.emptyReadOnly;
}

type Dialog =
  | { kind: "form"; branch: Branch | null }
  | { kind: "state"; branch: Branch; transition: BranchTransition };

// A dialog belongs to the company it was opened for: if the tab changes company, it is gone, so a
// write never names a company the screen no longer shows.
type OpenDialog = Dialog & { organizationId: string };

function BranchesBody({
  organizationId,
  filter,
  canCreate,
  actions,
  onOpen,
}: Readonly<{
  organizationId: string | null;
  filter: BranchFilter;
  canCreate: boolean;
  actions: BranchRowActions;
  onOpen: (dialog: Dialog) => void;
}>) {
  const branches = useBranches(organizationId, filter);
  if (branches.isPending) {
    return <BranchesSkeleton />;
  }
  if (branches.isError) {
    return branches.error.status === 403 ? (
      <EmptyState title={BRANCHES_TEXTS.forbidden} />
    ) : (
      <ErrorNotice
        message={branches.error.title}
        onRetry={() => void branches.refetch()}
        retrying={branches.isFetching}
      />
    );
  }
  if (branches.data.length === 0) {
    const create =
      canCreate && filter === "all" ? (
        <Button variant="contained" onClick={() => onOpen({ kind: "form", branch: null })}>
          {BRANCHES_TEXTS.create}
        </Button>
      ) : undefined;
    return <EmptyState title={emptyTitle(filter, canCreate)} action={create} />;
  }
  return (
    <BranchesTable
      branches={branches.data}
      actions={actions}
      onEdit={(branch) => onOpen({ kind: "form", branch })}
      onChangeState={(branch, transition) => onOpen({ kind: "state", branch, transition })}
    />
  );
}

export function BranchesScreen() {
  const { organizationId } = useActiveOrganization();
  const details = useCurrentOrganizationDetails(organizationId);
  const [filter, setFilter] = useState<BranchFilter>("all");
  const registersId = useId();
  const [opened, setOpened] = useState<OpenDialog | null>(null);
  const dialog = opened !== null && opened.organizationId === organizationId ? opened : null;
  const open = (next: Dialog) => {
    if (organizationId !== null) setOpened({ ...next, organizationId });
  };
  const close = () => setOpened(null);
  const allowed = allowedActionsOf(details.data);
  const canCreate = allowed.has("branch.create");
  const actions: BranchRowActions = {
    canEdit: allowed.has("branch.update"),
    canDeactivate: allowed.has("branch.deactivate"),
    canReactivate: allowed.has("branch.reactivate"),
  };

  return (
    <div className="tw-flex tw-flex-col tw-gap-4">
      <div className="tw-flex tw-flex-wrap tw-items-center tw-justify-between tw-gap-3">
        <Typography component="h1" variant="h5">
          {BRANCHES_TEXTS.title}
        </Typography>
        <div className="tw-flex tw-flex-wrap tw-items-center tw-gap-3">
          <ToggleButtonGroup
            exclusive
            size="small"
            aria-label={BRANCHES_TEXTS.filterLabel}
            value={filter}
            onChange={(_event, value: BranchFilter | null) => {
              if (value !== null) setFilter(value);
            }}
          >
            {BRANCH_FILTERS.map((value) => (
              <ToggleButton key={value} value={value}>
                {BRANCHES_TEXTS.filters[value]}
              </ToggleButton>
            ))}
          </ToggleButtonGroup>
          {canCreate ? (
            <Button variant="contained" onClick={() => open({ kind: "form", branch: null })}>
              {BRANCHES_TEXTS.create}
            </Button>
          ) : null}
        </div>
      </div>
      {details.isError ? (
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
          {BRANCHES_TEXTS.actionsUnknown}
        </Alert>
      ) : null}
      <BranchesBody
        organizationId={organizationId}
        filter={filter}
        canCreate={canCreate}
        actions={actions}
        onOpen={open}
      />
      <section aria-labelledby={registersId} className="tw-flex tw-flex-col tw-gap-1">
        <Typography id={registersId} component="h2" variant="h6">
          {BRANCHES_TEXTS.registersTitle}
        </Typography>
        <Typography variant="body2" color="text.secondary">
          {BRANCHES_TEXTS.registersText}
        </Typography>
      </section>
      {dialog?.kind === "form" ? (
        <BranchFormDialog
          organizationId={dialog.organizationId}
          branch={dialog.branch}
          onClose={close}
        />
      ) : null}
      {dialog?.kind === "state" ? (
        <BranchStatusDialog
          organizationId={dialog.organizationId}
          branch={dialog.branch}
          transition={dialog.transition}
          onClose={close}
        />
      ) : null}
    </div>
  );
}
