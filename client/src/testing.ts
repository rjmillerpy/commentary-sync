/** For tests of anything that calls the API: the API faked at the network
 * boundary. `fetch` answers from a route table and records every request,
 * so the real client code runs. Response fixtures match the API's shapes.
 *
 *   const fake = new FakeApi().on("GET", "/events?limit=100", { status: 200, body: EVENTS }).install();
 */

export interface Recorded {
  method: string;
  path: string;
  /** JSON bodies parsed; anything else (audio) as it was sent. */
  body: unknown;
  contentType: string | null;
  authorization: string | null;
  signal: AbortSignal | null;
}

export interface Reply {
  status: number;
  body?: unknown;
}

export const BASE_URL = "https://api.test";

export class FakeApi {
  readonly requests: Recorded[] = [];
  private readonly routes = new Map<string, Reply[]>();
  /** Make every request fail as if the network were down. */
  offline = false;

  /** Answer `method path` with `replies`, in order; the last one repeats. */
  on(method: string, path: string, ...replies: Reply[]): this {
    this.routes.set(`${method} ${path}`, replies);
    return this;
  }

  install(): this {
    globalThis.fetch = (async (url: string, init: RequestInit = {}) => this.answer(url, init)) as typeof fetch;
    return this;
  }

  paths(): string[] {
    return this.requests.map((request) => `${request.method} ${request.path}`);
  }

  private answer(url: string, init: RequestInit): Response {
    if (this.offline) throw new TypeError("fetch failed");
    const { pathname, search } = new URL(url);
    const headers = (init.headers ?? {}) as Record<string, string>;
    const request: Recorded = {
      method: init.method ?? "GET",
      path: pathname + search,
      body: parseBody(init.body, headers["Content-Type"]),
      contentType: headers["Content-Type"] ?? null,
      authorization: headers.Authorization ?? null,
      signal: init.signal ?? null,
    };
    this.requests.push(request);
    // A route without a query string answers any query (sync stamps a fresh
    // capture time on every request).
    const replies = this.routes.get(`${request.method} ${request.path}`) ?? this.routes.get(`${request.method} ${pathname}`);
    if (replies === undefined) return respond({ status: 404, body: { detail: "Not Found" } });
    const reply = replies.length > 1 ? replies.shift() : replies[0];
    return respond(reply ?? { status: 404 });
  }
}

function parseBody(body: RequestInit["body"], contentType: string | undefined): unknown {
  if (body === undefined || body === null) return null;
  return contentType === "application/json" && typeof body === "string" ? JSON.parse(body) : body;
}

function respond({ status, body }: Reply): Response {
  return new Response(body === undefined ? null : JSON.stringify(body), { status });
}

export const PAIR = { access_token: "access-1", refresh_token: "refresh-1", token_type: "bearer", expires_in: 900 };
export const PAIR_2 = { access_token: "access-2", refresh_token: "refresh-2", token_type: "bearer", expires_in: 900 };
export const COMMENTATOR = { id: "c-1", handle: "fan_cast", display_name: "Fan", bio: "", created_at: "2026-10-17T12:00:00Z" };
export const LIVE_GAME = {
  id: "e-live",
  league: "nfl",
  title: "Houston Texans at Jacksonville Jaguars",
  starts_at: "2026-10-18T17:00:00Z",
  status: "live",
  networks: ["CBS"],
};
export const EVENTS = { items: [LIVE_GAME], limit: 100, offset: 0, next_offset: null };
export const STREAM = {
  id: "s-1",
  event_id: "e-live",
  commentator: { handle: "fan_cast", display_name: "Fan" },
  status: "live",
  started_at: "2026-10-18T17:05:00Z",
  ended_at: null,
  listeners: 3,
};
export const STREAMS = { items: [STREAM], limit: 100, offset: 0, next_offset: null };
export const ROOM = { url: "ws://localhost:7880/", room: "stream-s-1", token: "room-token", expires_in: 600 };
export const PLAYLIST = { url: "http://localhost:8080/abc/index.m3u8" };
export const SYNC_MATCHED = { status: "matched", delay_seconds: 23.5, peak_ratio: 3.2 };
export const SYNC_NOT_FOUND = { status: "not_found", delay_seconds: null, peak_ratio: null };
