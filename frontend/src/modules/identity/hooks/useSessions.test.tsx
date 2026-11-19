import { QueryClientProvider } from "@tanstack/react-query";
import { act, renderHook, waitFor } from "@testing-library/react";
import type { ReactNode } from "react";
import { describe, expect, it, vi } from "vitest";

import { createApiClient, CSRF_HEADER } from "@/lib/api-client";
import { ApiError } from "@/lib/problem";
import { makeQueryClient } from "@/lib/query-client";

import { revokeOtherSessions, useRevokeOtherSessions } from "./useRevokeOtherSessions";
import { revokeSession, useRevokeSession } from "./useRevokeSession";
import { fetchAllSessions, SESSIONS_QUERY_KEY, type Session } from "./useSessions";

// A browser resolves a relative URL against the page; Node's Request (used under jsdom) does not.
class BrowserRequest extends Request {
  constructor(input: RequestInfo | URL, init?: RequestInit) {
    super(typeof input === "string" ? new URL(input, window.location.href) : input, init);
  }
}

const SESSION_ID = "6d1c2b9a-3f4e-4a5b-8c7d-0e1f2a3b4c5d";

function session(id: string, isCurrent = false): Session {
  return {
    id,
    browser: "Chrome",
    os: "Windows",
    created_at: "2026-11-19T12:00:00Z",
    last_used_at: "2026-11-19T15:30:00Z",
    is_current: isCurrent,
  };
}

function page(results: Session[], next: string | null) {
  return new Response(JSON.stringify({ count: 3, next, previous: null, results }), {
    headers: { "content-type": "application/json" },
  });
}

function problem(status: number, code: string, title: string) {
  return new Response(
    JSON.stringify({ type: `urn:hub:problem:${code}`, title, status, code, request_id: "req-1" }),
    { status, headers: { "content-type": "application/problem+json" } },
  );
}

function clientWith(responses: Response[]) {
  const fetchMock = vi.fn<(request: Request) => Promise<Response>>(async () => {
    const next = responses.shift();
    if (next === undefined) throw new Error("unexpected request");
    return next;
  });
  const client = createApiClient({
    fetch: fetchMock,
    Request: BrowserRequest,
    readCsrfToken: () => "csrf-1",
  });
  return { client, fetchMock };
}

function wrapperWith(queryClient = makeQueryClient()) {
  return function Wrapper({ children }: Readonly<{ children: ReactNode }>) {
    return <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>;
  };
}

describe("sessions hooks (AC-IDA-33, RF-IDA-07, design.md §6.2)", () => {
  it("test_AC_IDA_33_sessions_reads_every_page", async () => {
    const { client, fetchMock } = clientWith([
      page([session("a", true), session("b")], "/api/auth/sessions/?page=2"),
      page([session("c")], null),
    ]);
    const sessions = await fetchAllSessions(client);
    expect(sessions.map((item) => item.id)).toEqual(["a", "b", "c"]);
    const urls = fetchMock.mock.calls.map(([request]) => new URL(request.url));
    expect(urls.map((url) => url.pathname)).toEqual(["/api/auth/sessions/", "/api/auth/sessions/"]);
    expect(urls[1]!.searchParams.get("page")).toBe("2");
    expect(SESSIONS_QUERY_KEY).toEqual(["identity", "sessions"]);
  });

  it("test_AC_IDA_33_sessions_refuses_a_next_page_that_does_not_advance", async () => {
    const { client } = clientWith([page([session("a", true)], "/api/auth/sessions/?page=1")]);
    const error = await fetchAllSessions(client).catch((caught: unknown) => caught);
    expect(error).toBeInstanceOf(ApiError);
  });

  it("test_AC_IDA_33_revoke_posts_the_id_only_in_the_path", async () => {
    const { client, fetchMock } = clientWith([new Response(null, { status: 204 })]);
    await expect(revokeSession(client, SESSION_ID)).resolves.toBe("revoked");
    const request = fetchMock.mock.calls[0]![0];
    expect(request.method).toBe("POST");
    const url = new URL(request.url);
    expect(url.pathname).toBe(`/api/auth/sessions/${SESSION_ID}/revoke/`);
    expect(url.search).toBe("");
    expect(request.headers.get(CSRF_HEADER)).toBe("csrf-1");
  });

  it("test_AC_IDA_33_revoke_404_counts_as_already_ended", async () => {
    const { client } = clientWith([problem(404, "not_found", "No encontrado")]);
    await expect(revokeSession(client, SESSION_ID)).resolves.toBe("already_ended");
  });

  it("test_AC_IDA_33_revoke_other_failures_stay_errors", async () => {
    const { client } = clientWith([problem(500, "internal_error", "Error interno")]);
    const error = await revokeSession(client, SESSION_ID).catch((caught: unknown) => caught);
    expect(error).toBeInstanceOf(ApiError);
    expect((error as ApiError).code).toBe("internal_error");
  });

  it("test_AC_IDA_33_revoke_others_posts_to_revoke_others", async () => {
    const { client, fetchMock } = clientWith([new Response(null, { status: 204 })]);
    await revokeOtherSessions(client);
    const request = fetchMock.mock.calls[0]![0];
    expect(request.method).toBe("POST");
    expect(new URL(request.url).pathname).toBe("/api/auth/sessions/revoke-others/");
  });

  it("test_AC_IDA_33_revoke_refreshes_the_list", async () => {
    const queryClient = makeQueryClient();
    const invalidate = vi.spyOn(queryClient, "invalidateQueries");
    const { client } = clientWith([problem(404, "not_found", "No encontrado")]);
    const { result } = renderHook(() => useRevokeSession(client), {
      wrapper: wrapperWith(queryClient),
    });
    act(() => result.current.mutate(SESSION_ID));
    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(invalidate).toHaveBeenCalledWith({ queryKey: SESSIONS_QUERY_KEY });
  });

  it("test_AC_IDA_33_revoke_others_refreshes_the_list", async () => {
    const queryClient = makeQueryClient();
    const invalidate = vi.spyOn(queryClient, "invalidateQueries");
    const { client } = clientWith([new Response(null, { status: 204 })]);
    const { result } = renderHook(() => useRevokeOtherSessions(client), {
      wrapper: wrapperWith(queryClient),
    });
    act(() => result.current.mutate());
    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(invalidate).toHaveBeenCalledWith({ queryKey: SESSIONS_QUERY_KEY });
  });
});
