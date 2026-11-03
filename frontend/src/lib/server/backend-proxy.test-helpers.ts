// Shared setup of the BFF proxy suites (backend-proxy.{paths,errors}.test.ts): stdout capture,
// a mocked fetch, a real HTTP backend on 127.0.0.1 and the problem+json + log assertion.
import { createServer, type IncomingHttpHeaders, type ServerResponse } from "node:http";
import type { AddressInfo } from "node:net";

import { afterEach, beforeEach, expect, vi } from "vitest";

export const UUID4 = /^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/;
export const VALID = "3f2b8c1e-9d4a-4b7e-8f61-2a5c9e0d7b13";
export const BFF = "http://localhost:3000";

let stdout: string[] = [];

// Call once at the top level of a suite.
export function installBffTestHooks(): void {
  beforeEach(() => {
    vi.stubEnv("BACKEND_INTERNAL_URL", "http://backend:8000");
    stdout = [];
    vi.spyOn(process.stdout, "write").mockImplementation((chunk: string | Uint8Array) => {
      stdout.push(String(chunk));
      return true;
    });
  });

  afterEach(async () => {
    vi.unstubAllEnvs();
    await Promise.all(servers.splice(0).map((close) => close()));
  });
}

export function mockFetch(
  impl: (init: RequestInit) => Promise<Response> = async () => Response.json({}),
) {
  const calls: { url: URL; init: RequestInit }[] = [];
  vi.spyOn(globalThis, "fetch").mockImplementation(async (input, init) => {
    calls.push({ url: new URL(String(input)), init: init ?? {} });
    return impl(init ?? {});
  });
  return calls;
}

function lastLog(): Record<string, unknown> {
  expect(stdout).toHaveLength(1);
  return JSON.parse(stdout[0]!) as Record<string, unknown>;
}

type LogExpectation = { reason?: string; level?: string };

export async function expectProblem(
  response: Response,
  status: number,
  code: string,
  log: LogExpectation = {},
): Promise<string> {
  expect(response.status).toBe(status);
  const requestId = response.headers.get("x-request-id");
  expect(requestId).toMatch(UUID4);
  expect(Object.fromEntries(response.headers.entries())).toEqual({
    "content-type": "application/problem+json",
    "cache-control": "no-store",
    "x-request-id": requestId,
  });
  const text = await response.text();
  const body = JSON.parse(text) as Record<string, unknown>;
  // The cause of a 502 is only for the operators' log, never for the browser.
  expect(body).not.toHaveProperty("reason");
  expect(text).not.toMatch(/config|network|client_abort/);
  expect(body).toMatchObject({
    type: `urn:hub:problem:${code}`,
    title: expect.any(String),
    status,
    code,
    request_id: requestId,
  });
  // The log line is written on errors too, with the same id, the problem code and (502) the cause.
  const entry = lastLog();
  expect(entry).toMatchObject({
    level: log.level ?? (status >= 500 ? "error" : "info"),
    request_id: requestId,
    route: "/api/[...path]",
    status,
    code,
  });
  if ("reason" in log) {
    expect(entry.reason).toBe(log.reason);
  }
  stdout.length = 0;
  return text;
}

// Real HTTP backend on 127.0.0.1 so undici's actual behaviour (content-length, abort) is tested.
type Received = { url: string; headers: IncomingHttpHeaders; body: string };
const servers: (() => Promise<void>)[] = [];

export async function startBackend(reply: (res: ServerResponse) => void = (res) => res.end("{}")) {
  const received: Received[] = [];
  const server = createServer((req, res) => {
    const chunks: Buffer[] = [];
    req.on("data", (chunk: Buffer) => chunks.push(chunk));
    req.on("end", () => {
      received.push({
        url: req.url ?? "",
        headers: req.headers,
        body: Buffer.concat(chunks).toString(),
      });
      reply(res);
    });
  });
  await new Promise<void>((resolve) => server.listen(0, "127.0.0.1", resolve));
  const close = () =>
    new Promise<void>((resolve) => {
      server.closeAllConnections();
      server.close(() => resolve());
    });
  servers.push(close);
  const { port } = server.address() as AddressInfo;
  return { origin: `http://127.0.0.1:${port}`, received, close };
}
