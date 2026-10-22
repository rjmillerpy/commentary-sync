/** The studio's Content-Security-Policy: what its pages may load and talk to.
 *
 * Scripts: the studio's own files, and inline ones only with this request's
 * nonce (Next marks its own with it). `blob:` for the AudioWorklet that
 * records the room for TV sync (lib/reference.ts), which loads from a blob
 * URL; the voice gate's worklet is the studio's own file (lib/gate.ts).
 * Connections: the API and the LiveKit server only, so an injected
 * script couldn't send anything elsewhere. Never framed.
 */

export interface CspSources {
  apiUrl: string;
  livekitUrl: string;
  /** `next dev` evaluates code and injects styles; a production build doesn't. */
  isDevelopment: boolean;
}

export function contentSecurityPolicy(nonce: string, { apiUrl, livekitUrl, isDevelopment }: CspSources): string {
  const livekit = new URL(livekitUrl);
  // livekit-client checks a failed connection over HTTP(S) at the same host.
  const livekitHttp = `${livekit.protocol === "wss:" ? "https:" : "http:"}//${livekit.host}`;
  const directives: Record<string, string[]> = {
    "default-src": ["'self'"],
    "script-src": ["'self'", `'nonce-${nonce}'`, "blob:", ...(isDevelopment ? ["'unsafe-eval'"] : [])],
    "style-src": ["'self'", ...(isDevelopment ? ["'unsafe-inline'"] : [])],
    "img-src": ["'self'", "data:"],
    "connect-src": ["'self'", new URL(apiUrl).origin, `${livekit.protocol}//${livekit.host}`, livekitHttp],
    "worker-src": ["'self'", "blob:"],
    "object-src": ["'none'"],
    "base-uri": ["'none'"],
    "form-action": ["'self'"],
    "frame-ancestors": ["'none'"],
  };
  return Object.entries(directives)
    .map(([name, sources]) => `${name} ${sources.join(" ")}`)
    .join("; ");
}
