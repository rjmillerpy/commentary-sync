import type { TvSyncState } from "@/hooks/useTvSync";
import { type SyncInputs, syncStatus, URGENT_KINDS } from "@/lib/syncStatus";

const SYNCED_TV: TvSyncState = { kind: "synced", auto: false, changed: true, at: 1, delay: 12, pauseTv: 0 };
const base: SyncInputs = { tv: SYNCED_TV, phase: "playing", pausedBehind: 0, hasSynced: true, isSyncOn: true, isOnline: true };
const status = (overrides: Partial<SyncInputs>) => syncStatus({ ...base, ...overrides });

test.each<[string, Partial<SyncInputs>, string, string, string | null]>([
  ["in sync", {}, "synced", "Synced with your TV", null],
  ["listening to the TV", { tv: { kind: "recording", auto: false } }, "syncing", "Listening to your TV…", null],
  ["an automatic check", { tv: { kind: "recording", auto: true } }, "syncing", "Checking your TV…", null],
  ["matching", { tv: { kind: "matching", auto: false } }, "syncing", "Lining up with your TV…", null],
  ["building up the delay", { phase: "holding" }, "syncing", "Lining up the commentary…", null],
  ["starting", { phase: "loading" }, "syncing", "Starting the commentary…", null],
  ["drifting", { phase: "drifting" }, "drifting", "Catching up", null],
  ["the TV is ahead", { tv: { ...SYNCED_TV, delay: 4, pauseTv: 3.5 } }, "drifting", "Pause your TV for 3.5 s", "sync"],
  ["correcting gave up", { phase: "stuck" }, "desynced", "Out of sync · Tap to resync", "sync"],
  ["not synced yet", { tv: { kind: "idle" }, hasSynced: false }, "desynced", "Not synced yet · Tap to sync", "sync"],
  ["a sync that didn't hear the TV", { tv: { kind: "not-found", auto: false, misses: 0 } }, "desynced", "Out of sync · Tap to resync", "sync"],
  ["a sync that failed", { tv: { kind: "failed", auto: false, detail: "Couldn't sync", reason: "other" } }, "desynced", "Out of sync · Tap to resync", "sync"],
  ["the microphone refused", { tv: { kind: "failed", auto: false, detail: "x", reason: "microphone" } }, "unavailable", "Can't hear your TV", "settings"],
  ["automatic checks keep missing", { tv: { kind: "not-found", auto: true, misses: 3 } }, "unavailable", "Can't hear your TV", "sync"],
  ["paused by the listener", { phase: "paused", pausedBehind: 42 }, "paused", "You're 0:42 behind · Jump back in", "jump"],
  ["sync turned off", { isSyncOn: false }, "off", "Sync off", "turn-on"],
  ["offline", { isOnline: false }, "syncing", "Reconnecting…", null],
  ["the player reconnecting", { phase: "reconnecting" }, "syncing", "Reconnecting…", null],
])("%s", (_case, overrides, kind, label, action) => {
  expect(status(overrides)).toMatchObject({ kind, label, action });
});

test.each<[string, TvSyncState]>([
  ["an automatic check that missed once", { kind: "not-found", auto: true, misses: 1 }],
  ["an automatic check that failed", { kind: "failed", auto: true, detail: "offline", reason: "other" }],
])("%s says nothing: the status follows playback", (_case, tv) => {
  expect(status({ tv }).kind).toBe("synced");
});

test("the listener's pause beats everything, even being offline (UI rule 1.3)", () => {
  expect(status({ phase: "paused", isOnline: false, isSyncOn: false }).kind).toBe("paused");
});

test("never 'Synced' while drifting, stuck or unsynced (UI rule 0.6)", () => {
  for (const overrides of [{ phase: "drifting" }, { phase: "stuck" }, { hasSynced: false, tv: { kind: "idle" } }] as Partial<SyncInputs>[]) {
    expect(status(overrides).kind).not.toBe("synced");
  }
});

test("only broken sync is urgent for screen readers", () => {
  expect([...URGENT_KINDS].sort()).toEqual(["desynced", "unavailable"]);
});
