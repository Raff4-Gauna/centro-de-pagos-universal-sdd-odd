// @vitest-environment node
import { NextRequest } from "next/server";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { config, proxy } from "./proxy";

// `server-only` throws outside the react-server condition; the guard is asserted in env.test.ts.
vi.mock("server-only", () => ({}));

const APP = "https://app.example";
const RT = "__Host-cpu_rt";

function call(path: string, cookie?: string, method = "GET"): Response {
  const headers: Record<string, string> = cookie === undefined ? {} : { cookie };
  return proxy(new NextRequest(`http://frontend.internal:3000${path}`, { headers, method }));
}

function passes(response: Response): boolean {
  return response.headers.get("x-middleware-next") === "1";
}

beforeEach(() => {
  vi.stubEnv("HUB_APP_ORIGIN", APP);
});

afterEach(() => {
  vi.unstubAllEnvs();
});

describe("proxy.ts: pages need a session (AC-IDA-19, design.md §3.2)", () => {
  it.each(["/", "/inicio", "/configuracion", "/configuracion/perfil", "/pagina-nueva"])(
    "test_AC_IDA_19_page_%s_without_session_redirects_to_login",
    (path) => {
      const response = call(path);
      expect(response.status).toBe(302);
      const location = new URL(response.headers.get("location")!);
      expect(location.origin).toBe(APP);
      expect(location.pathname).toBe("/login");
      expect(location.searchParams.get("return_to")).toBe(path);
      expect(response.headers.get("cache-control")).toBe("no-store");
    },
  );

  it("test_AC_IDA_19_query_of_the_page_is_kept_in_return_to", () => {
    const location = new URL(call("/cobros?estado=pendiente").headers.get("location")!);
    expect(location.searchParams.get("return_to")).toBe("/cobros?estado=pendiente");
    expect([...location.searchParams.keys()]).toEqual(["return_to"]);
  });

  it.each(["/..//evil.example", "/.//evil.example", "/%2e%2e//evil.example"])(
    "test_AC_IDA_19_path_%s_never_becomes_another_host",
    (path) => {
      const location = new URL(call(path).headers.get("location")!);
      expect(location.origin).toBe(APP);
      expect(location.pathname).toBe("/login");
      expect(location.searchParams.get("return_to")!.startsWith("//")).toBe(false);
    },
  );

  it("test_AC_IDA_19_location_uses_the_app_origin_not_the_host_header", () => {
    const request = new NextRequest("http://frontend.internal:3000/inicio", {
      headers: { host: "evil.example" },
    });
    expect(new URL(proxy(request).headers.get("location")!).origin).toBe(APP);
  });

  it("test_AC_IDA_19_without_app_origin_still_redirects_with_a_fixed_path", () => {
    vi.stubEnv("HUB_APP_ORIGIN", "");
    const response = call("/inicio");
    expect(response.status).toBe(302);
    expect(response.headers.get("location")).toBe("/login");
  });

  it.each(["POST", "HEAD"])("test_AC_IDA_19_%s_to_a_page_without_session_redirects", (method) => {
    expect(call("/inicio", undefined, method).status).toBe(302);
  });

  it("test_AC_IDA_19_page_with_refresh_cookie_passes", () => {
    expect(passes(call("/inicio", `${RT}=opaque-refresh`))).toBe(true);
  });

  it("test_AC_IDA_19_only_an_access_cookie_is_no_session", () => {
    expect(call("/inicio", "__Host-cpu_at=jwt").status).toBe(302);
  });

  it("test_AC_IDA_19_repeated_refresh_cookie_counts_as_missing", () => {
    expect(call("/inicio", `${RT}=a; ${RT}=b`).status).toBe(302);
  });

  it("test_AC_IDA_19_cookie_without_the_host_prefix_is_no_session", () => {
    expect(call("/inicio", "cpu_rt=opaque").status).toBe(302);
  });

  it.each([undefined, `${RT}=opaque-refresh`])(
    "test_AC_IDA_19_login_page_is_open_with_or_without_session (%s)",
    (cookie) => {
      expect(passes(call("/login?error=session_expired", cookie))).toBe(true);
    },
  );

  it.each(["/api/me", "/api/auth/google/start", "/api/health", "/_next/static/chunks/app.js"])(
    "test_AC_IDA_19_%s_is_left_to_the_bff",
    (path) => {
      // The BFF answers 401 by itself; a redirect would hand the api-client an HTML page.
      expect(passes(call(path))).toBe(true);
    },
  );

  it.each(["/login/x", "/loginx", "/apis", "/api"])(
    "test_AC_IDA_19_lookalike_%s_is_protected",
    (path) => {
      expect(call(path).status).toBe(302);
    },
  );

  it("test_AC_IDA_19_matcher_skips_only_static_assets", () => {
    expect(config.matcher).toEqual(["/((?!_next/static|_next/image|favicon.ico).*)"]);
  });
});
