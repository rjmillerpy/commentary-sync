/** The commentary-sync API: one function per endpoint the clients use.
 * Stateless: calls that need an account take its access token.
 *
 *   const api = createApi({ baseUrl: "https://api.example.com", timeoutMs: 10_000 });
 *   const events = await api.upcomingEvents();
 */

import { z } from "zod";

import {
  type Commentator,
  CommentatorSchema,
  ErrorBodySchema,
  type EventPage,
  EventPageSchema,
  type PlaylistAccess,
  PlaylistAccessSchema,
  type RoomAccess,
  RoomAccessSchema,
  type Stream,
  type StreamPage,
  StreamPageSchema,
  StreamSchema,
  type SyncResult,
  SyncResultSchema,
  ServerTimeSchema,
  type TokenPair,
  TokenPairSchema,
} from "./schema.ts";
import type { Features } from "./features.ts";

export const HTTP_NO_CONTENT = 204;
export const HTTP_UNAUTHORIZED = 401;
export const HTTP_NOT_FOUND = 404;
export const HTTP_CONFLICT = 409;
export const NETWORK_ERROR_STATUS = 0;
const EVENTS_PAGE_SIZE = 100;
const STREAMS_PAGE_SIZE = 100;
// The API's 409 for a stream whose audio hasn't reached HLS yet, as opposed
// to one that has ended (app/streams/views.py); the first is worth retrying.
export const NO_HLS_YET_DETAIL = "This stream has no HLS audio yet";
const GENERIC_DETAIL = "Something went wrong; try again.";
const NETWORK_DETAIL = "Can't reach the server. Check your connection and try again.";

/** A failed call: the HTTP status (0 for no answer at all) and a sentence
 * that can be shown to the user as it is. */
export class ApiError extends Error {
  readonly status: number;
  readonly detail: string;

  constructor(status: number, detail: string) {
    super(detail);
    this.name = "ApiError";
    this.status = status;
    this.detail = detail;
  }
}

export interface ApiConfig {
  /** The API's address, with or without a trailing slash. */
  baseUrl: string;
  /** Every call gives up after this long (rule 67). */
  timeoutMs: number;
}

export interface Registration {
  email: string;
  password: string;
  display_name: string;
}

type Method = "GET" | "POST" | "PATCH";

interface Call<T> {
  method: Method;
  path: string;
  schema: z.ZodType<T>;
  /** Sent as JSON. */
  body?: unknown;
  /** Sent as it is: audio. */
  audio?: AudioBody;
  token?: string;
}

/** Raw bytes for the sync endpoints: reference audio, or features. */
export type AudioBody = ArrayBuffer | ArrayBufferView | Blob;

const OCTET_STREAM = "application/octet-stream";

const Nothing = z.null();

export type Api = ReturnType<typeof createApi>;

export function createApi({ baseUrl, timeoutMs }: ApiConfig) {
  const root = baseUrl.replace(/\/+$/, "");
  const call = <T>(request: Call<T>): Promise<T> => send(root, timeoutMs, request);
  const streamPath = (streamId: string, action: string) => `/streams/${encodeURIComponent(streamId)}/${action}`;

  return {
    register: (registration: Registration): Promise<TokenPair> =>
      call({ method: "POST", path: "/auth/register", schema: TokenPairSchema, body: registration }),

    login: (email: string, password: string): Promise<TokenPair> =>
      call({ method: "POST", path: "/auth/login", schema: TokenPairSchema, body: { email, password } }),

    refresh: (refreshToken: string): Promise<TokenPair> =>
      call({ method: "POST", path: "/auth/refresh", schema: TokenPairSchema, body: { refresh_token: refreshToken } }),

    logout: (refreshToken: string): Promise<null> =>
      call({ method: "POST", path: "/auth/logout", schema: Nothing, body: { refresh_token: refreshToken } }),

    myCommentatorProfile: (token: string): Promise<Commentator> =>
      call({ method: "GET", path: "/commentators/me", schema: CommentatorSchema, token }),

    becomeCommentator: (token: string, handle: string): Promise<Commentator> =>
      call({ method: "POST", path: "/commentators", schema: CommentatorSchema, body: { handle }, token }),

    /** Games from four hours ago on (the API's default), soonest first. */
    upcomingEvents: (): Promise<EventPage> =>
      call({ method: "GET", path: `/events?limit=${EVENTS_PAGE_SIZE}`, schema: EventPageSchema }),

    /** Who is live on one game, longest-running first. */
    liveStreamsOn: (eventId: string): Promise<StreamPage> => {
      const query = new URLSearchParams({ event_id: eventId, limit: String(STREAMS_PAGE_SIZE) });
      return call({ method: "GET", path: `/streams?${query}`, schema: StreamPageSchema });
    },

    /** The commentator's live stream, if they have one (at most one at a time). */
    liveStreamOf: async (handle: string): Promise<Stream | null> => {
      const query = new URLSearchParams({ commentator: handle, limit: "1" });
      const page = await call({ method: "GET", path: `/streams?${query}`, schema: StreamPageSchema });
      return page.items[0] ?? null;
    },

    /** One stream, live or ended. */
    getStream: (streamId: string): Promise<Stream> =>
      call({ method: "GET", path: `/streams/${encodeURIComponent(streamId)}`, schema: StreamSchema }),

    goLive: (token: string, eventId: string): Promise<Stream> =>
      call({ method: "POST", path: "/streams", schema: StreamSchema, body: { event_id: eventId }, token }),

    endStream: (token: string, streamId: string): Promise<Stream> =>
      call({ method: "POST", path: streamPath(streamId, "end"), schema: StreamSchema, token }),

    publisherToken: (token: string, streamId: string): Promise<RoomAccess> =>
      call({ method: "POST", path: streamPath(streamId, "publisher-token"), schema: RoomAccessSchema, token }),

    /** The server's clock, in seconds since the epoch (see clock.ts). */
    serverTime: async (): Promise<number> => (await call({ method: "GET", path: "/clock", schema: ServerTimeSchema })).now,

    /** A chunk of the commentator's room audio: 16-bit mono PCM at 8 kHz,
     * whose first sample was captured at `capturedAt` (server time). */
    sendReference: (token: string, streamId: string, pcm: AudioBody, capturedAt: number): Promise<null> =>
      call({
        method: "POST",
        path: `${streamPath(streamId, "reference")}?${capturedAtQuery(capturedAt)}`,
        schema: Nothing,
        audio: pcm,
        token,
      }),

    /** The matcher's features (features.ts) of what the listener's phone
     * heard of their TV, from `capturedAt` (server time): how far behind the
     * commentator's TV it is. The audio itself is never sent. */
    syncToTv: (token: string, streamId: string, features: Features, capturedAt: number): Promise<SyncResult> =>
      call({
        method: "POST",
        path: `${streamPath(streamId, "sync")}?${capturedAtQuery(capturedAt)}`,
        schema: SyncResultSchema,
        // Float32Array is little-endian on every phone and browser CPU, as the API reads it.
        audio: features.values,
        token,
      }),

    /** "I'm listening": a listener's app sends this every 20 s while it plays a stream. */
    listening: (token: string, streamId: string): Promise<null> =>
      call({ method: "POST", path: streamPath(streamId, "listening"), schema: Nothing, token }),

    /** The stream's HLS playlist. A 409 until the commentator's audio
     * connects, and once the stream has ended. */
    listenerPlaylist: (token: string, streamId: string): Promise<PlaylistAccess> =>
      call({ method: "POST", path: streamPath(streamId, "listener-playlist"), schema: PlaylistAccessSchema, token }),
  };
}

function capturedAtQuery(capturedAt: number): string {
  return new URLSearchParams({ captured_at: String(capturedAt) }).toString();
}

function requestBody(body: unknown, audio: AudioBody | undefined): { contentType?: string; payload?: BodyInit } {
  if (audio !== undefined) return { contentType: OCTET_STREAM, payload: audio as BodyInit };
  if (body !== undefined) return { contentType: "application/json", payload: JSON.stringify(body) };
  return {};
}

async function send<T>(root: string, timeoutMs: number, { method, path, schema, body, audio, token }: Call<T>): Promise<T> {
  const headers: Record<string, string> = {};
  const { contentType, payload: requestPayload } = requestBody(body, audio);
  if (contentType !== undefined) headers["Content-Type"] = contentType;
  if (token !== undefined) headers.Authorization = `Bearer ${token}`;
  let response: Response;
  try {
    response = await fetch(`${root}${path}`, {
      method,
      headers,
      body: requestPayload,
      signal: AbortSignal.timeout(timeoutMs),
    });
  } catch {
    // Offline, DNS, CORS or the timeout: the platform gives no more detail.
    throw new ApiError(NETWORK_ERROR_STATUS, NETWORK_DETAIL);
  }
  if (!response.ok) throw new ApiError(response.status, await errorDetail(response));
  const payload: unknown = response.status === HTTP_NO_CONTENT ? null : await response.json();
  return schema.parse(payload);
}

async function errorDetail(response: Response): Promise<string> {
  const parsed = ErrorBodySchema.safeParse(await response.json().catch(() => null));
  if (!parsed.success) return GENERIC_DETAIL;
  const { detail } = parsed.data;
  return typeof detail === "string" ? detail : detail.map((issue) => issue.msg).join("; ");
}
