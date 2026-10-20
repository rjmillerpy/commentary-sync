import type { Browser, Page } from "@playwright/test";

import type { RoomAccess } from "./api";

// A listener in its own browser context, hearing a stream the two ways the
// listener app will: live over WebRTC (LiveKit's own browser SDK), and
// delayed over HLS (hls.js, which browsers without native HLS use, held
// behind live by its liveSyncDuration). Both feed a Web Audio analyser, which
// reports the loudest frequency it heard.

export interface Heard {
  frequency: number; // Hz, of the loudest analyser bin seen
  level: number; // dBFS of that bin
}

export interface HeardBehindLive extends Heard {
  behindLive: number; // seconds between the playhead and the live edge
}

const LISTEN_MS = 3_000;
// The package's `require` entry is its browser bundle (UMD), which defines
// window.LivekitClient when loaded as a script.
const LIVEKIT_BUNDLE = require.resolve("livekit-client");
// Likewise hls.js's: window.Hls.
const HLS_BUNDLE = require.resolve("hls.js");
// How far hls.js may drift past the chosen delay before it jumps back.
const DELAY_SLACK_SECONDS = 10;

declare global {
  interface Window {
    // livekit-client's UMD bundle names its global LivekitClient.
    LivekitClient: typeof import("livekit-client");
    Hls: typeof import("hls.js").default;
    meter: { listen(source: AudioNode, ms: number): Promise<Heard> };
  }
}

export async function openListener(browser: Browser): Promise<Page> {
  const context = await browser.newContext();
  const page = await context.newPage();
  await page.addScriptTag({ path: LIVEKIT_BUNDLE });
  await page.addScriptTag({ path: HLS_BUNDLE });
  await page.addScriptTag({ content: `(${installMeter.toString()})();` });
  return page;
}

/** Joins the stream's room with a listener token and listens. */
export async function hearRoom(page: Page, access: RoomAccess): Promise<Heard> {
  return page.evaluate(
    async ({ url, token, ms }) => {
      const { Room, RoomEvent, Track } = window.LivekitClient;
      const room = new Room();
      const subscribed = new Promise<import("livekit-client").RemoteTrack>((resolve) => {
        room.on(RoomEvent.TrackSubscribed, (track) => {
          if (track.kind === Track.Kind.Audio) resolve(track);
        });
      });
      await room.connect(url, token);
      const track = await subscribed;
      // Chrome only feeds a remote WebRTC stream to Web Audio while a media
      // element plays it; muted, so the analyser is the only thing hearing it.
      const element = track.attach();
      element.muted = true;
      document.body.append(element);
      const context = new AudioContext();
      const source = context.createMediaStreamSource(new MediaStream([track.mediaStreamTrack]));
      const heard = await window.meter.listen(source, ms);
      await room.disconnect();
      await context.close();
      return heard;
    },
    { url: access.url, token: access.token, ms: LISTEN_MS },
  );
}

/** Plays the stream's HLS playlist `behindLive` seconds behind the live edge, and listens. */
export async function hearPlaylist(
  page: Page,
  url: string,
  behindLive: number,
): Promise<HeardBehindLive> {
  return page.evaluate(
    async ({ url, behindLive, slack, ms }) => {
      const Hls = window.Hls;
      const hls = new Hls({
        liveSyncDuration: behindLive,
        liveMaxLatencyDuration: behindLive + slack,
      });
      const audio = new Audio();
      document.body.append(audio);
      const parsed = new Promise((resolve) => hls.once(Hls.Events.MANIFEST_PARSED, resolve));
      hls.loadSource(url);
      hls.attachMedia(audio);
      await parsed;
      await audio.play();
      const context = new AudioContext();
      const heard = await window.meter.listen(context.createMediaElementSource(audio), ms);
      const behind = hls.latency;
      hls.destroy();
      await context.close();
      return { ...heard, behindLive: behind };
    },
    { url, behindLive, slack: DELAY_SLACK_SECONDS, ms: LISTEN_MS },
  );
}

/** Runs in the page: window.meter, a frequency analyser. Self-contained,
 * because only its source text reaches the page. */
function installMeter(): void {
  const FFT_SIZE = 8192; // about 6 Hz per bin at 48 kHz
  const POLL_MS = 100;
  window.meter = {
    async listen(source, ms) {
      const context = source.context as AudioContext;
      const analyser = context.createAnalyser();
      analyser.fftSize = FFT_SIZE;
      // An analyser only runs while something pulls on it: a silent path to
      // the speakers does.
      const silence = context.createGain();
      silence.gain.value = 0;
      source.connect(analyser).connect(silence).connect(context.destination);
      const bins = new Float32Array(analyser.frequencyBinCount);
      let loudest = { frequency: 0, level: -Infinity };
      for (let elapsed = 0; elapsed < ms; elapsed += POLL_MS) {
        await new Promise((resolve) => setTimeout(resolve, POLL_MS));
        analyser.getFloatFrequencyData(bins);
        bins.forEach((level, bin) => {
          if (level > loudest.level) {
            loudest = { frequency: (bin * context.sampleRate) / FFT_SIZE, level };
          }
        });
      }
      return loudest;
    },
  };
}
