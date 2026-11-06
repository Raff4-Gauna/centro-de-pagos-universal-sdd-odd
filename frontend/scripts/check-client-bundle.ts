// AC-PLT-29 (RN-PLT-16, Q-050, design.md §3.3.3): the client bundle carries no server-only value
// nor the name of a non-public variable.
//
//   node scripts/check-client-bundle.ts [NEXT_DIR]      (NEXT_DIR defaults to .next)
//
// The builder stage of frontend/Dockerfile runs `next build` with a sentinel value in every
// server-only variable and then this script. It scans what reaches a browser: every file under
// NEXT_DIR/static and the prerendered output of NEXT_DIR/server/app (*.html, *.rsc, and the *.body
// and *.meta of static route handlers). It fails when a file contains (1) the value of a
// server-only variable (the sentinel) or, when that value is a URL, its hostname: unique, and it
// survives `new URL(x).host` and encodeURIComponent, (2) the name of a server-only variable, or
// (3) an `env.NAME` / `env["NAME"]` reference (NAME in UPPER_SNAKE case) whose NAME is not
// NEXT_PUBLIC_* (NODE_ENV aside: Next inlines it and it is public by definition).
// Findings never print a value. Exit codes: 0 clean, 1 findings, 2 misconfiguration (no build
// output, a server-only variable unset): never a silent pass. A clean run prints
// `client bundle clean: N files checked`, and the builder stage requires that line: if the
// entrypoint guard below ever stopped matching, this script would exit 0 without checking anything.
//
// Limits (it is a plain text search over the build output):
// - A value transformed beyond percent-encoding is not found: base64, JS or Unicode escapes,
//   strings split or concatenated at runtime, a change of case.
// - Only what exists at build time is scanned: dynamic pages render on request, so what they send
//   is checked by the smoke of the running stack (T-PLT-38).
//
// Runs with Node's built-in type stripping: erasable TypeScript only, node: imports only.
import { existsSync, readdirSync, readFileSync, statSync } from "node:fs";
import { join, relative, sep } from "node:path";
import { pathToFileURL } from "node:url";

// Read by the BFF on the server only (src/lib/server/env.ts). A new server-only variable of the
// frontend is added here, and frontend/Dockerfile gives it a sentinel in the builder stage.
export const SERVER_ONLY_VARIABLES: readonly string[] = ["BACKEND_INTERNAL_URL"];

const PUBLIC_PREFIX = "NEXT_PUBLIC_";
const ALLOWED_ENV_NAMES = new Set(["NODE_ENV"]);
// Not only `process.env.`: Turbopack compiles a client `process.env.X` to `<module>.default.env.X`
// (its process polyfill), so any `env.NAME` / `env["NAME"]` with an env-style name counts.
const ENV_REFERENCE = /\benv(?:\.([A-Z][A-Z0-9_]*)\b|\[\s*["'`]([A-Z][A-Z0-9_]*)["'`]\s*\])/g;
// .body and .meta: the response of a statically generated route handler and its headers.
const PRERENDERED_SUFFIXES = [".html", ".rsc", ".body", ".meta"];

// Only the variables read here matter; process.env fits.
export type Env = Readonly<Record<string, string | undefined>>;

export interface Sentinel {
  name: string;
  value: string;
  hostname?: string;
}

export interface Finding {
  file: string;
  reason: string;
}

export interface CheckResult {
  code: 0 | 1 | 2;
  messages: string[];
}

function walk(dir: string): string[] {
  const files: string[] = [];
  for (const entry of readdirSync(dir, { withFileTypes: true })) {
    const path = join(dir, entry.name);
    if (entry.isDirectory()) {
      files.push(...walk(path));
    } else if (entry.isFile()) {
      files.push(path);
    }
  }
  return files;
}

/** Files served to a browser: all of NEXT_DIR/static plus the prerendered output. */
export function listClientFiles(nextDir: string): string[] {
  const files = walk(join(nextDir, "static"));
  const prerendered = join(nextDir, "server", "app");
  if (existsSync(prerendered)) {
    files.push(
      ...walk(prerendered).filter((file) =>
        PRERENDERED_SUFFIXES.some((suffix) => file.endsWith(suffix)),
      ),
    );
  }
  return files.sort();
}

/** Findings for one file's text; `file` is only used to label them. */
export function scanText(text: string, file: string, sentinels: readonly Sentinel[]): Finding[] {
  const findings: Finding[] = [];
  for (const { name, value, hostname } of sentinels) {
    if (text.includes(value)) {
      findings.push({ file, reason: `contains the sentinel value of ${name}` });
    } else if (hostname && text.includes(hostname)) {
      findings.push({ file, reason: `contains the sentinel hostname of ${name}` });
    }
  }
  for (const name of SERVER_ONLY_VARIABLES) {
    if (text.includes(name)) {
      findings.push({ file, reason: `contains the server-only variable name ${name}` });
    }
  }
  const referenced = new Set<string>();
  for (const match of text.matchAll(ENV_REFERENCE)) {
    const name = match[1] ?? match[2];
    if (!name.startsWith(PUBLIC_PREFIX) && !ALLOWED_ENV_NAMES.has(name)) {
      referenced.add(name);
    }
  }
  for (const name of [...referenced].sort()) {
    findings.push({
      file,
      reason: `references env.${name}, which is not ${PUBLIC_PREFIX}`,
    });
  }
  return findings;
}

/** The hostname of a URL value; undefined for anything else (a token has no partial form). */
function sentinelHostname(value: string): string | undefined {
  return URL.canParse(value) ? new URL(value).hostname || undefined : undefined;
}

/** Sentinels from the environment; a server-only variable that is unset is an error. */
export function readSentinels(env: Env): Sentinel[] | string {
  const sentinels: Sentinel[] = [];
  for (const name of SERVER_ONLY_VARIABLES) {
    const value = env[name];
    if (!value) {
      return `${name} is not set: build and check with a sentinel value in it`;
    }
    sentinels.push({ name, value, hostname: sentinelHostname(value) });
  }
  return sentinels;
}

export function checkClientBundle(nextDir: string, env: Env): CheckResult {
  const sentinels = readSentinels(env);
  if (typeof sentinels === "string") {
    return { code: 2, messages: [sentinels] };
  }
  const staticDir = join(nextDir, "static");
  if (!existsSync(staticDir) || !statSync(staticDir).isDirectory()) {
    return { code: 2, messages: [`no client bundle at ${staticDir}: run next build first`] };
  }
  const files = listClientFiles(nextDir);
  if (files.length === 0) {
    return { code: 2, messages: [`the client bundle at ${staticDir} is empty`] };
  }
  const findings = files.flatMap((file) =>
    scanText(readFileSync(file, "utf8"), relative(nextDir, file).split(sep).join("/"), sentinels),
  );
  if (findings.length > 0) {
    return {
      code: 1,
      messages: findings.map(({ file, reason }) => `client bundle: ${file} ${reason}`),
    };
  }
  return { code: 0, messages: [`client bundle clean: ${files.length} files checked`] };
}

export function main(argv: readonly string[], env: Env): number {
  const result = checkClientBundle(argv[0] ?? ".next", env);
  const write = result.code === 0 ? console.log : console.error;
  for (const message of result.messages) {
    write(message);
  }
  return result.code;
}

if (process.argv[1] && import.meta.url === pathToFileURL(process.argv[1]).href) {
  process.exitCode = main(process.argv.slice(2), process.env);
}
