// @vitest-environment node
import { spawnSync } from "node:child_process";
import { mkdirSync, mkdtempSync, rmSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import {
  checkClientBundle,
  listClientFiles,
  main,
  readSentinels,
  scanText,
} from "./check-client-bundle";

// Fictitious, like the builder stage of frontend/Dockerfile: never a real backend address.
const SENTINEL = "http://bundle-sentinel-backend-internal-url.invalid:8000";
const SENTINEL_HOST = "bundle-sentinel-backend-internal-url.invalid";
const ENV = { BACKEND_INTERNAL_URL: SENTINEL };
const SCRIPT = fileURLToPath(new URL("./check-client-bundle.ts", import.meta.url));
const CLEAN_CHUNK = 'self.__next_f.push([1,"ok"]);if("production"!==process.env.NODE_ENV){}';

let nextDir: string;

function put(path: string, content: string): void {
  const file = join(nextDir, path);
  mkdirSync(dirname(file), { recursive: true });
  writeFileSync(file, content, "utf8");
}

beforeEach(() => {
  nextDir = mkdtempSync(join(tmpdir(), "bundle-check-"));
  put("static/chunks/main.js", CLEAN_CHUNK);
  put("static/css/app.css", "body{margin:0}");
  put("server/app/inicio.html", "<html><body>Inicio</body></html>");
  put("server/app/inicio.rsc", '0:["inicio"]');
  put("server/app/inicio.meta", '{"status":200}');
  // Server code never reaches a browser: not scanned, even when it names the variable.
  put("server/app/api/[...path]/route.js", "process.env.BACKEND_INTERNAL_URL");
  put("standalone/server.js", "process.env.BACKEND_INTERNAL_URL");
});

afterEach(() => {
  rmSync(nextDir, { recursive: true, force: true });
});

describe("check-client-bundle (AC-PLT-29)", () => {
  it("test_AC_PLT_29_bundle_with_sentinel_fails", () => {
    put("static/chunks/leak.js", `fetch("${SENTINEL}/api/x")`);
    put("server/app/configuracion.html", `<a href="${SENTINEL}">x</a>`);

    const result = checkClientBundle(nextDir, ENV);

    expect(result.code).toBe(1);
    expect(result.messages).toEqual([
      "client bundle: server/app/configuracion.html contains the sentinel value of BACKEND_INTERNAL_URL",
      "client bundle: static/chunks/leak.js contains the sentinel value of BACKEND_INTERNAL_URL",
    ]);
    // The value itself is never printed (C-06).
    expect(result.messages.join("\n")).not.toContain(SENTINEL);
  });

  it("test_AC_PLT_29_bundle_with_non_public_var_name_fails", () => {
    put("static/chunks/name.js", 'const k="BACKEND_INTERNAL_URL";');
    put("static/chunks/env.js", 'a=process.env.SECRET_TOKEN;b=process.env["API_KEY"];');
    put("static/chunks/public.js", "a=process.env.NEXT_PUBLIC_FLAG;b=process.env.NODE_ENV;");

    const result = checkClientBundle(nextDir, ENV);

    expect(result.code).toBe(1);
    expect(result.messages).toEqual([
      "client bundle: static/chunks/env.js references env.API_KEY, which is not NEXT_PUBLIC_",
      "client bundle: static/chunks/env.js references env.SECRET_TOKEN, which is not NEXT_PUBLIC_",
      "client bundle: static/chunks/name.js contains the server-only variable name BACKEND_INTERNAL_URL",
    ]);
  });

  it("test_AC_PLT_29_turbopack_polyfilled_env_reference_fails", () => {
    // What Turbopack emits for `process.env.SOME_SERVER_TOKEN` in a client component (observed on
    // a real build): the process polyfill module, not the literal `process.env.`.
    put("static/chunks/tp.js", "children:String(e.default.env.SOME_SERVER_TOKEN)});x.env.lower;");

    const result = checkClientBundle(nextDir, ENV);

    expect(result.code).toBe(1);
    expect(result.messages).toEqual([
      "client bundle: static/chunks/tp.js references env.SOME_SERVER_TOKEN, which is not NEXT_PUBLIC_",
    ]);
  });

  it("test_AC_PLT_29_clean_bundle_passes", () => {
    const result = checkClientBundle(nextDir, ENV);

    expect(result).toEqual({ code: 0, messages: ["client bundle clean: 5 files checked"] });
  });

  it("test_AC_PLT_29_scans_static_and_prerendered_pages_only", () => {
    put("server/app/inicio.txt", "not served");

    const files = listClientFiles(nextDir).map((file) => file.slice(nextDir.length + 1));

    expect(files.map((file) => file.replaceAll("\\", "/"))).toEqual([
      "server/app/inicio.html",
      "server/app/inicio.meta",
      "server/app/inicio.rsc",
      "static/chunks/main.js",
      "static/css/app.css",
    ]);
  });

  it("test_AC_PLT_29_static_route_body_is_scanned", () => {
    // A force-static route handler: Next writes its response to .body and its headers to .meta.
    put("server/app/config.body", `{"backend":"${SENTINEL}"}`);
    put("server/app/config.meta", `{"headers":{"x-backend":"${SENTINEL}"}}`);

    const result = checkClientBundle(nextDir, ENV);

    expect(result.code).toBe(1);
    expect(result.messages).toEqual([
      "client bundle: server/app/config.body contains the sentinel value of BACKEND_INTERNAL_URL",
      "client bundle: server/app/config.meta contains the sentinel value of BACKEND_INTERNAL_URL",
    ]);
  });

  it("test_AC_PLT_29_partial_or_encoded_sentinel_fails", () => {
    put("static/chunks/host.js", `a="${new URL(SENTINEL).host}";`);
    put("static/chunks/hostname.js", `a="${new URL(SENTINEL).hostname}";`);
    put("static/chunks/encoded.js", `a="${encodeURIComponent(SENTINEL)}";`);

    const result = checkClientBundle(nextDir, ENV);

    expect(result.code).toBe(1);
    expect(result.messages).toEqual(
      ["encoded", "host", "hostname"].map(
        (file) =>
          `client bundle: static/chunks/${file}.js contains the sentinel hostname of BACKEND_INTERNAL_URL`,
      ),
    );
    // Not even the partial value is printed (C-06).
    expect(result.messages.join("\n")).not.toContain(SENTINEL_HOST);
  });

  it("test_AC_PLT_29_non_url_sentinel_is_matched_whole", () => {
    expect(readSentinels({ BACKEND_INTERNAL_URL: "not a url" })).toEqual([
      { name: "BACKEND_INTERNAL_URL", value: "not a url", hostname: undefined },
    ]);
  });

  it("test_AC_PLT_29_cli_entrypoint_runs_the_check", () => {
    // Through the real entrypoint: if its guard did not match, nothing would be checked at all.
    const run = () =>
      spawnSync(process.execPath, [SCRIPT, nextDir], {
        encoding: "utf8",
        env: { ...process.env, ...ENV },
      });

    const clean = run();
    expect(clean.status).toBe(0);
    expect(clean.stdout).toMatch(/^client bundle clean: 5 files checked$/m);

    put("static/chunks/leak.js", SENTINEL_HOST);
    const leaky = run();
    expect(leaky.status).toBe(1);
    expect(leaky.stderr).toContain("static/chunks/leak.js contains the sentinel hostname");
  });

  it("test_AC_PLT_29_prerendered_dir_is_optional", () => {
    rmSync(join(nextDir, "server"), { recursive: true });

    expect(checkClientBundle(nextDir, ENV).code).toBe(0);
  });

  it("test_AC_PLT_29_reports_each_reference_once_per_file", () => {
    const findings = scanText("process.env.X;process.env.X;process.env['X']", "a.js", []);

    expect(findings).toEqual([
      { file: "a.js", reason: "references env.X, which is not NEXT_PUBLIC_" },
    ]);
  });

  it("test_AC_PLT_29_unset_sentinel_is_an_error_not_a_pass", () => {
    const result = checkClientBundle(nextDir, {});

    expect(result.code).toBe(2);
    expect(result.messages[0]).toContain("BACKEND_INTERNAL_URL is not set");
    expect(checkClientBundle(nextDir, { BACKEND_INTERNAL_URL: "" }).code).toBe(2);
  });

  it("test_AC_PLT_29_missing_or_empty_build_is_an_error", () => {
    expect(checkClientBundle(join(nextDir, "nope"), ENV).code).toBe(2);

    rmSync(join(nextDir, "static"), { recursive: true });
    writeFileSync(join(nextDir, "static"), "a file, not a directory");
    expect(checkClientBundle(nextDir, ENV).code).toBe(2);

    rmSync(join(nextDir, "static"));
    rmSync(join(nextDir, "server"), { recursive: true });
    mkdirSync(join(nextDir, "static"));
    const empty = checkClientBundle(nextDir, ENV);
    expect(empty.code).toBe(2);
    expect(empty.messages[0]).toContain("is empty");
  });

  it("test_AC_PLT_29_main_prints_and_returns_the_exit_code", () => {
    const log = vi.spyOn(console, "log").mockImplementation(() => {});
    const error = vi.spyOn(console, "error").mockImplementation(() => {});

    expect(main([nextDir], ENV)).toBe(0);
    expect(log).toHaveBeenCalledWith("client bundle clean: 5 files checked");

    put("static/chunks/leak.js", SENTINEL);
    expect(main([nextDir], ENV)).toBe(1);
    expect(error).toHaveBeenCalledWith(
      "client bundle: static/chunks/leak.js contains the sentinel value of BACKEND_INTERNAL_URL",
    );
  });
});
