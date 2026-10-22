import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import TvCheck from "@/components/TvCheck";
import type { CheckPhase, TvCheckValue } from "@/hooks/useTvCheck";
import type { TvCheckResult, Verdict } from "@/lib/tvCheck";

function check(phase: CheckPhase, verdict: Verdict | null = null): TvCheckValue {
  const result: TvCheckResult | null = verdict === null ? null : { verdict, tvDb: -45, voiceDb: -20, thresholdDb: -39 };
  return { phase, result, start: jest.fn() };
}

const props = { canCheck: true, isTvLouder: false, error: null };

test("before a check, explains it and offers to start", async () => {
  const value = check("idle");
  render(<TvCheck check={value} {...props} />);
  expect(screen.getByText(/stay quiet for 5 seconds, then talk for 5/)).toBeInTheDocument();
  await userEvent.click(screen.getByRole("button", { name: "Start the TV check" }));
  expect(value.start).toHaveBeenCalled();
});

test.each([
  ["quiet", /Stay quiet/],
  ["talking", /Now talk/],
] as const)("while %s, says what to do, and can't be restarted", (phase, prompt) => {
  render(<TvCheck check={check(phase)} {...props} />);
  expect(screen.getByRole("status")).toHaveTextContent(prompt);
  expect(screen.getByRole("button")).toBeDisabled();
});

test.each([
  ["clear", /listeners hear nothing at all\. Your voice is 25 dB louder than the TV\./],
  ["faint", /may faintly hear the TV/],
  ["too-loud", /would go out to listeners/],
  ["no-voice", /^We couldn't hear you\. Check the microphone above, then check again\.$/],
] as const)("the verdict, %s", (verdict, text) => {
  render(<TvCheck check={check("done", verdict)} {...props} />);
  expect(screen.getByRole("status")).toHaveTextContent(text);
  expect(screen.getByRole("button", { name: "Check again" })).toBeEnabled();
});

test("can't check without a running gate, or while live", () => {
  render(<TvCheck check={check("idle")} {...props} canCheck={false} />);
  expect(screen.getByRole("button")).toBeDisabled();
});

test.each([
  ["the TV got louder while live", { isTvLouder: true }, /hearing more of the TV than at your check/],
  ["the browser can't gate", { error: "This browser can't run the TV check." }, /can't run the TV check/],
])("warns when %s", (_case, overrides, text) => {
  render(<TvCheck check={check("done", "clear")} {...props} {...overrides} />);
  expect(screen.getByRole("alert")).toHaveTextContent(text);
});
