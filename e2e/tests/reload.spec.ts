import { expect, test } from "../support/fixtures";

import { listenerPlaylist, listenerToken, liveStreamOf, register } from "../support/api";
import { expectTheTone } from "../support/expectations";
import { hearRoom, openListener } from "../support/listener";
import { SEEDED_GAME } from "../support/stack";
import { Studio } from "../support/studio";

test("a reload mid-broadcast resumes the same stream", async ({ page, browser, request }) => {
  const studio = new Studio(page);
  const handle = await studio.signUp("reloader");
  await studio.pickGame(SEEDED_GAME);
  await studio.checkTv();
  await studio.goLive();
  const before = await liveStreamOf(request, handle);
  const listener = await register(request, "listener");
  const playlist = await listenerPlaylist(request, listener, before.id);

  await page.reload();
  await expect(page.getByRole("button", { name: "Resume" })).toBeVisible();
  await studio.checkTv(); // a reload needs a new check
  await studio.resume();

  const after = await liveStreamOf(request, handle);
  expect(after.id, "the same stream, not a new one").toBe(before.id);
  const listening = await openListener(browser);
  expectTheTone(await hearRoom(listening, await listenerToken(request, listener, after.id)));
  expect(await listenerPlaylist(request, listener, after.id), "one playlist all game").toBe(
    playlist,
  );
  await studio.end();
});
