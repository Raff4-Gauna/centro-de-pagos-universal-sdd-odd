import type { NextConfig } from "next";

// design.md §3.3.3. CSP is out of scope until SPEC-01; telemetry is off via NEXT_TELEMETRY_DISABLED=1
// (CI env and the frontend image), not here.
const securityHeaders = [
  { key: "X-Content-Type-Options", value: "nosniff" },
  { key: "Referrer-Policy", value: "same-origin" },
  { key: "X-Frame-Options", value: "DENY" },
  { key: "Permissions-Policy", value: "camera=(), microphone=(), geolocation=()" },
];

const nextConfig: NextConfig = {
  output: "standalone",
  poweredByHeader: false,
  reactStrictMode: true,
  // DRF routes end in `/`: without this Next answers `/api/x/` with a 308 to `/api/x` before the
  // BFF runs, and the BFF keeps the request's trailing slash when it builds the target (Q-061).
  skipTrailingSlashRedirect: true,
  async headers() {
    return [{ source: "/:path*", headers: securityHeaders }];
  },
};

export default nextConfig;
