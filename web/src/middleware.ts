/** Every page gets a Content-Security-Policy (lib/csp.ts) with a nonce of
 * its own, which Next puts on the scripts it renders. */

import { type NextRequest, NextResponse } from "next/server";

import { API_URL, LIVEKIT_URL } from "@/lib/config";
import { contentSecurityPolicy } from "@/lib/csp";

export const CSP_HEADER = "Content-Security-Policy";

export function middleware(request: NextRequest): NextResponse {
  const nonce = btoa(crypto.randomUUID());
  const policy = contentSecurityPolicy(nonce, {
    apiUrl: API_URL,
    livekitUrl: LIVEKIT_URL,
    isDevelopment: process.env.NODE_ENV === "development",
  });
  // On the request too: that is where Next reads the nonce from.
  const headers = new Headers(request.headers);
  headers.set(CSP_HEADER, policy);
  const response = NextResponse.next({ request: { headers } });
  response.headers.set(CSP_HEADER, policy);
  return response;
}

export const config = {
  // Pages only: static files carry no scripts to protect, and prefetches
  // reuse the page's policy.
  matcher: [
    {
      source: "/((?!_next/static|_next/image|favicon.ico|icon.svg).*)",
      missing: [
        { type: "header", key: "next-router-prefetch" },
        { type: "header", key: "purpose", value: "prefetch" },
      ],
    },
  ],
};
