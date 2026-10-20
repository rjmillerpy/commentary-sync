import { act, renderHook } from "@testing-library/react-native";

import { useAutoSync } from "@/hooks/useAutoSync";
import { AUTO_CHECK_INTERVAL_MS, SETTLE_MS } from "@/lib/autoSync";

beforeEach(() => jest.useFakeTimers());
afterEach(() => jest.useRealTimers());

const advance = (ms: number) =>
  act(async () => {
    await jest.advanceTimersByTimeAsync(ms);
  });

interface Props {
  enabled: boolean;
  isBusy: boolean;
  triggers: (number | null)[];
}

async function renderAuto(initial: Props) {
  const check = jest.fn();
  const hook = await renderHook((props: Props) => useAutoSync({ ...props, check }), { initialProps: initial });
  return { ...hook, check };
}

test("re-checks every few minutes while enabled", async () => {
  const { check } = await renderAuto({ enabled: true, isBusy: false, triggers: [null] });
  await advance(AUTO_CHECK_INTERVAL_MS * 2);
  expect(check).toHaveBeenCalledTimes(2);
});

test("re-checks a few seconds after a reconnect or a return to the app", async () => {
  const { check, rerender } = await renderAuto({ enabled: true, isBusy: false, triggers: [null, null] });
  await rerender({ enabled: true, isBusy: false, triggers: [1_000, null] });
  await advance(SETTLE_MS - 1);
  expect(check).not.toHaveBeenCalled();
  await advance(1);
  expect(check).toHaveBeenCalledTimes(1);
  await rerender({ enabled: true, isBusy: false, triggers: [1_000, 2_000] });
  await advance(SETTLE_MS);
  expect(check).toHaveBeenCalledTimes(2);
});

test("nothing while disabled, and what happened before enabling isn't news", async () => {
  const { check, rerender } = await renderAuto({ enabled: false, isBusy: false, triggers: [5_000] });
  await advance(AUTO_CHECK_INTERVAL_MS);
  expect(check).not.toHaveBeenCalled();
  await rerender({ enabled: true, isBusy: false, triggers: [5_000] });
  await advance(SETTLE_MS);
  expect(check).not.toHaveBeenCalled();
});

test("a check never starts while a sync is already running", async () => {
  const { check, rerender } = await renderAuto({ enabled: true, isBusy: true, triggers: [null] });
  await advance(AUTO_CHECK_INTERVAL_MS);
  await rerender({ enabled: true, isBusy: true, triggers: [9_000] });
  await advance(SETTLE_MS);
  expect(check).not.toHaveBeenCalled();
});

test("disabling stops the schedule (rule 71)", async () => {
  const { check, rerender } = await renderAuto({ enabled: true, isBusy: false, triggers: [null] });
  await rerender({ enabled: false, isBusy: false, triggers: [null] });
  await advance(AUTO_CHECK_INTERVAL_MS * 3);
  expect(check).not.toHaveBeenCalled();
});
