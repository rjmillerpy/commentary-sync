/** How far this device's clock is from the server's.
 *
 * Sync compares audio recorded on two devices, so each stamps its audio in
 * server time (GET /clock). A round trip is timed with the device's own
 * clock; the server read its clock somewhere in between, assumed halfway.
 * The fastest of a few round trips is kept: the less time a request spent
 * in flight, the less that guess can be off by.
 *
 *   const offset = await measureClockOffset(api.serverTime, () => Date.now() / 1000);
 *   const serverNow = Date.now() / 1000 + offset;
 */

export const CLOCK_SAMPLES = 3;

interface Sample {
  offset: number;
  roundTrip: number;
}

/** Seconds to add to the device's clock to get the server's. */
export async function measureClockOffset(
  serverTime: () => Promise<number>,
  deviceTime: () => number,
  samples: number = CLOCK_SAMPLES,
): Promise<number> {
  const measured: Sample[] = [];
  for (let round = 0; round < samples; round += 1) {
    const sent = deviceTime();
    const server = await serverTime();
    const received = deviceTime();
    measured.push({ offset: server - (sent + received) / 2, roundTrip: received - sent });
  }
  const fastest = measured.reduce((best, sample) => (sample.roundTrip < best.roundTrip ? sample : best));
  return fastest.offset;
}
