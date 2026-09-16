import { expect, test } from "@playwright/test";
import { BASE_URL } from "../../playwright.config";
import { fixClock, keptKeys, seedOwner, signInThroughTheApp, throttleCpu, waitForWorker } from "./helpers";

/** E00-08's budget: "cold start under 3 s on a reference low-end device; card readable with no
 *  data", at 360 px. The reference is Lighthouse's mid-tier phone — a processor 4 times slower
 *  than the runner's — on a 360 by 640 screen. The home-screen app starts from the worker's
 *  copy of the shell and the phone's copy of the page, so it is timed from the reload to his
 *  list on screen, and to the emergency card after one tap; first with no network at all, then
 *  on a slow mobile network. Each time is written on the report. */

test.use({ viewport: { width: 360, height: 640 } });

test.beforeEach(async ({ page }) => {
  await fixClock(page);
});

test("cold start on a slow phone at 360 by 640: his list and the emergency card in under 3 seconds, with no network and on a slow one", async ({ page, context, request }) => {
  test.skip(BASE_URL.includes(":5173"), "needs the built app the backend serves (the worker is not built in dev)");
  const pa = await seedOwner(request);
  await signInThroughTheApp(page, pa.phone, "Pa");
  await expect(page.getByTestId("proud")).toBeVisible();
  await expect.poll(async () => (await keptKeys(page)).some((key) => key.startsWith("emergency."))).toBe(true);
  await waitForWorker(page);

  const slow = await throttleCpu(page, 4);
  const timings: { network: string; list: number; card: number }[] = [];
  const coldStart = async (network: string) => {
    const started = Date.now();
    await page.reload();
    await expect(page.getByTestId("today-list").or(page.getByTestId("now-card"))).toBeVisible({ timeout: 15_000 });
    const list = Date.now() - started;
    await page.getByTestId("open-emergency").click();
    await expect(page.getByTestId("emergency-card")).toBeVisible({ timeout: 15_000 });
    timings.push({ network, list, card: Date.now() - started });
  };

  await context.setOffline(true);
  for (let run = 0; run < 3; run++) await coldStart("none");
  await context.setOffline(false);

  // A slow mobile network: 150 ms each way, 1.6 Mbit/s down, 750 kbit/s up.
  const cdp = await context.newCDPSession(page);
  await cdp.send("Network.emulateNetworkConditions", { offline: false, latency: 150, downloadThroughput: (1.6 * 1024 * 1024) / 8, uploadThroughput: (750 * 1024) / 8 });
  for (let run = 0; run < 3; run++) await coldStart("slow mobile");
  await cdp.send("Network.emulateNetworkConditions", { offline: false, latency: 0, downloadThroughput: -1, uploadThroughput: -1 });
  await cdp.detach();
  await slow();

  test.info().annotations.push({ type: "cold start, ms (a processor 4 times slower, 360 by 640)", description: JSON.stringify(timings) });
  console.log("cold start (ms):", JSON.stringify(timings));
  for (const each of timings) {
    expect(each.list, `${each.network}: his list`).toBeLessThan(3000);
    expect(each.card, `${each.network}: the emergency card`).toBeLessThan(3000);
  }
});
