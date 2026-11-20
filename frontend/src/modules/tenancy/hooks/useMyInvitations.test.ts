import { describe, expect, it, vi } from "vitest";

import { createApiClient, ORGANIZATION_HEADER } from "@/lib/api-client";
import { ApiError } from "@/lib/problem";

import {
  acceptMyInvitation,
  fetchMyInvitations,
  MY_INVITATIONS_PAGE_SIZE,
  MY_INVITATIONS_QUERY_KEY,
  myInvitationsQueryOptions,
} from "./useMyInvitations";

// A browser resolves a relative URL against the page; Node's Request (used under jsdom) does not.
class BrowserRequest extends Request {
  constructor(input: RequestInfo | URL, init?: RequestInit) {
    super(typeof input === "string" ? new URL(input, window.location.href) : input, init);
  }
}

function invitation(index: number) {
  return {
    id: `3c4d5e6f-7a8b-4c9d-8e0f-${String(index).padStart(12, "0")}`,
    organization: {
      id: `7b2e1d3f-2c4e-4f60-9bac-${String(index).padStart(12, "0")}`,
      name: `B${index}`,
    },
    role: "admin",
    expires_at: "2026-11-27T15:30:00Z",
  };
}

function page(results: unknown[], count: number, next: string | null) {
  return new Response(JSON.stringify({ count, next, previous: null, results }), {
    headers: { "content-type": "application/json" },
  });
}

function clientWith(respond: (request: Request) => Response) {
  const fetchMock = vi.fn(async (request: Request) => respond(request));
  const client = createApiClient({
    fetch: fetchMock,
    Request: BrowserRequest,
    readCsrfToken: () => "csrf-test-token",
  });
  return { client, fetchMock };
}

describe("useMyInvitations (AC-TEN-39, RF-TEN-05, design.md §3.9)", () => {
  it("test_AC_TEN_39_fetch_reads_every_page_without_a_company", async () => {
    const { client, fetchMock } = clientWith((request) =>
      new URL(request.url).searchParams.get("page") === "1"
        ? page([invitation(1)], 2, "/api/invitations/mine/?page=2")
        : page([invitation(2)], 2, null),
    );

    const list = await fetchMyInvitations(client);

    expect(list.map(({ organization }) => organization.name)).toEqual(["B1", "B2"]);
    const requests = fetchMock.mock.calls.map(([request]) => request);
    expect(requests.map(({ url }) => new URL(url).pathname)).toEqual([
      "/api/invitations/mine/",
      "/api/invitations/mine/",
    ]);
    expect(new URL(requests[0]!.url).searchParams.get("page_size")).toBe(
      String(MY_INVITATIONS_PAGE_SIZE),
    );
    expect(requests.every(({ headers }) => headers.get(ORGANIZATION_HEADER) === null)).toBe(true);
  });

  it("test_AC_TEN_39_fetch_stops_at_count_and_fails_without_a_body", async () => {
    const loop = clientWith(() => page([invitation(1)], 1, "/api/invitations/mine/?page=2"));
    await expect(fetchMyInvitations(loop.client)).resolves.toHaveLength(1);
    expect(loop.fetchMock).toHaveBeenCalledTimes(1);

    const empty = clientWith(() => new Response(null, { status: 204 }));
    await expect(fetchMyInvitations(empty.client)).rejects.toBeInstanceOf(ApiError);
    // Exempt from the active organization: never under ['org', …].
    expect(myInvitationsQueryOptions(empty.client).queryKey).toEqual(MY_INVITATIONS_QUERY_KEY);
    expect(MY_INVITATIONS_QUERY_KEY[0]).not.toBe("org");
  });

  it("test_AC_TEN_39_accept_posts_the_id_with_csrf_and_no_body", async () => {
    const accepted = {
      organization: invitation(1).organization,
      role: "admin",
      membership_id: "m",
    };
    const { client, fetchMock } = clientWith(
      () =>
        new Response(JSON.stringify(accepted), { headers: { "content-type": "application/json" } }),
    );

    await expect(acceptMyInvitation(client, invitation(1).id)).resolves.toEqual(accepted);

    const [request] = fetchMock.mock.calls[0]!;
    expect(request.method).toBe("POST");
    expect(new URL(request.url).pathname).toBe(`/api/invitations/${invitation(1).id}/accept/`);
    expect(request.headers.get(ORGANIZATION_HEADER)).toBeNull();
    expect(request.headers.get("X-CSRF-Token")).toBe("csrf-test-token");
    expect(await request.text()).toBe("");
  });

  it("test_AC_TEN_39_accept_refused_is_an_api_error_with_its_code", async () => {
    const { client } = clientWith(
      () =>
        new Response(
          JSON.stringify({
            type: "about:blank",
            title: "Invitación no válida",
            status: 400,
            code: "invitation_invalid",
            reason: "not_found",
            request_id: "req-1",
          }),
          { status: 400, headers: { "content-type": "application/problem+json" } },
        ),
    );

    const error = await acceptMyInvitation(client, invitation(9).id).catch(
      (caught: unknown) => caught,
    );

    expect(error).toBeInstanceOf(ApiError);
    expect((error as ApiError).code).toBe("invitation_invalid");
    expect((error as ApiError).title).toBe("Invitación no válida");
  });
});
