import type { Metadata } from "next";
import type { ReactNode } from "react";

import "./globals.css";

// Rendered for each request, so Next can put the request's CSP nonce
// (src/middleware.ts) on its scripts.
export const dynamic = "force-dynamic";

export const metadata: Metadata = {
  title: "commentary-sync studio",
  description: "Go live with your commentary over the TV broadcast.",
};

export default function RootLayout({ children }: { children: ReactNode }) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  );
}
