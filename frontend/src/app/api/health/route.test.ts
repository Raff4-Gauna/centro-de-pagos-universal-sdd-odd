// @vitest-environment node
import { describe, expect, it, vi } from "vitest";

import { GET, dynamic, runtime } from "./route";

describe("GET /api/health (RF-PLT-07)", () => {
  it("test_RF_PLT_07_bff_health_returns_ok", async () => {
    const fetchSpy = vi.spyOn(globalThis, "fetch");

    const response = GET();

    expect(response.status).toBe(200);
    expect(response.headers.get("content-type")).toContain("application/json");
    expect(response.headers.get("cache-control")).toBe("no-store");
    expect(await response.json()).toEqual({ status: "ok" });
    // The BFF health is about the frontend process only: it never calls the backend.
    expect(fetchSpy).not.toHaveBeenCalled();
  });

  it("test_RF_PLT_07_bff_health_is_dynamic_on_node_runtime", () => {
    expect(runtime).toBe("nodejs");
    expect(dynamic).toBe("force-dynamic");
  });
});
