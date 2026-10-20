/** The API, faked at the network boundary: `fetch` answers from a route
 * table and records every request. Nothing inside the studio is mocked. */

export interface Recorded {
  method: string;
  path: string;
  body: unknown;
  authorization: string | null;
}

interface Reply {
  status: number;
  body?: unknown;
}

type Route = Reply | ((request: Recorded) => Reply);

export class FakeApi {
  readonly requests: Recorded[] = [];
  private readonly routes = new Map<string, Route[]>();

  /** Answer `method path` with `reply`. Several replies for one route are
   * used in order, and the last one repeats. */
  on(method: string, path: string, ...replies: Route[]): this {
    this.routes.set(`${method} ${path}`, replies);
    return this;
  }

  /** Make every request fail as if the network were down. */
  offline = false;

  readonly fetch = jest.fn(async (url: string, init: RequestInit = {}): Promise<Response> => {
    if (this.offline) throw new TypeError("Failed to fetch");
    const { pathname, search } = new URL(url);
    const headers = (init.headers ?? {}) as Record<string, string>;
    const request: Recorded = {
      method: init.method ?? "GET",
      path: pathname + search,
      body: typeof init.body === "string" ? JSON.parse(init.body) : (init.body ?? null),
      authorization: headers.Authorization ?? null,
    };
    this.requests.push(request);
    // A route without a query string answers any query (the capture times
    // sync stamps on its requests change every time).
    const replies = this.routes.get(`${request.method} ${request.path}`) ?? this.routes.get(`${request.method} ${pathname}`);
    if (replies === undefined || replies.length === 0) return respond({ status: 404, body: { detail: "Not Found" } });
    const route = replies.length > 1 ? replies.shift()! : replies[0]!;
    return respond(typeof route === "function" ? route(request) : route);
  });

  install(): this {
    globalThis.fetch = this.fetch as unknown as typeof fetch;
    return this;
  }

  paths(): string[] {
    return this.requests.map((request) => `${request.method} ${request.path}`);
  }
}

function respond({ status, body }: Reply): Response {
  // jsdom has no Response; the studio reads only these members.
  return {
    ok: status >= 200 && status < 300,
    status,
    json: async () => {
      if (body === undefined) throw new SyntaxError("Unexpected end of JSON input");
      return body;
    },
  } as Response;
}

export const PAIR = { access_token: "access-1", refresh_token: "refresh-1", token_type: "bearer", expires_in: 900 };
export const PAIR_2 = { access_token: "access-2", refresh_token: "refresh-2", token_type: "bearer", expires_in: 900 };
export const COMMENTATOR = {
  id: "c-1",
  handle: "fan_cast",
  display_name: "Fan",
  bio: "",
  created_at: "2026-10-17T12:00:00Z",
};
export const LIVE_GAME = {
  id: "e-live",
  league: "nfl",
  title: "Houston Texans at Jacksonville Jaguars",
  home_team: "Jacksonville Jaguars",
  away_team: "Houston Texans",
  starts_at: "2026-10-18T17:00:00Z",
  status: "live",
  networks: ["CBS"],
};
export const LATER_GAME = { ...LIVE_GAME, id: "e-later", title: "Lakers at Celtics", league: "nba", status: "scheduled", networks: [] };
export const FINAL_GAME = { ...LIVE_GAME, id: "e-final", title: "Bears at Packers", status: "final" };
export const EVENTS = { items: [LIVE_GAME, LATER_GAME, FINAL_GAME], limit: 100, offset: 0, next_offset: null };
export const STREAM = {
  id: "s-1",
  event_id: "e-live",
  commentator: { handle: "fan_cast", display_name: "Fan" },
  status: "live",
  started_at: "2026-10-18T17:05:00Z",
  ended_at: null,
  listeners: 0,
};
export const ENDED_STREAM = { ...STREAM, status: "ended", ended_at: "2026-10-18T20:05:00Z" };
export const ROOM = { url: "ws://localhost:7880/", room: "stream-s-1", token: "room-token", expires_in: 600 };

/** How the studio asks whether fan_cast left a stream live. */
export const OWN_LIVE_STREAMS = "/streams?commentator=fan_cast&limit=1";
export const NOT_LIVE = { items: [], limit: 1, offset: 0, next_offset: null };
export const STILL_LIVE = { items: [STREAM], limit: 1, offset: 0, next_offset: 1 };

/** The API a signed-in commentator sees, with a live game to go live on. */
export function studioApi(): FakeApi {
  return new FakeApi()
    .on("POST", "/auth/login", { status: 200, body: PAIR })
    .on("POST", "/auth/refresh", { status: 200, body: PAIR_2 })
    .on("POST", "/auth/logout", { status: 204 })
    .on("GET", "/commentators/me", { status: 200, body: COMMENTATOR })
    .on("GET", "/events?limit=100", { status: 200, body: EVENTS })
    .on("GET", OWN_LIVE_STREAMS, { status: 200, body: NOT_LIVE })
    .on("POST", "/streams", { status: 201, body: STREAM })
    .on("POST", "/streams/s-1/publisher-token", { status: 200, body: ROOM })
    .on("POST", "/streams/s-1/end", { status: 200, body: ENDED_STREAM })
    .install();
}
