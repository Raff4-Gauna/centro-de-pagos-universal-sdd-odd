// @vitest-environment node
import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

import { afterEach, describe, expect, it, vi } from "vitest";

import { getAppOrigin, getBffCredential, getTrustedProxyHops } from "./env";

// `server-only` throws outside the react-server condition; that the modules import it is
// asserted on their source below.
vi.mock("server-only", () => ({}));

afterEach(() => {
  vi.unstubAllEnvs();
});

describe("BFF identity configuration (design.md §8.3, RN-IDA-12)", () => {
  it("test_RN_IDA_12_bff_credential_is_required_and_never_echoed", () => {
    vi.stubEnv("HUB_BFF_CREDENTIAL", "");
    expect(() => getBffCredential()).toThrow("HUB_BFF_CREDENTIAL is not set");
    vi.stubEnv("HUB_BFF_CREDENTIAL", "test-only-sentinel");
    expect(getBffCredential()).toBe("test-only-sentinel");
  });

  it("test_RN_IDA_13_app_origin_is_a_bare_http_origin", () => {
    vi.stubEnv("HUB_APP_ORIGIN", "https://App.Example/");
    expect(getAppOrigin()).toBe("https://app.example");
    vi.stubEnv("HUB_APP_ORIGIN", "http://localhost:3000");
    expect(getAppOrigin()).toBe("http://localhost:3000");

    vi.stubEnv("HUB_APP_ORIGIN", "");
    expect(() => getAppOrigin()).toThrow("HUB_APP_ORIGIN is not set");
    for (const bad of [
      "not a url sentinel",
      "ftp://app.example",
      "https://app.example/path",
      "https://app.example/?",
      "https://app.example/#x",
      "https://user:sentinel@app.example",
    ]) {
      vi.stubEnv("HUB_APP_ORIGIN", bad);
      expect(() => getAppOrigin(), bad).toThrow(/^HUB_APP_ORIGIN is not a valid/);
      expect(() => getAppOrigin(), bad).not.toThrow(/sentinel/);
    }
  });

  it("test_RN_IDA_15_trusted_proxy_hops_default_to_zero_and_are_bounded", () => {
    vi.stubEnv("HUB_TRUSTED_PROXY_HOPS", "");
    expect(getTrustedProxyHops()).toBe(0);
    vi.stubEnv("HUB_TRUSTED_PROXY_HOPS", "2");
    expect(getTrustedProxyHops()).toBe(2);
    vi.stubEnv("HUB_TRUSTED_PROXY_HOPS", "10");
    expect(getTrustedProxyHops()).toBe(10);
    for (const bad of ["11", "-1", "1.5", " 1", "one", "100"]) {
      vi.stubEnv("HUB_TRUSTED_PROXY_HOPS", bad);
      expect(() => getTrustedProxyHops(), bad).toThrow(/^HUB_TRUSTED_PROXY_HOPS must be/);
    }
  });

  it("test_RN_IDA_12_session_modules_are_server_only", () => {
    const here = dirname(fileURLToPath(import.meta.url));
    for (const name of ["env", "cookies", "client-ip", "return-path", "django", "problem"]) {
      const source = readFileSync(join(here, `${name}.ts`), "utf8");
      const firstStatement = source.split("\n").find((line) => line && !line.startsWith("//"));
      expect(firstStatement, name).toBe('import "server-only";');
      expect(source, name).not.toContain("NEXT_PUBLIC_");
    }
    // The credential is only ever put in a header: never logged nor written to stdout.
    const django = readFileSync(join(here, "django.ts"), "utf8");
    expect(django).not.toMatch(/console\.|process\.stdout|logBffRequest/);
  });
});
