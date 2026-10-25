import { expect, test } from "../support/fixtures";

import { liveStreamOf, login, serverTime, syncToTv } from "../support/api";
import { SEEDED_GAME } from "../support/stack";
import { Studio } from "../support/studio";
import { roomClipFeatures } from "../support/tone";

// The studio records the room raw while live; a recording of the same room
// sound, sent as a listener's phone would, has to be found in it.
// The fake mic's file starts at the mic check, before going live, so the
// reference starts some seconds into it: the clips are taken from later on.
const REFERENCE_WAIT_MS = 30_000;
const CLIP_FROM = 14;
const CLIP_SECONDS = 8;
const CLIP_STEP_SECONDS = 4;
const AGREEMENT_SECONDS = 0.25;
const OTHER_ROOM_SEED = 2;

test("a listener's TV recording is found in the commentator's room, and gives one delay", async ({
  page,
  request,
}) => {
  const studio = new Studio(page);
  const handle = await studio.signUp("syncer");
  await studio.pickGame(SEEDED_GAME);
  await studio.goLive();
  await expect(page.getByRole("status").filter({ hasText: "Listeners can sync their TVs to yours" })).toBeVisible();
  const stream = await liveStreamOf(request, handle);
  // Any signed-in account can sync; the commentator's own saves a registration.
  const token = await login(request, studio.email);
  await page.waitForTimeout(REFERENCE_WAIT_MS);

  // A listener's TV that played the room's second 14 at `tv`, and second 18 four seconds later.
  const tv = (await serverTime(request)) - 10;
  const first = await syncToTv(request, token, stream.id, roomClipFeatures(CLIP_FROM, CLIP_SECONDS), tv);
  const later = roomClipFeatures(CLIP_FROM + CLIP_STEP_SECONDS, CLIP_SECONDS);
  const second = await syncToTv(request, token, stream.id, later, tv + CLIP_STEP_SECONDS);
  expect(first.status).toBe("matched");
  expect(second.status).toBe("matched");
  expect(Math.abs(first.delay_seconds! - second.delay_seconds!)).toBeLessThan(AGREEMENT_SECONDS);

  const elsewhere = await syncToTv(request, token, stream.id, roomClipFeatures(CLIP_FROM, CLIP_SECONDS, OTHER_ROOM_SEED), tv);
  expect(elsewhere.status, "a different room's sound is not found").toBe("not_found");
  await studio.end();
});
