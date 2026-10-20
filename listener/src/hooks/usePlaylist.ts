/** The stream's HLS playlist URL. Until the commentator's audio reaches HLS
 * the API answers "no HLS audio yet"; with no connection, or the server
 * failing, there is no answer at all. Both are retried every few seconds:
 * neither is the listener's to fix. */

import { ApiError, HTTP_CONFLICT, NETWORK_ERROR_STATUS, NO_HLS_YET_DETAIL } from "@commentary-sync/client/api";
import { useSession } from "@commentary-sync/client/react";
import { useEffect, useState } from "react";

import { api } from "@/lib/api";

export const PLAYLIST_RETRY_MS = 3_000;

export type PlaylistState =
  | { kind: "waiting" }
  | { kind: "ready"; url: string }
  | { kind: "failed"; detail: string };

export function usePlaylist(streamId: string): PlaylistState {
  const { authorized } = useSession();
  const [state, setState] = useState<PlaylistState>({ kind: "waiting" });

  useEffect(() => {
    let isCurrent = true;
    let retry: ReturnType<typeof setTimeout> | undefined;
    const attempt = () => {
      authorized((token) => api.listenerPlaylist(token, streamId))
        .then(({ url }) => {
          if (isCurrent) setState({ kind: "ready", url });
        })
        .catch((failure: unknown) => {
          if (!isCurrent) return;
          if (isWorthRetrying(failure)) retry = setTimeout(attempt, PLAYLIST_RETRY_MS);
          else setState({ kind: "failed", detail: failure instanceof ApiError ? failure.detail : String(failure) });
        });
    };
    attempt();
    return () => {
      isCurrent = false;
      clearTimeout(retry);
    };
  }, [authorized, streamId]);

  return state;
}

const SERVER_ERROR = 500;

function isWorthRetrying(failure: unknown): boolean {
  if (!(failure instanceof ApiError)) return false;
  const isNotYet = failure.status === HTTP_CONFLICT && failure.detail === NO_HLS_YET_DETAIL;
  return isNotYet || failure.status === NETWORK_ERROR_STATUS || failure.status >= SERVER_ERROR;
}
