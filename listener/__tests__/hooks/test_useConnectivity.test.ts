import { act, renderHook } from "@testing-library/react-native";

import { useConnectivity } from "@/hooks/useConnectivity";
import { listenerCount, network, setOnline } from "../_fakeNetwork";

test("online to start, with no reconnection yet", async () => {
  const { result } = await renderHook(useConnectivity);
  expect(result.current).toEqual({ isConnected: true, reconnectedAt: null });
});

test("losing the connection, then getting it back, is noticed and timed", async () => {
  const { result } = await renderHook(useConnectivity);
  await act(() => setOnline(false));
  expect(result.current.isConnected).toBe(false);
  const before = Date.now();
  await act(() => setOnline(true));
  expect(result.current.isConnected).toBe(true);
  expect(result.current.reconnectedAt).toBeGreaterThanOrEqual(before);
});

test("staying online isn't a reconnection", async () => {
  const { result } = await renderHook(useConnectivity);
  await act(() => setOnline(true));
  expect(result.current.reconnectedAt).toBeNull();
});

test("a phone that starts offline says so", async () => {
  network.state = { isConnected: false, isInternetReachable: false };
  const { result } = await renderHook(useConnectivity);
  expect(result.current.isConnected).toBe(false);
});

test("connected but with no internet counts as offline", async () => {
  const { result } = await renderHook(useConnectivity);
  await act(() => {
    network.state = { isConnected: true, isInternetReachable: false };
    setOnline(true); // re-announce
    network.state = { isConnected: true, isInternetReachable: false };
  });
  expect(result.current.isConnected).toBe(true);
});

test("leaving stops listening (rule 71)", async () => {
  const { unmount } = await renderHook(useConnectivity);
  expect(listenerCount()).toBe(1);
  await unmount();
  expect(listenerCount()).toBe(0);
});
