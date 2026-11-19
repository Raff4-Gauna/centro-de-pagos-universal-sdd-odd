import { CSRF_COOKIE, CSRF_HEADER, cookieValue } from "@/lib/api-client";
import { apiErrorFromResponse, networkApiError } from "@/lib/problem";
import type { components } from "@/types/api";

// Which company a tab shows (Q-119 b, Q-205, ADR-0004 §7, design.md §3.9). Three sources, in this
// order: the tab's own value (`sessionStorage`, so two tabs never mix companies), the default the
// BFF keeps in the `HttpOnly` cookie `__Host-cpu_org` (read by the `(dashboard)` layout on the
// server), and the first organization by name. Each one counts only if the person still has an
// active membership there: none of them authorizes anything, Django revalidates every request.
export type MyOrganization = components["schemas"]["MyOrganization"];

// Canonical hyphenated form, any version: the id as Django stores it (same check as the BFF route).
const UUID = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;

export function isOrganizationId(value: unknown): value is string {
  return typeof value === "string" && UUID.test(value);
}

// The list comes ordered by name from `GET /api/organizations/` (design.md §6): its first item is
// "the first by name". Ids are compared without case, as the BFF lowercases the cookie's value.
export function resolveActiveOrganization(
  organizations: readonly MyOrganization[],
  tabOrganizationId: string | null,
  defaultOrganizationId: string | null,
): MyOrganization | null {
  const find = (id: string | null) =>
    id === null
      ? undefined
      : organizations.find((organization) => organization.id.toLowerCase() === id.toLowerCase());
  return find(tabOrganizationId) ?? find(defaultOrganizationId) ?? organizations[0] ?? null;
}

// The tab's value, as an external store for `useSyncExternalStore`: `sessionStorage` does not
// notify the tab that writes it, so writes go through here and tell the subscribers.
export const TAB_ORGANIZATION_KEY = "cpu.active-organization";

const tabListeners = new Set<() => void>();

function storage(): Storage | null {
  try {
    return typeof window === "undefined" ? null : window.sessionStorage;
  } catch {
    // Storage disabled by the browser: the tab falls back to the default and the first company.
    return null;
  }
}

export function readTabOrganization(): string | null {
  let value: string | null = null;
  try {
    value = storage()?.getItem(TAB_ORGANIZATION_KEY) ?? null;
  } catch {
    return null;
  }
  return isOrganizationId(value) ? value : null;
}

export function readServerTabOrganization(): string | null {
  return null;
}

export function writeTabOrganization(organizationId: string | null): void {
  try {
    const store = storage();
    if (organizationId === null) {
      store?.removeItem(TAB_ORGANIZATION_KEY);
    } else {
      store?.setItem(TAB_ORGANIZATION_KEY, organizationId);
    }
  } catch {
    // Quota or disabled storage: the choice still holds for this render through the api-client.
  }
  for (const listener of tabListeners) {
    listener();
  }
}

export function subscribeTabOrganization(listener: () => void): () => void {
  tabListeners.add(listener);
  return () => {
    tabListeners.delete(listener);
  };
}

// `PUT /api/session/active-organization` of the BFF (T-IDA-25): the default for new tabs. A BFF
// route, not part of the OpenAPI contract, so it goes through `fetch` with the CSRF double submit,
// like the logout. Only a `204` saved it.
export const ACTIVE_ORGANIZATION_PATH = "/api/session/active-organization";

function browserCookies(): string {
  return typeof document === "undefined" ? "" : document.cookie;
}

export async function saveDefaultOrganization(
  organizationId: string | null,
  fetchImpl: typeof fetch = globalThis.fetch,
  cookies: string = browserCookies(),
): Promise<void> {
  const headers = new Headers({ "content-type": "application/json" });
  const token = cookieValue(cookies, CSRF_COOKIE);
  if (token !== null) {
    headers.set(CSRF_HEADER, token);
  }
  let response: Response;
  try {
    response = await fetchImpl(ACTIVE_ORGANIZATION_PATH, {
      method: "PUT",
      headers,
      body: JSON.stringify({ organization_id: organizationId }),
      credentials: "same-origin",
      cache: "no-store",
    });
  } catch {
    throw networkApiError();
  }
  if (response.status !== 204) {
    throw await apiErrorFromResponse(response);
  }
}
