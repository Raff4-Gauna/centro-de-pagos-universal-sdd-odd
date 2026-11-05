import { afterEach, describe, expect, it, vi } from "vitest";

import { getQueryClient, makeQueryClient } from "./query-client";

describe("React Query client (RF-PLT-15, design.md §3.3.3)", () => {
  afterEach(() => {
    vi.doUnmock("@tanstack/react-query");
    vi.resetModules();
  });

  it("test_RF_PLT_15_query_client_defaults", () => {
    const defaults = makeQueryClient().getDefaultOptions();
    expect(defaults.queries).toMatchObject({
      retry: 1,
      staleTime: 30_000,
      refetchOnWindowFocus: false,
    });
    // A mutation (a charge, a refund) is never repeated behind the user's back.
    expect(defaults.mutations).toMatchObject({ retry: 0 });
  });

  it("test_RF_PLT_15_browser_reuses_one_query_client", () => {
    const first = getQueryClient();
    expect(getQueryClient()).toBe(first);
    expect(makeQueryClient()).not.toBe(first);
  });

  it("test_RF_PLT_15_server_gets_a_new_query_client_per_call", async () => {
    vi.resetModules();
    vi.doMock("@tanstack/react-query", async (importOriginal) => ({
      ...(await importOriginal<typeof import("@tanstack/react-query")>()),
      isServer: true,
    }));
    const { getQueryClient: getOnServer } = await import("./query-client");
    expect(getOnServer()).not.toBe(getOnServer());
  });
});
