import { afterEach, describe, expect, it, vi } from "vitest";

import { ApiError, CLIENT_ERROR_CODES } from "@/lib/problem";

import {
  ACTIVE_ORGANIZATION_PATH,
  isOrganizationId,
  type MyOrganization,
  readServerTabOrganization,
  readTabOrganization,
  resolveActiveOrganization,
  saveDefaultOrganization,
  subscribeTabOrganization,
  TAB_ORGANIZATION_KEY,
  writeTabOrganization,
} from "./active-organization";

const ACME: MyOrganization = {
  id: "6a1f0c2e-1b3d-4e5f-8a9b-0c1d2e3f4a5b",
  name: "Acme",
  status: "active",
  role: "owner",
};
const BETA: MyOrganization = {
  id: "7b2e1d3f-2c4e-4f60-9bac-1d2e3f4a5b6c",
  name: "Beta",
  status: "suspended",
  role: "viewer",
};
const GONE = "8c3f2e4a-3d5f-4a71-8cbd-2e3f4a5b6c7d";
const LIST = [ACME, BETA];

afterEach(() => window.sessionStorage.clear());

describe("active organization of the tab (RF-TEN-02, Q-205, Q-119, design.md §3.9)", () => {
  it("test_RF_TEN_02_resolution_prefers_tab_then_bff_default_then_first_by_name", () => {
    expect(resolveActiveOrganization(LIST, BETA.id, ACME.id)).toBe(BETA);
    expect(resolveActiveOrganization(LIST, GONE, BETA.id)).toBe(BETA);
    expect(resolveActiveOrganization(LIST, null, BETA.id.toUpperCase())).toBe(BETA);
    expect(resolveActiveOrganization(LIST, GONE, GONE)).toBe(ACME);
    expect(resolveActiveOrganization(LIST, null, null)).toBe(ACME);
    expect(resolveActiveOrganization([], ACME.id, ACME.id)).toBeNull();
  });

  it("test_RF_TEN_02_tab_value_lives_in_session_storage_and_notifies", () => {
    const listener = vi.fn();
    const unsubscribe = subscribeTabOrganization(listener);

    writeTabOrganization(ACME.id);
    expect(window.sessionStorage.getItem(TAB_ORGANIZATION_KEY)).toBe(ACME.id);
    expect(readTabOrganization()).toBe(ACME.id);
    writeTabOrganization(null);
    expect(readTabOrganization()).toBeNull();
    unsubscribe();
    writeTabOrganization(BETA.id);

    expect(listener).toHaveBeenCalledTimes(2);
    expect(readServerTabOrganization()).toBeNull();
  });

  it("test_RF_TEN_02_tab_value_that_is_not_a_uuid_is_absent", () => {
    window.sessionStorage.setItem(TAB_ORGANIZATION_KEY, "acme");
    expect(readTabOrganization()).toBeNull();
    expect(isOrganizationId(ACME.id)).toBe(true);
    expect(isOrganizationId(undefined)).toBe(false);
    expect(isOrganizationId(`${ACME.id}x`)).toBe(false);
  });

  it("test_RF_TEN_02_tab_storage_disabled_falls_back_silently", () => {
    const getItem = vi.spyOn(Storage.prototype, "getItem").mockImplementation(() => {
      throw new DOMException("denied", "SecurityError");
    });
    const setItem = vi.spyOn(Storage.prototype, "setItem").mockImplementation(() => {
      throw new DOMException("full", "QuotaExceededError");
    });
    expect(readTabOrganization()).toBeNull();
    expect(() => writeTabOrganization(ACME.id)).not.toThrow();
    getItem.mockRestore();
    setItem.mockRestore();
  });

  it("test_RF_TEN_02_saves_the_bff_default_with_csrf", async () => {
    const fetchMock = vi.fn<typeof fetch>(async () => new Response(null, { status: 204 }));

    await saveDefaultOrganization(ACME.id, fetchMock, "a=1; __Host-cpu_csrf=tok");

    const [path, init] = fetchMock.mock.calls[0]!;
    expect(path).toBe(ACTIVE_ORGANIZATION_PATH);
    expect(init?.method).toBe("PUT");
    expect(JSON.parse(String(init?.body))).toEqual({ organization_id: ACME.id });
    expect(new Headers(init?.headers).get("x-csrf-token")).toBe("tok");
  });

  it("test_RF_TEN_02_save_default_failures_are_api_errors", async () => {
    const refused = vi.fn<typeof fetch>(
      async () =>
        new Response(
          JSON.stringify({
            type: "urn:hub:problem:bff.csrf_failed",
            title: "Solicitud rechazada",
            status: 403,
            code: "bff.csrf_failed",
            request_id: "r",
          }),
          { status: 403, headers: { "content-type": "application/problem+json" } },
        ),
    );
    await expect(saveDefaultOrganization(null, refused, "")).rejects.toMatchObject({
      status: 403,
      code: "bff.csrf_failed",
    });
    expect(new Headers(refused.mock.calls[0]![1]?.headers).has("x-csrf-token")).toBe(false);

    const offline = vi.fn<typeof fetch>(async () => {
      throw new TypeError("network");
    });
    const error = await saveDefaultOrganization(ACME.id, offline, "").catch((e: unknown) => e);
    expect(error).toBeInstanceOf(ApiError);
    expect((error as ApiError).code).toBe(CLIENT_ERROR_CODES.network);
  });
});
