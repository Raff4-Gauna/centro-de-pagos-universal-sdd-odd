import "server-only";

// Server-only configuration of the BFF (RN-PLT-16, Q-050). The backend URL is internal: it is
// read from the server's environment on every call (never frozen into the build, never a public
// client-exposed variable) and error messages never echo the configured value (C-06).
const ALLOWED_PROTOCOLS = new Set(["http:", "https:"]);

export function getBackendInternalUrl(): URL {
  const raw = process.env.BACKEND_INTERNAL_URL;
  if (!raw) {
    throw new Error("BACKEND_INTERNAL_URL is not set");
  }
  let url: URL;
  try {
    url = new URL(raw);
  } catch {
    throw new Error("BACKEND_INTERNAL_URL is not a valid URL");
  }
  if (!ALLOWED_PROTOCOLS.has(url.protocol)) {
    throw new Error("BACKEND_INTERNAL_URL is not a valid http(s) URL");
  }
  return url;
}
