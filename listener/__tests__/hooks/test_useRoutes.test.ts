import { EVENTS, STREAM } from "@commentary-sync/client/testing";
import { act, renderHook } from "@testing-library/react-native";
import { BackHandler } from "react-native";

import { useRoutes } from "@/hooks/useRoutes";

const GAME = { ...EVENTS.items[0]!, status: "live" as const, league: "nfl" as const };
const STREAM_ROW = { ...STREAM, status: "live" as const };

test("starts on the games, opens deeper screens and goes back", async () => {
  const { result } = await renderHook(useRoutes);
  expect(result.current.current).toEqual({ name: "games" });
  await act(() => result.current.open({ name: "commentators", game: GAME }));
  await act(() => result.current.open({ name: "listen", game: GAME, stream: STREAM_ROW }));
  expect(result.current.current.name).toBe("listen");
  await act(() => result.current.back());
  expect(result.current.current.name).toBe("commentators");
});

test("back on the first screen stays there", async () => {
  const { result } = await renderHook(useRoutes);
  await act(() => result.current.back());
  expect(result.current.current).toEqual({ name: "games" });
});

test("Android's back button goes back a screen, and on the first one is left to the system", async () => {
  const listeners: (() => boolean)[] = [];
  jest.spyOn(BackHandler, "addEventListener").mockImplementation((_event, handler) => {
    listeners.push(handler as () => boolean);
    return { remove: () => listeners.splice(listeners.indexOf(handler as () => boolean), 1) };
  });
  const { result } = await renderHook(useRoutes);
  expect(listeners).toHaveLength(0);
  await act(() => result.current.open({ name: "commentators", game: GAME }));
  let handled = false;
  await act(() => {
    handled = listeners[0]!();
  });
  expect(handled).toBe(true);
  expect(result.current.current.name).toBe("games");
  expect(listeners).toHaveLength(0);
});
