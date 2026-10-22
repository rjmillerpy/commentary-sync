import { expect, test } from "../support/fixtures";

import {
  checkIn,
  listenerPlaylist,
  listenerToken,
  liveStreamOf,
  playlistStatus,
  register,
  streamStatus,
  waitForRecorded,
} from "../support/api";
import { expectSilence, expectTheTone } from "../support/expectations";
import { hearPlaylist, hearRoom, openListener } from "../support/listener";
import { SEEDED_GAME } from "../support/stack";
import { Studio } from "../support/studio";

const BEHIND_LIVE_SECONDS = 4;
const DELAY_TOLERANCE_SECONDS = 1;
const AUDIENCE_WAIT_MS = 15_000; // the studio re-reads the count every 10 s

test("a commentator goes live and a listener hears them, live and delayed", async ({
  page,
  browser,
  request,
}) => {
  const studio = new Studio(page);
  const handle = await studio.signUp("caster");
  await studio.pickGame(SEEDED_GAME);
  expect(await studio.micPeak(), "the mic check meter moves").toBeGreaterThan(0);
  await studio.checkTv();
  await studio.goLive();

  const stream = await liveStreamOf(request, handle);
  const listener = await register(request, "listener");
  const listening = await openListener(browser);

  await test.step("live, over WebRTC", async () => {
    expectTheTone(await hearRoom(listening, await listenerToken(request, listener, stream.id)));
  });

  await test.step("while the commentator pauses, the TV is not broadcast", async () => {
    await studio.pause();
    expectSilence(await hearRoom(listening, await listenerToken(request, listener, stream.id)));
    await studio.talk();
  });

  const playlist = await listenerPlaylist(request, listener, stream.id);
  await test.step("delayed, over HLS", async () => {
    await waitForRecorded(request, playlist, BEHIND_LIVE_SECONDS * 2);
    const heard = await hearPlaylist(listening, playlist, BEHIND_LIVE_SECONDS);
    expectTheTone(heard);
    expect(Math.abs(heard.behindLive - BEHIND_LIVE_SECONDS), `${heard.behindLive} s behind`).toBeLessThan(
      DELAY_TOLERANCE_SECONDS,
    );
  });

  await test.step("the commentator sees who is listening", async () => {
    await checkIn(request, listener, stream.id);
    await expect(page.getByRole("status").filter({ hasText: "1 listening" })).toBeVisible({ timeout: AUDIENCE_WAIT_MS });
  });

  await test.step("ending the stream ends it for everyone", async () => {
    await studio.end();
    expect(await streamStatus(request, stream.id)).toBe("ended");
    expect(await playlistStatus(request, listener, stream.id)).toBe(409);
  });
});
