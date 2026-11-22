import { act, renderHook } from "@testing-library/react-native";

import { type PlaybackOptions, TICK_MS, useDelayedPlayback } from "@/hooks/useDelayedPlayback";
import { SEEK_COOLDOWN_MS } from "@/lib/delay";
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
  expect(player.preservesPitch).toBe(true); // speed corrections don't change voices
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

test("a new delay is applied at once, by the difference: a fine-tune is heard as it's tapped", async () => {
  const { rerender } = await renderHook(({ delay }: { delay: number }) => useDelayedPlayback(URL, delay), {
    initialProps: { delay: 10 },
  });
  Object.assign(latestPlayer(), { currentTime: 60, currentOffsetFromLive: 10 });
  await rerender({ delay: 25 });
  expect(latestPlayer().seeks).toEqual([-15]);
  await rerender({ delay: 25.1 });
  expect(latestPlayer().seeks.at(-1)).toBeCloseTo(-0.1);
  await tick();
  expect(latestPlayer().seeks).toHaveLength(2); // already there: nothing more to do
});

test("a little off: corrected by speed, not a seek, until back within ±0.25 s", async () => {
  const { result } = await renderHook(() => useDelayedPlayback(URL, 10));
  const player = latestPlayer();
  Object.assign(player, { currentTime: 60, currentOffsetFromLive: 9 }); // 1 s too close to live
  await tick();
  expect(player.playbackRate).toBeCloseTo(0.95);
  expect(result.current.phase).toBe("drifting");
  for (let ticks = 0; ticks < 100 && result.current.phase === "drifting"; ticks += 1) {
    player.advance(TICK_MS / 1_000);
    await tick();
  }
  expect(player.seeks).toEqual([]);
  expect(player.playbackRate).toBe(1);
  expect(result.current.phase).toBe("playing");
});

test("far off: one seek, then at most one every 10 s; three that don't land is stuck", async () => {
  const { result, rerender } = await renderHook(({ jumpAt }: { jumpAt: number }) => useDelayedPlayback(URL, 10, { jumpAt }), {
    initialProps: { jumpAt: 0 },
  });
  const player = latestPlayer();
  Object.assign(player, { currentTime: 60, currentOffsetFromLive: 30, ignoresSeeks: true }); // seeks don't take
  await tick();
  expect(player.seeks).toHaveLength(1);
  await tick();
  expect(player.seeks).toHaveLength(1); // cooling down
  await advance(SEEK_COOLDOWN_MS * 3);
  expect(player.seeks).toHaveLength(4); // one every 10 s
  await advance(SEEK_COOLDOWN_MS);
  expect(result.current.phase).toBe("stuck");
  await advance(SEEK_COOLDOWN_MS * 3);
  expect(player.seeks).toHaveLength(4); // stopped trying
  await rerender({ jumpAt: Date.now() }); // the listener resyncs
  await tick();
  expect(player.seeks).toHaveLength(5);
});

test("paused by the listener: paused, uncorrected, and how far behind keeps growing", async () => {
  const options = (isPausedByListener: boolean): PlaybackOptions => ({ isPausedByListener });
  const { result, rerender } = await renderHook(({ paused }: { paused: boolean }) => useDelayedPlayback(URL, 10, options(paused)), {
    initialProps: { paused: false },
  });
  const player = latestPlayer();
  Object.assign(player, { currentTime: 60, currentOffsetFromLive: 10 });
  await rerender({ paused: true });
  expect(player.playing).toBe(false);
  player.advance(42);
  await tick();
  expect(result.current).toMatchObject({ phase: "paused", behind: 52 });
  expect(player.seeks).toEqual([]);
  await rerender({ paused: false });
  expect(player.playing).toBe(true);
  await tick();
  expect(player.seeks).toEqual([42]); // straight back to 10 s behind
});

test("the commentary's volume is the listener's", async () => {
  const { rerender } = await renderHook(({ volume }: { volume: number }) => useDelayedPlayback(URL, 10, { volume }), {
    initialProps: { volume: 0.4 },
  });
  expect(latestPlayer().volume).toBe(0.4);
  await rerender({ volume: 0.7 });
  expect(latestPlayer().volume).toBe(0.7);
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
