import { act, renderHook } from "@testing-library/react-native";

import { TICK_MS, useDelayedPlayback } from "@/hooks/useDelayedPlayback";
import { latestPlayer, players } from "../_fakeVideo";

const URL = "http://hls.test/abc/index.m3u8";

beforeEach(() => jest.useFakeTimers());
afterEach(() => jest.useRealTimers());

async function advance(ms: number): Promise<void> {
  await act(async () => {
    await jest.advanceTimersByTimeAsync(ms);
  });
}

async function tick(): Promise<void> {
  await act(async () => {
    await jest.advanceTimersByTimeAsync(TICK_MS);
  });
}

test("plays the playlist, and keeps playing with the screen off", async () => {
  await renderHook(() => useDelayedPlayback(URL, 10));
  const player = latestPlayer();
  expect(player.source).toBe(URL);
  expect([player.playing, player.staysActiveInBackground, player.showNowPlayingNotification]).toEqual([true, true, true]);
});

test("is loading until the player knows how far behind live it is", async () => {
  const { result } = await renderHook(() => useDelayedPlayback(URL, 10));
  await tick();
  expect(result.current).toEqual({ phase: "loading", behind: null, recoveredAt: null });
});

test("seeks back to the chosen delay when there is recording to spare", async () => {
  const { result } = await renderHook(() => useDelayedPlayback(URL, 10));
  Object.assign(latestPlayer(), { currentTime: 60, currentOffsetFromLive: 3 });
  await tick();
  expect(latestPlayer().seeks).toEqual([-7]);
  await tick();
  expect(result.current).toMatchObject({ phase: "playing", behind: 10 });
});

test("pauses to build up a delay the recording can't reach yet, then plays", async () => {
  const { result } = await renderHook(() => useDelayedPlayback(URL, 10));
  const player = latestPlayer();
  Object.assign(player, { currentTime: 2, currentOffsetFromLive: 3 });
  await tick();
  expect(player.playing).toBe(false);
  expect(result.current.phase).toBe("holding");
  player.advance(7);
  await tick();
  expect(player.playing).toBe(true);
  expect(result.current).toMatchObject({ phase: "playing", behind: 10 });
});

test("a new delay is applied on the next tick", async () => {
  const { rerender } = await renderHook(({ delay }: { delay: number }) => useDelayedPlayback(URL, delay), {
    initialProps: { delay: 10 },
  });
  Object.assign(latestPlayer(), { currentTime: 60, currentOffsetFromLive: 10 });
  await rerender({ delay: 25 });
  await tick();
  expect(latestPlayer().seeks).toEqual([-15]);
});

test("a failed player reconnects by itself, waiting longer each time", async () => {
  const { result } = await renderHook(() => useDelayedPlayback(URL, 10));
  const player = latestPlayer();
  Object.assign(player, { status: "error", keepsFailing: true });
  await tick();
  expect(result.current).toMatchObject({ phase: "reconnecting", behind: null });
  expect(player.reloads).toEqual([]);
  await advance(1_000); // first wait: 1 s
  expect(player.reloads).toEqual([URL]);
  await advance(1_000); // still failing: the next wait is 2 s
  expect(player.reloads).toHaveLength(1);
  await advance(1_500);
  expect(player.reloads).toHaveLength(2);
});

test("back again, it plays at the same delay and says when it came back", async () => {
  const { result } = await renderHook(() => useDelayedPlayback(URL, 10));
  const player = latestPlayer();
  player.status = "error";
  await tick();
  await advance(1_000); // the reload succeeds
  Object.assign(player, { currentTime: 90, currentOffsetFromLive: 25 }); // live moved on while it was down
  await tick();
  expect(player.playing).toBe(true);
  expect(player.seeks).toEqual([15]); // back to 10 s behind
  expect(result.current.recoveredAt).not.toBeNull();
});

test("the phone's connection coming back reloads at once, without waiting", async () => {
  const { rerender } = await renderHook(({ reconnectedAt }: { reconnectedAt: number | null }) => useDelayedPlayback(URL, 10, { reconnectedAt }), {
    initialProps: { reconnectedAt: null as number | null },
  });
  const player = latestPlayer();
  Object.assign(player, { status: "error", keepsFailing: true });
  await tick();
  await rerender({ reconnectedAt: Date.now() });
  expect(player.reloads).toEqual([URL]);
});

test("a reconnect while playing fine reloads nothing", async () => {
  const { rerender } = await renderHook(({ reconnectedAt }: { reconnectedAt: number | null }) => useDelayedPlayback(URL, 10, { reconnectedAt }), {
    initialProps: { reconnectedAt: null as number | null },
  });
  await rerender({ reconnectedAt: Date.now() });
  expect(latestPlayer().reloads).toEqual([]);
});

test("muted, it keeps playing (its place in time doesn't move), silently", async () => {
  const { rerender } = await renderHook(({ isMuted }: { isMuted: boolean }) => useDelayedPlayback(URL, 10, { isMuted }), {
    initialProps: { isMuted: false },
  });
  const player = latestPlayer();
  await rerender({ isMuted: true });
  expect([player.muted, player.playing]).toEqual([true, true]);
  await rerender({ isMuted: false });
  expect(player.muted).toBe(false);
});

test("leaving while waiting to reconnect cancels the reload (rule 71)", async () => {
  const { unmount } = await renderHook(() => useDelayedPlayback(URL, 10));
  const player = latestPlayer();
  player.status = "error";
  await tick();
  await unmount();
  await jest.advanceTimersByTimeAsync(60_000);
  expect(player.reloads).toEqual([]);
});

test("without a playlist yet, nothing ticks", async () => {
  const { result } = await renderHook(() => useDelayedPlayback(null, 10));
  await tick();
  expect(players[0]?.source).toBeNull();
  expect(result.current.phase).toBe("loading");
});

test("leaving stops the checks (rule 71)", async () => {
  const { unmount } = await renderHook(() => useDelayedPlayback(URL, 10));
  const player = latestPlayer();
  Object.assign(player, { currentTime: 60, currentOffsetFromLive: 3 });
  await unmount();
  await jest.advanceTimersByTimeAsync(TICK_MS * 4);
  expect(player.seeks).toEqual([]);
});

test("while suspended it stays paused and doesn't correct; then it plays again", async () => {
  const { rerender } = await renderHook(({ isSuspended }: { isSuspended: boolean }) => useDelayedPlayback(URL, 10, { isSuspended }), {
    initialProps: { isSuspended: false },
  });
  const player = latestPlayer();
  await rerender({ isSuspended: true });
  expect(player.playing).toBe(false);
  Object.assign(player, { currentTime: 60, currentOffsetFromLive: 3 });
  await tick();
  expect(player.seeks).toEqual([]);
  await rerender({ isSuspended: false });
  expect(player.playing).toBe(true);
  await tick();
  expect(player.seeks).toEqual([-7]);
});
