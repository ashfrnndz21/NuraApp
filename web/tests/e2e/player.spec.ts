import { expect, test, type APIRequestContext, type Page } from "@playwright/test";
import { API, captureSpeech, cutKey, fakeRecorder, fixClock, seedOwner, seedVisitDay, signInThroughTheApp, speechRates, stand, openMe, proudCard, todayReady} from "./helpers";

/** E15-07, the one player: a card's voice on tap and never by itself; a big Play / Pause; his
 *  speed, remembered on the phone; the line being said under it, in his body size; a visit's clip
 *  only its stretch; and a recording this key may not hear refused in the backend's words, with
 *  no player. Both clocks at 10 in the morning in Singapore on Monday 14 September. */

test.beforeEach(async ({ page }) => {
  await fixClock(page);
  await captureSpeech(page);
});

const auth = (token: string) => ({ headers: { Authorization: `Bearer ${token}` } });
const spoken = (page: Page) => page.evaluate(() => (window as unknown as { __spoken: string[] }).__spoken);
const cancels = (page: Page) => page.evaluate(() => (window as unknown as { __cancels: number }).__cancels);

test("Hear opens the one player: nothing before the tap, Play and Pause, his speed kept on the phone, the line being said in his body size", async ({ page, request }) => {
  const pa = await seedOwner(request);
  await signInThroughTheApp(page, pa.phone, "Pa");
  await todayReady(page);
  // The proud number, and its Hear, are on the Me sheet (D1).
  await openMe(page);
  const proud = proudCard(page);
  await expect(proud).toBeVisible();
  await expect(page.getByTestId("player")).toHaveCount(0);
  expect(await spoken(page)).toEqual([]);

  await proud.getByTestId("hear").click();
  const player = proud.getByTestId("player");
  await expect(player).toBeVisible();
  await expect(page.getByTestId("player")).toHaveCount(1);
  const toggle = player.getByTestId("player-toggle");
  await expect(toggle).toHaveText("Pause");
  expect(await spoken(page)).toEqual(["When you tap Taken, this number becomes 1.", "This number only goes up."]);
  await expect(player.getByTestId("player-line")).toHaveText("When you tap Taken, this number becomes 1.");
  // The transcript in his body size (the patient density's 20px); Play / Pause half as tall
  // again as his 56px target.
  expect(await player.getByTestId("player-line").evaluate((el) => getComputedStyle(el).fontSize)).toBe("20px");
  expect((await toggle.boundingBox())!.height).toBeGreaterThanOrEqual(84);

  await toggle.click();
  await expect(toggle).toHaveText("Play");
  await expect(player).toHaveAttribute("data-status", "paused");
  await toggle.click();
  await expect(toggle).toHaveText("Pause");
  await expect(player).toHaveAttribute("data-status", "playing");

  // His speed: three plain choices; the voice takes it at once; the phone keeps it.
  await expect(player.getByTestId("speed-1")).toHaveAttribute("aria-pressed", "true");
  await player.getByTestId("speed-0.75").click();
  await expect(player.getByTestId("speed-0.75")).toHaveAttribute("aria-pressed", "true");
  await expect(player.getByTestId("speed-1")).toHaveAttribute("aria-pressed", "false");
  expect((await speechRates(page)).at(-1)).toBeCloseTo(0.9 * 0.75);
  // The phone has kept it (IndexedDB, `device.speed`) before the app is opened again.
  const keptSpeed = () =>
    page.evaluate(
      () =>
        new Promise<unknown>((resolve) => {
          const opened = indexedDB.open("nura", 1);
          opened.onsuccess = () => {
            const read = opened.result.transaction("kv", "readonly").objectStore("kv").get("device.speed");
            read.onsuccess = () => resolve(read.result);
          };
          opened.onerror = () => resolve(null);
        }),
    );
  await expect.poll(keptSpeed).toBe(0.75);
  await page.reload();
  await expect(proud).toBeVisible();
  expect(await spoken(page)).toEqual([]); // reopening plays nothing
  await proud.getByTestId("hear").click();
  await expect(proud.getByTestId("speed-0.75")).toHaveAttribute("aria-pressed", "true");
  expect((await speechRates(page)).at(-1)).toBeCloseTo(0.9 * 0.75);

  // Leaving the screen stops it, and the player goes with it.
  const before = await cancels(page);
  await page.getByRole("button", { name: "Me", exact: true }).click();
  await expect.poll(() => cancels(page)).toBeGreaterThan(before);
  await expect(page.getByTestId("player")).toHaveCount(0);
});

/** Pa's visit to Dr Tan this morning, recorded on the Visit screen with the phone's stand-in
 *  recorder: the post-visit card with a clip under each line the recording has. */
async function recordedVisit(page: Page, request: APIRequestContext) {
  await fakeRecorder(page);
  const pa = await seedVisitDay(request, { recording: true });
  await signInThroughTheApp(page, pa.phone, "Pa");
  await page.getByTestId("open-visit").click();
  await page.getByTestId("start-recording").click();
  await page.getByTestId("doctor-yes").click();
  await page.clock.fastForward("01:06");
  await page.getByTestId("stop-recording").click();
  const summary = page.getByTestId("summary");
  await expect(summary).toContainText("water pill");
  return { pa, summary };
}

test("a clip in the player: only its stretch, its line as the transcript, Pause and Play", async ({ page, request }) => {
  const { summary } = await recordedVisit(page, request);
  const line = summary.getByTestId("summary-line").filter({ hasText: "water pill" });
  expect((await stand(page)).__clips).toEqual([]);
  await line.getByTestId("hear-clip").click();
  await expect.poll(async () => (await stand(page)).__clips.length).toBe(1);
  expect((await stand(page)).__clips[0]).toMatch(/^blob:.*#t=19\.8,28\.9$/);
  const player = line.getByTestId("player");
  await expect(player.getByTestId("player-line")).toHaveText((await line.locator("p").first().textContent()) ?? "");
  await expect(player.getByTestId("player-toggle")).toHaveText("Pause");
  await player.getByTestId("player-toggle").click();
  await expect(player.getByTestId("player-toggle")).toHaveText("Play");
  await expect(page.getByTestId("player")).toHaveCount(1);
});

test("a recording this key may not hear: the backend's refusal said on the line, and no player", async ({ page, request }) => {
  // What the backend answers a key that reads the visits but does not hear the room (a viewer's,
  // checked over the API below), given to the phone for its recording. Set before the recording
  // is sent: the screen fetches it straight after, to play on the first tap.
  const refusal = { refusal: "OnlyTheFamilyHears" };
  await page.route("**/api/profiles/*/artifacts/*/clip**", (route) => route.fulfill({ status: 403, contentType: "application/json", body: JSON.stringify(refusal) }));
  const { pa, summary } = await recordedVisit(page, request);
  const line = summary.getByTestId("summary-line").filter({ hasText: "water pill" });
  await expect(line.getByTestId("clip-refused")).toHaveText("Only the owner and the family he let in can hear this.");
  await expect(summary.getByTestId("hear-clip")).toHaveCount(0);
  await expect(page.getByTestId("player")).toHaveCount(0);
  expect((await stand(page)).__clips).toEqual([]);

  // The backend's own answer to a viewer's key is exactly that refusal.
  const kit = await cutKey(request, pa, { name: "Kit", prefix: "+659559" }, "viewer", ["visits", "readings"]);
  const recordings = (await (await request.get(`${API}/profiles/${pa.profileId}/appointments/${pa.appointmentId}/recordings`, auth(pa.token))).json()) as { artifact_id: string }[];
  const heard = await request.get(`${API}/profiles/${pa.profileId}/artifacts/${recordings[0]!.artifact_id}/clip?start=19.8&end=28.9`, auth(kit.token));
  expect(heard.status()).toBe(403);
  expect(await heard.json()).toEqual(refusal);
  const his = await request.get(`${API}/profiles/${pa.profileId}/artifacts/${recordings[0]!.artifact_id}/clip?start=19.8&end=28.9`, auth(pa.token));
  expect(his.status()).toBe(200);
});
