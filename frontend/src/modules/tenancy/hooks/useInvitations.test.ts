import { describe, expect, it, vi } from "vitest";

import { createApiClient, ORGANIZATION_HEADER } from "@/lib/api-client";

import { BrowserRequest, json } from "../components/branches.test-helpers";
import { acceptUrl, invitationPage, NUEVA, TOKEN } from "../components/invitations.test-helpers";
import { createInvitation, fetchInvitations, invitationsQueryKey } from "./useInvitations";

// The requests of "Invitaciones pendientes" (RF-TEN-05, design.md §6): every page of the list
// under the company of the query key, and the `201` that carries the link (AC-TEN-24).
function clientAnswering(respond: (request: Request) => Response) {
  const requests: Request[] = [];
  const client = createApiClient({
    Request: BrowserRequest,
    readCsrfToken: () => "csrf-test-token",
    onSessionExpired: () => undefined,
    onOrganizationError: () => undefined,
    fetch: async (request: Request) => {
      requests.push(request);
      return respond(request);
    },
  });
  return { client, requests };
}

describe("useInvitations (RF-TEN-05)", () => {
  it("test_RF_TEN_05_list_reads_every_page_with_the_key_company", async () => {
    const second = { ...NUEVA, id: "y", email: "otra@acme.test" };
    const { client, requests } = clientAnswering((request) => {
      const page = new URL(request.url).searchParams.get("page");
      return page === "1"
        ? json({ count: 2, next: "/api/invitations/?page=2", previous: null, results: [NUEVA] })
        : invitationPage([second]);
    });
    const list = await fetchInvitations(client, invitationsQueryKey("org-a"));
    expect(list.map(({ email }) => email)).toEqual([NUEVA.email, second.email]);
    expect(requests.map((r) => r.headers.get(ORGANIZATION_HEADER))).toEqual(["org-a", "org-a"]);
  });

  it("test_AC_TEN_24_a_201_without_link_is_an_unexpected_response", async () => {
    const { client } = clientAnswering(() => json(NUEVA, 201));
    await expect(
      createInvitation(client, "org-a", { email: NUEVA.email, role: "operator" }),
    ).rejects.toMatchObject({ code: "client.unexpected_response" });
  });

  it("test_AC_TEN_24_the_201_brings_the_link", async () => {
    const respond = vi.fn(() => json({ ...NUEVA, accept_url: acceptUrl(TOKEN) }, 201));
    const { client } = clientAnswering(respond);
    const created = await createInvitation(client, "org-a", {
      email: NUEVA.email,
      role: "operator",
    });
    expect(created.accept_url).toBe(acceptUrl(TOKEN));
  });
});
