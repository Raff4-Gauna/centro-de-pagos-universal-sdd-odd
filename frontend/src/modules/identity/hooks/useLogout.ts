"use client";

import { useMutation } from "@tanstack/react-query";

import { CSRF_COOKIE, CSRF_HEADER, cookieValue } from "@/lib/api-client";
import { apiErrorFromResponse, networkApiError, type ApiError } from "@/lib/problem";
import { clearTabOrganization } from "@/modules/tenancy/lib/active-organization";

// "Cerrar sesión" (RF-IDA-05, design.md §3.4, §4.6): `POST /api/auth/logout` of the BFF, which
// revokes the session and clears its cookies. The route is the BFF's own, not part of the OpenAPI
// contract, so it goes through `fetch` with the same CSRF double submit as the typed client.
//
// Only a `204` means the session is closed. A `403 bff.csrf_failed` cleared nothing (T-IDA-25,
// review of #109) and a network failure says nothing: both stay errors, the browser keeps the page
// and the person can retry. Only after the `204` the tab forgets its company (`sessionStorage`, as
// the BFF clears `__Host-cpu_org`, ADR-0004 §7) and the browser goes to "Ingresar".
export const LOGOUT_PATH = "/api/auth/logout";
export const AFTER_LOGOUT_PATH = "/login";

function browserCookies(): string {
  return typeof document === "undefined" ? "" : document.cookie;
}

export async function requestLogout(
  fetchImpl: typeof fetch = globalThis.fetch,
  cookies: string = browserCookies(),
): Promise<void> {
  const headers = new Headers();
  const token = cookieValue(cookies, CSRF_COOKIE);
  if (token !== null) {
    headers.set(CSRF_HEADER, token);
  }
  let response: Response;
  try {
    response = await fetchImpl(LOGOUT_PATH, {
      method: "POST",
      headers,
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

function goTo(url: string): void {
  window.location.assign(url);
}

// Injectable for tests only; production uses the browser's `fetch` and navigation.
export type UseLogoutOptions = Readonly<{
  navigate?: (url: string) => void;
  fetch?: typeof fetch;
}>;

export function useLogout({ navigate = goTo, fetch: fetchImpl }: UseLogoutOptions = {}) {
  return useMutation<void, ApiError, void>({
    mutationFn: () => requestLogout(fetchImpl),
    onSuccess: () => {
      clearTabOrganization();
      navigate(AFTER_LOGOUT_PATH);
    },
  });
}
