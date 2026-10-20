"use client";

/** Going live, resuming and ending: the stream in the API and the audio in
 * LiveKit, kept in step. */

import { useCallback, useEffect, useRef, useState } from "react";

import * as api from "@/lib/api";
import { ApiError } from "@/lib/api";
import type { Broadcast, ConnectionState } from "@/lib/broadcast";
import type { Stream } from "@commentary-sync/client/schema";
import type { SessionValue } from "@/hooks/useSession";

/** "interrupted": the stream is live in the API but this tab sends no audio:
 * after a reload, or once LiveKit gives up reconnecting. */
export type BroadcastPhase = "idle" | "starting" | "connecting" | "live" | "reconnecting" | "interrupted" | "ending";

const MEDIA_FAILURE = "Couldn't connect your audio. Check your connection and try again.";
const HTTP_CONFLICT = 409;

export interface BroadcastValue {
  phase: BroadcastPhase;
  stream: Stream | null;
  error: string | null;
  start(eventId: string, microphone: MediaStreamTrack): Promise<void>;
  resume(microphone: MediaStreamTrack): Promise<void>;
  end(): Promise<void>;
}

const toPhase = (state: ConnectionState): BroadcastPhase => (state === "disconnected" ? "interrupted" : state);
const describe = (failure: unknown): string => (failure instanceof ApiError ? failure.detail : MEDIA_FAILURE);

export function useBroadcast({ authorized }: Pick<SessionValue, "authorized">, handle: string): BroadcastValue {
  const [phase, setPhase] = useState<BroadcastPhase>("idle");
  const [stream, setStream] = useState<Stream | null>(null);
  const [error, setError] = useState<string | null>(null);
  const { connect, disconnect } = useAudioLink(authorized, setPhase);
  useStillLive(handle, setStream, setPhase);

  const start = useCallback(
    async (eventId: string, microphone: MediaStreamTrack) => {
      setError(null);
      setPhase("starting");
      let live: Stream | null = null;
      try {
        live = await authorized((token) => api.goLive(token, eventId));
        setStream(live);
        await connect(live, microphone);
      } catch (failure) {
        if (live !== null) await endQuietly(authorized, live.id);
        setStream(null);
        setError(describe(failure));
        setPhase("idle");
      }
    },
    [authorized, connect],
  );

  const resume = useCallback(
    async (microphone: MediaStreamTrack) => {
      if (stream === null) return;
      setError(null);
      setPhase("starting");
      try {
        await connect(stream, microphone);
      } catch (failure) {
        // The API may have ended it meanwhile (the grace period ran out).
        const isOver = failure instanceof ApiError && failure.status === HTTP_CONFLICT;
        if (isOver) setStream(null);
        setError(describe(failure));
        setPhase(isOver ? "idle" : "interrupted");
      }
    },
    [connect, stream],
  );

  const end = useCallback(async () => {
    if (stream === null) return;
    setPhase("ending");
    await disconnect();
    await endQuietly(authorized, stream.id);
    setStream(null);
    setPhase("idle");
  }, [authorized, disconnect, stream]);

  return { phase, stream, error, start, resume, end };
}

/** This tab's audio connection to a stream's room: at most one at a time. */
function useAudioLink(authorized: SessionValue["authorized"], setPhase: (phase: BroadcastPhase) => void) {
  const broadcast = useRef<Broadcast | null>(null);
  const disconnect = useCallback(async () => {
    await broadcast.current?.stop();
    broadcast.current = null;
  }, []);
  // Leaving the page stops sending; the API ends the stream once LiveKit
  // reports the commentator gone (app/streams/service.py).
  useEffect(() => () => void broadcast.current?.stop(), []);

  const connect = useCallback(
    async (live: Stream, microphone: MediaStreamTrack) => {
      await disconnect();
      const access = await authorized((token) => api.publisherToken(token, live.id));
      const { startBroadcast } = await import("@/lib/broadcast");
      broadcast.current = await startBroadcast(access, microphone, (state) => setPhase(toPhase(state)));
    },
    [authorized, disconnect, setPhase],
  );
  return { connect, disconnect };
}

/** On opening the studio, pick up a stream this commentator left live (a
 * reload, a crash), so they can resume or end it rather than be told
 * they're already live. */
function useStillLive(
  handle: string,
  setStream: (stream: Stream) => void,
  setPhase: (phase: BroadcastPhase) => void,
): void {
  useEffect(() => {
    let isCurrent = true;
    api
      .liveStreamOf(handle)
      .then((live) => {
        if (!isCurrent || live === null) return;
        setStream(live);
        setPhase("interrupted");
      })
      .catch(() => {
        // Nothing to pick up that we know of; going live reports a live one.
      });
    return () => {
      isCurrent = false;
    };
  }, [handle, setStream, setPhase]);
}

/** End a stream, ignoring failure: if this call is lost, the API ends the
 * stream itself once LiveKit reports the commentator gone. */
async function endQuietly(authorized: SessionValue["authorized"], streamId: string): Promise<void> {
  await authorized((token) => api.endStream(token, streamId)).catch(() => undefined);
}
