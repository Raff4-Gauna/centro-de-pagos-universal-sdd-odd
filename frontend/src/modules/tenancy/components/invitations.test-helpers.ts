import type { QueryClient } from "@tanstack/react-query";

import type { TenancyAction } from "../hooks/useCurrentOrganizationDetails";
import type { Invitation } from "../hooks/useInvitations";
import type { Role } from "../lib/role-labels";
import { currentOrganization, json, problem } from "./branches.test-helpers";
import { ME, memberPage } from "./members.test-helpers";

// Fixtures and the fake BFF of "Invitaciones pendientes": the bodies follow the contract
// (`OrganizationInvitation`, `CreatedInvitation`, `CurrentOrganization` of
// specs/_contracts/openapi.yaml), with the `allowed_actions` and `invitable_roles` the backend
// computes, so the screen is checked against what the backend sends, never against a role.
export const NUEVA: Invitation = {
  id: "6f7a8b9c-0d1e-4f2a-8b3c-4d5e6f7a8b9c",
  email: "nueva@acme.test",
  role: "operator",
  status: "pending",
  purpose: "standard",
  expires_at: "2026-11-28T12:00:00Z",
  invited_by: ME.user,
  created_at: "2026-11-21T12:00:00Z",
  allowed_actions: ["invitation.resend", "invitation.revoke"],
};

// An owner invitation an admin may not touch, issued by the operator (no inviter).
export const DUENA: Invitation = {
  id: "7a8b9c0d-1e2f-4a3b-9c4d-5e6f7a8b9c0d",
  email: "duena@acme.test",
  role: "owner",
  status: "pending",
  purpose: "first_owner",
  expires_at: "2026-11-29T12:00:00Z",
  invited_by: null,
  created_at: "2026-11-22T12:00:00Z",
  allowed_actions: [],
};

// Fake tokens (never real ones): what the tests look for everywhere they must not be.
export const TOKEN = "fake-invitation-token-created";
export const RESENT_TOKEN = "fake-invitation-token-resent";

export function acceptUrl(token: string): string {
  return `http://localhost:3000/invitacion#token=${token}`;
}

export function created(invitation: Invitation, token: string): Response {
  return json({ ...invitation, accept_url: acceptUrl(token) }, 201);
}

export const INVITE_ACTIONS: TenancyAction[] = [
  "org.read",
  "member.list",
  "invitation.list",
  "invitation.create",
  "invitation.resend",
  "invitation.revoke",
];

export function current(allowed: TenancyAction[], invitable: Role[]) {
  return json({ ...currentOrganization(allowed), invitable_roles: invitable });
}

export function invitationPage(results: readonly Invitation[]): Response {
  return json({ count: results.length, next: null, previous: null, results });
}

export type Respond = (request: Request) => Response | Promise<Response>;
export type Write = (request: Request) => Response | Promise<Response> | null;

type Backend = Readonly<{
  invitations?: () => readonly Invitation[];
  allowed?: TenancyAction[];
  invitable?: Role[];
  write?: Write;
}>;

// The fake backend: the company's details, its members and invitations, and `write` for the rest.
export function backend({
  invitations = () => [NUEVA],
  allowed = INVITE_ACTIONS,
  invitable = ["admin", "operator", "viewer"],
  write = () => null,
}: Backend = {}): Respond {
  return (request) => {
    const { pathname } = new URL(request.url);
    if (request.method === "GET") {
      if (pathname === "/api/organizations/current/") return current(allowed, invitable);
      if (pathname === "/api/memberships/") return memberPage([ME]);
      if (pathname === "/api/invitations/") return invitationPage(invitations());
    }
    return write(request) ?? problem(404, "not_found", "No encontrado");
  };
}

// Everything TanStack Query keeps (queries and mutations, data and variables) as text, and the
// browser's storage and address: none of them may hold a token (AC-TEN-24).
export function keptByTheTab(queryClient: QueryClient): string {
  const queries = queryClient
    .getQueryCache()
    .getAll()
    .map(({ queryKey, state }) => ({ queryKey, state }));
  const mutations = queryClient
    .getMutationCache()
    .getAll()
    .map(({ state }) => state);
  const storage = [window.localStorage, window.sessionStorage].map((store) =>
    Array.from({ length: store.length }, (_, index) => store.getItem(store.key(index) ?? "")),
  );
  return JSON.stringify({ queries, mutations, storage, href: window.location.href });
}
