import { ApiError } from "@commentary-sync/client/api";
import { act, renderHook, waitFor } from "@testing-library/react-native";

import { useLoad } from "@/hooks/useLoad";

test("loads once, then holds the data", async () => {
  const load = jest.fn(async () => ["a"]);
  const { result } = await renderHook(() => useLoad(load));
  await waitFor(() => expect(result.current.isLoading).toBe(false));
  expect(result.current).toMatchObject({ data: ["a"], error: null });
  expect(load).toHaveBeenCalledTimes(1);
});

test("a failure is a sentence for the screen, and reload tries again", async () => {
  const load = jest.fn().mockRejectedValueOnce(new ApiError(0, "Can't reach the server.")).mockResolvedValue(["b"]);
  const { result } = await renderHook(() => useLoad(load));
  await waitFor(() => expect(result.current.error).toBe("Can't reach the server."));
  await act(() => result.current.reload());
  await waitFor(() => expect(result.current.data).toEqual(["b"]));
  expect(result.current.error).toBeNull();
});

test("a failure that isn't the API's is still explained", async () => {
  const { result } = await renderHook(() => useLoad(async () => Promise.reject(new TypeError("x"))));
  await waitFor(() => expect(result.current.error).toBe("Something went wrong; try again."));
});

test("a load that finishes after unmount changes nothing (rule 71)", async () => {
  let finish: (value: string[]) => void = () => undefined;
  const load = () => new Promise<string[]>((resolve) => (finish = resolve));
  const { result, unmount } = await renderHook(() => useLoad(load));
  await unmount();
  finish(["late"]);
  expect(result.current.data).toBeNull();
});
