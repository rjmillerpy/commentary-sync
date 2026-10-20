import { randomUUID } from "node:crypto";

import { type APIRequestContext, expect } from "@playwright/test";

import { API_URL } from "./stack";

// The API, called the way a client calls it. Each test makes its own
// accounts; registrations are limited to 5 an hour per address, and the whole
// suite comes from one, so the suite stays under that.
export const PASSWORD = "correct horse battery staple";
const PLAYLIST_WAIT_MS = 30_000;

export interface RoomAccess {
  url: string;
  room: string;
  token: string;
  expires_in: number;
}

export interface Stream {
  id: string;
  status: "live" | "ended";
}

export function uniqueEmail(tag: string): string {
  return `${tag}-${randomUUID()}@example.com`;
}

/** A new account's access token. */
export async function register(request: APIRequestContext, tag: string): Promise<string> {
  const response = await request.post(`${API_URL}/auth/register`, {
    data: { email: uniqueEmail(tag), password: PASSWORD, display_name: tag },
  });
  expect(response.status(), await response.text()).toBe(201);
  return ((await response.json()) as { access_token: string }).access_token;
}

/** The commentator's live stream, as anyone sees it. */
export async function liveStreamOf(request: APIRequestContext, handle: string): Promise<Stream> {
  const response = await request.get(`${API_URL}/streams`, {
    params: { commentator: handle, limit: 1 },
  });
  const page = (await response.json()) as { items: Stream[] };
  const stream = page.items[0];
  if (stream === undefined) {
    throw new Error(`@${handle} is not live`);
  }
  return stream;
}

export async function streamStatus(request: APIRequestContext, id: string): Promise<string> {
  const response = await request.get(`${API_URL}/streams/${id}`);
  return ((await response.json()) as Stream).status;
}

export async function listenerToken(
  request: APIRequestContext,
  accessToken: string,
  streamId: string,
): Promise<RoomAccess> {
  const response = await request.post(`${API_URL}/streams/${streamId}/listener-token`, {
    headers: { Authorization: `Bearer ${accessToken}` },
  });
  expect(response.status(), await response.text()).toBe(200);
  return (await response.json()) as RoomAccess;
}

/** The stream's HLS playlist URL, once its recording has started (a 409 until then). */
export async function listenerPlaylist(
  request: APIRequestContext,
  accessToken: string,
  streamId: string,
): Promise<string> {
  let url = "";
  await expect
    .poll(
      async () => {
        const response = await playlistResponse(request, accessToken, streamId);
        if (response.status() === 200) {
          url = ((await response.json()) as { url: string }).url;
        }
        return response.status();
      },
      { timeout: PLAYLIST_WAIT_MS },
    )
    .toBe(200);
  return url;
}

export async function playlistStatus(
  request: APIRequestContext,
  accessToken: string,
  streamId: string,
): Promise<number> {
  return (await playlistResponse(request, accessToken, streamId)).status();
}

function playlistResponse(request: APIRequestContext, accessToken: string, streamId: string) {
  return request.post(`${API_URL}/streams/${streamId}/listener-playlist`, {
    headers: { Authorization: `Bearer ${accessToken}` },
  });
}

/** Waits until the playlist holds at least `seconds` of audio. A player can't
 * sit further behind live than the recording reaches back. */
export async function waitForRecorded(
  request: APIRequestContext,
  playlistUrl: string,
  seconds: number,
): Promise<void> {
  await expect
    .poll(async () => recordedSeconds(await (await request.get(playlistUrl)).text()), {
      timeout: PLAYLIST_WAIT_MS,
    })
    .toBeGreaterThanOrEqual(seconds);
}

/** The audio an HLS playlist lists: the sum of its #EXTINF durations. */
export function recordedSeconds(playlist: string): number {
  return playlist
    .split("\n")
    .filter((line) => line.startsWith("#EXTINF:"))
    .reduce((total, line) => total + Number.parseFloat(line.slice("#EXTINF:".length)), 0);
}

/** An access token for an existing account: a session of its own, beside the browser's. */
export async function login(request: APIRequestContext, email: string): Promise<string> {
  const response = await request.post(`${API_URL}/auth/login`, { data: { email, password: PASSWORD } });
  expect(response.status(), await response.text()).toBe(200);
  return ((await response.json()) as { access_token: string }).access_token;
}

export async function serverTime(request: APIRequestContext): Promise<number> {
  return ((await (await request.get(`${API_URL}/clock`)).json()) as { now: number }).now;
}

export interface SyncResult {
  status: "matched" | "not_found";
  delay_seconds?: number;
}

/** What the listener app sends: the features of what it heard of the TV, from `capturedAt` (server time). */
export async function syncToTv(
  request: APIRequestContext,
  accessToken: string,
  streamId: string,
  features: Float32Array,
  capturedAt: number,
): Promise<SyncResult> {
  const response = await request.post(`${API_URL}/streams/${streamId}/sync`, {
    params: { captured_at: capturedAt },
    headers: { Authorization: `Bearer ${accessToken}`, "Content-Type": "application/octet-stream" },
    data: Buffer.from(features.buffer, features.byteOffset, features.byteLength),
  });
  expect(response.status(), await response.text()).toBe(200);
  return (await response.json()) as SyncResult;
}

/** What the listener app sends every 20 s while it plays a stream. */
export async function checkIn(request: APIRequestContext, accessToken: string, streamId: string): Promise<void> {
  const response = await request.post(`${API_URL}/streams/${streamId}/listening`, {
    headers: { Authorization: `Bearer ${accessToken}` },
  });
  expect(response.status(), await response.text()).toBe(204);
}
