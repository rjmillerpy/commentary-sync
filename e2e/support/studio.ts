import { randomUUID } from "node:crypto";

import { expect, type Page } from "@playwright/test";

import { PASSWORD, uniqueEmail } from "./api";
import { controlRoomVolume, setRoomVolume, TV_VOLUME, VOICE_VOLUME } from "./room";

const LIVE_TEXT = "Live: listeners can hear you";
const METER_SAMPLES = 20;
const METER_INTERVAL_MS = 100;
const CHECK_STEP_MS = 10_000; // each half of the TV check takes 5 s

/** The broadcaster studio, driven the way a commentator uses it. */
export class Studio {
  /** The account's email, once signed up: tests sign in as it over the API too. */
  email = "";

  constructor(readonly page: Page) {}

  /** Creates an account and a commentator profile; returns the handle. */
  async signUp(tag: string): Promise<string> {
    const handle = `${tag}_${randomUUID().slice(0, 8)}`;
    await controlRoomVolume(this.page);
    await this.page.goto("/");
    await this.page.getByRole("button", { name: "Create an account instead" }).click();
    await this.page.getByLabel("Display name").fill(tag);
    this.email = uniqueEmail(tag);
    await this.page.getByLabel("Email").fill(this.email);
    await this.page.getByLabel("Password").fill(PASSWORD);
    await this.page.getByRole("button", { name: "Create account" }).click();
    await this.page.getByRole("textbox", { name: "Handle", exact: true }).fill(handle);
    await this.page.getByRole("button", { name: "Become a commentator" }).click();
    await expect(this.page.getByText(`@${handle}`)).toBeVisible();
    return handle;
  }

  async pickGame(title: string): Promise<void> {
    await this.page.getByRole("radio", { name: new RegExp(title) }).check();
  }

  /** The loudest the mic-check meter reads over two seconds. */
  async micPeak(): Promise<number> {
    const meter = this.page.getByRole("meter");
    let peak = 0;
    for (let sample = 0; sample < METER_SAMPLES; sample += 1) {
      peak = Math.max(peak, Number(await meter.getAttribute("value")));
      await this.page.waitForTimeout(METER_INTERVAL_MS);
    }
    return peak;
  }

  /** The TV check: quiet with only the TV, then talking. The TV is about
   * 30 dB below the voice, which the check calls clear. */
  async checkTv(): Promise<void> {
    await setRoomVolume(this.page, TV_VOLUME);
    await this.page.getByRole("button", { name: /Start the TV check|Check again/ }).click();
    await expect(this.page.getByText(/Now talk/)).toBeVisible({ timeout: CHECK_STEP_MS });
    await setRoomVolume(this.page, VOICE_VOLUME);
    await expect(this.page.getByText(/listeners hear nothing at all/)).toBeVisible({ timeout: CHECK_STEP_MS });
  }

  /** The commentator pauses: only the TV is heard in the room. */
  async pause(): Promise<void> {
    await setRoomVolume(this.page, TV_VOLUME);
  }

  async talk(): Promise<void> {
    await setRoomVolume(this.page, VOICE_VOLUME);
  }

  async goLive(): Promise<void> {
    await this.page.getByRole("button", { name: "Go live" }).click();
    await expect(this.page.getByText(LIVE_TEXT)).toBeVisible();
  }

  async resume(): Promise<void> {
    await this.page.getByRole("button", { name: "Resume" }).click();
    await expect(this.page.getByText(LIVE_TEXT)).toBeVisible();
  }

  async end(): Promise<void> {
    await this.page.getByRole("button", { name: "End stream" }).click();
    await expect(this.page.getByText("Off air")).toBeVisible();
  }
}
