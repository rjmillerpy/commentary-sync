/** The API's response shapes, checked when they arrive. One schema per
 * shape (rule 16); each mirrors a Pydantic model in app/.../schema.py.
 * Fields a client doesn't read are left out, and dropped when parsed. */

import { z } from "zod";

export const MIN_PASSWORD_LENGTH = 12;
export const MAX_PASSWORD_LENGTH = 256;
export const MAX_DISPLAY_NAME_LENGTH = 50;
export const MIN_HANDLE_LENGTH = 3;
export const MAX_HANDLE_LENGTH = 30;
export const HANDLE_PATTERN = "[A-Za-z0-9_]+";

export const TokenPairSchema = z.object({
  access_token: z.string(),
  refresh_token: z.string(),
  expires_in: z.number().int(),
});
export type TokenPair = z.infer<typeof TokenPairSchema>;

export const CommentatorSchema = z.object({
  id: z.string(),
  handle: z.string(),
  display_name: z.string(),
  bio: z.string(),
});
export type Commentator = z.infer<typeof CommentatorSchema>;

export const EventStatusSchema = z.enum(["scheduled", "live", "final", "postponed", "cancelled"]);
export type EventStatus = z.infer<typeof EventStatusSchema>;

export const EventSchema = z.object({
  id: z.string(),
  league: z.enum(["nfl", "nba"]),
  title: z.string(),
  starts_at: z.string(),
  status: EventStatusSchema,
  networks: z.array(z.string()),
});
export type SportsEvent = z.infer<typeof EventSchema>;

export const EventPageSchema = z.object({
  items: z.array(EventSchema),
  next_offset: z.number().int().nullable(),
});
export type EventPage = z.infer<typeof EventPageSchema>;

/** Who is talking on a stream: enough for a listener to pick one. */
export const StreamCommentatorSchema = z.object({
  handle: z.string(),
  display_name: z.string(),
});

export const StreamSchema = z.object({
  id: z.string(),
  event_id: z.string(),
  commentator: StreamCommentatorSchema,
  status: z.enum(["live", "ended"]),
  started_at: z.string(),
  /** Accounts listening now; null when the API can't count them. */
  listeners: z.number().int().nullable(),
});
export type Stream = z.infer<typeof StreamSchema>;

export const StreamPageSchema = z.object({
  items: z.array(StreamSchema),
  next_offset: z.number().int().nullable(),
});
export type StreamPage = z.infer<typeof StreamPageSchema>;

/** Where a listener plays a stream's HLS recording. */
export const PlaylistAccessSchema = z.object({ url: z.string() });
export type PlaylistAccess = z.infer<typeof PlaylistAccessSchema>;

export const RoomAccessSchema = z.object({
  url: z.string(),
  room: z.string(),
  token: z.string(),
  expires_in: z.number().int(),
});
export type RoomAccess = z.infer<typeof RoomAccessSchema>;

/** A 4xx body: a sentence, or (422) the list of what was wrong. */
export const ErrorBodySchema = z.object({
  detail: z.union([z.string(), z.array(z.object({ msg: z.string() }))]),
});

/** The server's clock (GET /clock), seconds since the epoch. */
export const ServerTimeSchema = z.object({ now: z.number() });

/** How far the listener's TV is behind the commentator's (POST /streams/{id}/sync). */
export const SyncResultSchema = z.discriminatedUnion("status", [
  z.object({ status: z.literal("matched"), delay_seconds: z.number(), peak_ratio: z.number() }),
  z.object({ status: z.literal("not_found") }),
]);
export type SyncResult = z.infer<typeof SyncResultSchema>;
