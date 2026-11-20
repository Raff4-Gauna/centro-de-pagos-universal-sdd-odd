import { QueryClientProvider } from "@tanstack/react-query";
import { act, renderHook, waitFor } from "@testing-library/react";
import type { ReactNode } from "react";
import { describe, expect, it, vi } from "vitest";

import { CSRF_HEADER } from "@/lib/api-client";
import { ApiError, CLIENT_ERROR_CODES } from "@/lib/problem";
import { makeQueryClient } from "@/lib/query-client";
import {
  readTabOrganization,
  TAB_ORGANIZATION_KEY,
  writeTabOrganization,
} from "@/modules/tenancy/lib/active-organization";

import { AFTER_LOGOUT_PATH, LOGOUT_PATH, requestLogout, useLogout } from "./useLogout";

const CSRF = "csrf-token-value";
const COOKIES = `__Host-cpu_csrf=${CSRF}; other=1`;

function problem(status: number, code: string, title: string) {
  return new Response(
    JSON.stringify({ type: `urn:hub:problem:${code}`, title, status, code, request_id: "req-1" }),
    { status, headers: { "content-type": "application/problem+json" } },
  );
}

function wrapper({ children }: Readonly<{ children: ReactNode }>) {
  return <QueryClientProvider client={makeQueryClient()}>{children}</QueryClientProvider>;
}

describe("useLogout (RF-IDA-05, AC-IDA-17, design.md §3.4, §4.6)", () => {
  it("test_RF_IDA_05_logout_posts_to_the_bff_with_the_csrf_token", async () => {
    const fetchMock = vi.fn(async () => new Response(null, { status: 204 }));
    await requestLogout(fetchMock, COOKIES);
    expect(fetchMock).toHaveBeenCalledTimes(1);
    const [url, init] = fetchMock.mock.calls[0] as unknown as [string, RequestInit];
    expect(url).toBe(LOGOUT_PATH);
    expect(LOGOUT_PATH).toBe("/api/auth/logout");
    expect(init.method).toBe("POST");
    expect(init.credentials).toBe("same-origin");
    expect(new Headers(init.headers).get(CSRF_HEADER)).toBe(CSRF);
  });

  it("test_RF_IDA_05_logout_without_csrf_cookie_sends_no_header", async () => {
    const fetchMock = vi.fn(async () => new Response(null, { status: 204 }));
    await requestLogout(fetchMock, "other=1");
    const [, init] = fetchMock.mock.calls[0] as unknown as [string, RequestInit];
    expect(new Headers(init.headers).has(CSRF_HEADER)).toBe(false);
  });

  it("test_RF_IDA_05_logout_204_goes_to_login", async () => {
    const navigate = vi.fn();
    const fetchMock = vi.fn(async () => new Response(null, { status: 204 }));
    const { result } = renderHook(() => useLogout({ navigate, fetch: fetchMock }), { wrapper });
    act(() => result.current.mutate());
    await waitFor(() => expect(navigate).toHaveBeenCalledWith(AFTER_LOGOUT_PATH));
    expect(AFTER_LOGOUT_PATH).toBe("/login");
  });

  // T-TEN-29: as the BFF clears `__Host-cpu_org`, the tab forgets its company (ADR-0004 §7).
  it("test_RF_IDA_05_logout_204_clears_the_tab_organization", async () => {
    writeTabOrganization("6a1f0c2e-1b3d-4e5f-8a9b-0c1d2e3f4a5b");
    const fetchMock = vi.fn(async () => new Response(null, { status: 204 }));
    const { result } = renderHook(() => useLogout({ navigate: vi.fn(), fetch: fetchMock }), {
      wrapper,
    });
    act(() => result.current.mutate());
    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(window.sessionStorage.getItem(TAB_ORGANIZATION_KEY)).toBeNull();
    expect(readTabOrganization()).toBeNull();
  });

  // T-IDA-25, known limitation of #109: a `403` means nothing was cleared, the session is still open.
  it("test_RF_IDA_05_logout_403_is_not_a_closed_session", async () => {
    const navigate = vi.fn();
    const fetchMock = vi.fn(async () => problem(403, "bff.csrf_failed", "Solicitud rechazada"));
    const { result } = renderHook(() => useLogout({ navigate, fetch: fetchMock }), { wrapper });
    act(() => result.current.mutate());
    await waitFor(() => expect(result.current.isError).toBe(true));
    expect(result.current.error).toBeInstanceOf(ApiError);
    expect(result.current.error?.code).toBe("bff.csrf_failed");
    expect(result.current.error?.title).toBe("Solicitud rechazada");
    expect(navigate).not.toHaveBeenCalled();
  });

  it("test_RF_IDA_05_logout_network_failure_is_not_a_closed_session", async () => {
    const navigate = vi.fn();
    const fetchMock = vi.fn(async () => {
      throw new TypeError("Failed to fetch");
    });
    const { result } = renderHook(() => useLogout({ navigate, fetch: fetchMock }), { wrapper });
    act(() => result.current.mutate());
    await waitFor(() => expect(result.current.isError).toBe(true));
    expect(result.current.error?.code).toBe(CLIENT_ERROR_CODES.network);
    expect(navigate).not.toHaveBeenCalled();
  });

  it("test_RF_IDA_05_logout_only_a_204_counts_as_closed", async () => {
    const navigate = vi.fn();
    const fetchMock = vi.fn(async () => new Response("{}", { status: 200 }));
    const { result } = renderHook(() => useLogout({ navigate, fetch: fetchMock }), { wrapper });
    act(() => result.current.mutate());
    await waitFor(() => expect(result.current.isError).toBe(true));
    expect(navigate).not.toHaveBeenCalled();
  });
});
