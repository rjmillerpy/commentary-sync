import path from "node:path";

import type { NextConfig } from "next";

// Headers every page is served with. The studio needs the microphone and
// nothing else; it is never framed.
const SECURITY_HEADERS = [
  { key: "X-Frame-Options", value: "DENY" },
  { key: "X-Content-Type-Options", value: "nosniff" },
  { key: "Referrer-Policy", value: "no-referrer" },
  { key: "Permissions-Policy", value: "microphone=(self), camera=(), geolocation=(), display-capture=()" },
];

const nextConfig: NextConfig = {
  // A self-contained server in .next/standalone, so the image stays small.
  output: "standalone",
  // The workspace root: the shared client lives beside web/, and the
  // standalone server must include it.
  outputFileTracingRoot: path.join(__dirname, ".."),
  // The shared client is TypeScript source; Next compiles it with the studio.
  transpilePackages: ["@commentary-sync/client"],
  poweredByHeader: false,
  images: { unoptimized: true }, // no next/image here: the optimizer is only attack surface
  async headers() {
    return [{ source: "/:path*", headers: SECURITY_HEADERS }];
  },
};

export default nextConfig;
