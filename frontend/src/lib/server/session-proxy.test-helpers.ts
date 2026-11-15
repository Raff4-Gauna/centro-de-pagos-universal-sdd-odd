// Shared setup of the session proxy suites (session-proxy{,.refresh}.test.ts): the environment of
// the BFF, a fake Django behind `fetch` that tells the refresh endpoint from the proxied API, the
// browser's request and the captured log lines.
import { afterEach, beforeEach, vi } from "vitest";

export const BFF = "https://hub.example";
export const ACCESS = "test-only.access-token.sentinel-A";
export const NEW_ACCESS = "test-only.access-token.sentinel-B";
export const REFRESH = "rt1.0b6c2c1e-4d3a-4e5f-9a8b-7c6d5e4f3a2b.secret-part_A1";
export const SUCCESSOR = "rt1.0b6c2c1e-4d3a-4e5f-9a8b-7c6d5e4f3a2b.successor_B2";
export const CSRF = "c".repeat(43);
export const ORGANIZATION = "5d1f0c7a-3b2e-4c9d-8a6f-1e2d3c4b5a69";
export const REFRESH_PATH = "/api/auth/bff/refresh/";
export const TOKENS = [ACCESS, NEW_ACCESS, REFRESH, SUCCESSOR];

let stdout: string[] = [];

// Call once at the top level of a suite.
export function installSessionProxyHooks(): void {
  beforeEach(() => {
    vi.stubEnv("BACKEND_INTERNAL_URL", "http://backend:8000");
    vi.stubEnv("HUB_BFF_CREDENTIAL", "test-only-bff-credential");
    vi.stubEnv("HUB_APP_ORIGIN", BFF);
    vi.stubEnv("HUB_TRUSTED_PROXY_HOPS", "1");
    stdout = [];
    vi.spyOn(process.stdout, "write").mockImplementation((chunk: string | Uint8Array) => {
      stdout.push(String(chunk));
      return true;
    });
  });

  afterEach(() => {
    vi.unstubAllEnvs();
  });
}

export function logLines(): string[] {
  return stdout;
}

export type DjangoCall = { path: string; headers: Record<string, string>; body: string };

type Handler = (call: DjangoCall) => Response | Promise<Response>;

// Django behind `fetch`: `refresh` answers `auth/bff/refresh`, `api` everything else. Each call
// is recorded with its headers and its body as Django would read it.
export function fakeDjango(api: Handler, refresh: Handler = () => rotated()) {
  const calls: DjangoCall[] = [];
  vi.spyOn(globalThis, "fetch").mockImplementation(async (input, init) => {
    const url = new URL(String(input));
    const body = init?.body == null ? "" : await new Response(init.body).text();
    const call = {
      path: `${url.pathname}${url.search}`,
      headers: Object.fromEntries(new Headers(init?.headers).entries()),
      body,
    };
    calls.push(call);
    return url.pathname === REFRESH_PATH ? refresh(call) : api(call);
  });
  return {
    calls,
    apiCalls: () => calls.filter((call) => call.path !== REFRESH_PATH),
    refreshCalls: () => calls.filter((call) => call.path === REFRESH_PATH),
  };
}

export function rotated(refreshToken: string | null = SUCCESSOR): Response {
  return Response.json({
    access_token: NEW_ACCESS,
    access_expires_in: 900,
    refresh_token: refreshToken,
    session_expires_in: 604_800,
  });
}

export function problem(status: number, code: string, headers: Record<string, string> = {}) {
  return new Response(
    JSON.stringify({ type: `urn:hub:problem:${code}`, title: "x", status, code, request_id: null }),
    { status, headers: { "content-type": "application/problem+json", ...headers } },
  );
}

type BrowserInit = {
  method?: string;
  cookies?: Record<string, string>;
  headers?: Record<string, string>;
  body?: string;
};

// A request as the browser sends it. A mutation carries what the api-client adds: `Origin` and
// the double-submit token, unless the test overrides them.
export function browserRequest(path: string, init: BrowserInit = {}): Request {
  const method = init.method ?? "GET";
  const headers: Record<string, string> = {
    "user-agent": "Mozilla/5.0 (test)",
    "x-forwarded-for": "203.0.113.7",
  };
  if (method !== "GET" && method !== "HEAD") {
    headers.origin = BFF;
    headers["x-csrf-token"] = CSRF;
  }
  const cookies = { ...init.cookies };
  const pairs = Object.entries(cookies).map(([name, value]) => `${name}=${value}`);
  if (pairs.length > 0) {
    headers.cookie = pairs.join("; ");
  }
  Object.assign(headers, init.headers);
  if (init.body !== undefined) {
    headers["content-type"] = "application/json";
    headers["content-length"] = String(Buffer.byteLength(init.body));
  }
  return new Request(`${BFF}${path}`, { method, headers, body: init.body });
}

export function segmentsOf(path: string): string[] {
  return new URL(path, BFF).pathname.replace(/^\/api\//, "").split("/");
}

// The `Set-Cookie` headers of a response, by cookie name.
export function setCookies(response: Response): Record<string, string> {
  return Object.fromEntries(
    response.headers.getSetCookie().map((line) => {
      const pair = line.split(";", 1)[0]!;
      const separator = pair.indexOf("=");
      return [pair.slice(0, separator), line];
    }),
  );
}
