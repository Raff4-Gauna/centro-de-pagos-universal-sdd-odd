import type { Branch } from "../hooks/useBranches";
import type {
  CurrentOrganizationDetails,
  TenancyAction,
} from "../hooks/useCurrentOrganizationDetails";
import { ACME } from "./tenancy.test-helpers";

// Fixtures and answers of the fake BFF for the tests of "Sucursales": the bodies follow the
// contract (specs/_contracts/openapi.yaml), so the screen is checked against what the backend sends.
export const CENTRO: Branch = {
  id: "1a2b3c4d-5e6f-4a7b-8c9d-0e1f2a3b4c5d",
  name: "Centro",
  code: "C-01",
  address: "Av. Siempreviva 742",
  is_active: true,
  deactivated_at: null,
};

export const NORTE: Branch = {
  id: "2b3c4d5e-6f7a-4b8c-9d0e-1f2a3b4c5d6e",
  name: "Norte",
  code: "",
  address: "",
  is_active: false,
  deactivated_at: "2026-11-10T12:00:00Z",
};

export const MANAGE_ACTIONS: TenancyAction[] = [
  "org.read",
  "branch.read",
  "branch.create",
  "branch.update",
  "branch.deactivate",
  "branch.reactivate",
];
export const READ_ACTIONS: TenancyAction[] = ["org.read", "branch.read"];

export function currentOrganization(allowed: TenancyAction[]): CurrentOrganizationDetails {
  return {
    id: ACME.id,
    name: ACME.name,
    legal_name: "",
    tax_id: "",
    timezone: "America/Argentina/Buenos_Aires",
    status: "active",
    my_role: "owner",
    my_membership_id: "9f8e7d6c-5b4a-4392-8170-6f5e4d3c2b1a",
    allowed_actions: allowed,
    invitable_roles: [],
  };
}

export function json(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "content-type": "application/json" },
  });
}

export function problem(status: number, code: string, title: string, extra: object = {}): Response {
  return new Response(
    JSON.stringify({ type: "about:blank", title, status, code, request_id: "req-1", ...extra }),
    { status, headers: { "content-type": "application/problem+json" } },
  );
}

export function branchPage(results: Branch[]): Response {
  return json({ count: results.length, next: null, previous: null, results });
}

// The branches the fake backend keeps for one company, filtered as `?is_active=` asks.
export function listAnswer(request: Request, branches: readonly Branch[]): Response {
  const isActive = new URL(request.url).searchParams.get("is_active");
  const shown =
    isActive === null
      ? branches
      : branches.filter(({ is_active }) => String(is_active) === isActive);
  return branchPage([...shown]);
}

// A browser resolves a relative URL against the page; Node's Request (under jsdom) does not.
export class BrowserRequest extends Request {
  constructor(input: RequestInfo | URL, init?: RequestInit) {
    super(typeof input === "string" ? new URL(input, window.location.href) : input, init);
  }
}
