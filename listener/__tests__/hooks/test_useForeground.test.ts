import { act, renderHook } from "@testing-library/react-native";
import { AppState, type AppStateStatus } from "react-native";

import { useForeground } from "@/hooks/useForeground";

let listeners: ((state: AppStateStatus) => void)[];
const remove = jest.fn();

beforeEach(() => {
  listeners = [];
  remove.mockClear();
  jest.spyOn(AppState, "addEventListener").mockImplementation((_type, listener) => {
    listeners.push(listener as (state: AppStateStatus) => void);
    return { remove } as unknown as ReturnType<typeof AppState.addEventListener>;
  });
});

afterEach(() => jest.restoreAllMocks());

const change = (state: AppStateStatus) => act(() => listeners.forEach((listener) => listener(state)));

test("coming back to the app is timed; going away isn't", async () => {
  const { result } = await renderHook(useForeground);
  expect(result.current).toBeNull();
  await change("background");
  expect(result.current).toBeNull();
  const before = Date.now();
  await change("active");
  expect(result.current).toBeGreaterThanOrEqual(before);
});

test("staying in the app isn't a return", async () => {
  const { result } = await renderHook(useForeground);
  await change("background");
  await change("active");
  const returned = result.current;
  await change("active"); // announced again, without leaving
  expect(result.current).toBe(returned);
});

test("leaving stops listening (rule 71)", async () => {
  const { unmount } = await renderHook(useForeground);
  await unmount();
  expect(remove).toHaveBeenCalled();
});
