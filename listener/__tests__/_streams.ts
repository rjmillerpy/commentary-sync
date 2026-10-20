/** Stream fixtures beyond the shared client's. */

import { STREAM } from "@commentary-sync/client/testing";

export const ENDED_STREAM_FIXTURE = { ...STREAM, status: "ended", ended_at: "2026-10-19T20:00:00Z" };
