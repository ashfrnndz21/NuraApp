import { expect, test, type Page } from "@playwright/test";
import { API, captureSpeech, fixClock, freshPhone, paperPdf, paperPhoto, seedOwner, signInThroughTheApp, throttleCpu, todayReady} from "./helpers";

/** E18-01 on the web (ADR 0001: the photo library cannot be scanned from a browser, so the
 *  substitute is the phone's own picker, many at once): a grid he confirms, nothing sent before
 *  his one yes, a review card for each paper through E02's capture routes, a page that is not a
 *  health paper said so in the backend's words, and no photo left on the phone. */

test.beforeEach(async ({ page }) => {
  await fixClock(page);
});

const auth = (token: string) => ({ headers: { Authorization: `Bearer ${token}` } });

/** Every capture POST the phone makes: `photos` or `imports`, streamed or not (the trace,
 *  docs/design-direction.md) — the same two backend routes either way. */
function captures(page: Page): string[] {
  const seen: string[] = [];
  page.on("request", (sent) => {
    const found = new URL(sent.url()).pathname.match(/\/(photos|imports)(?:\/stream)?$/);
    if (sent.method() === "POST" && found) seen.push(found[1]!);
  });
  return seen;
}

/** What the phone holds of any photo: object URLs on screen, the worker's caches, web storage,
 *  and anything in IndexedDB that looks like a paper's bytes. */
async function photosOnThePhone(page: Page) {
  return page.evaluate(async () => {
    const cached: string[] = [];
    for (const name of await caches.keys()) for (const each of await (await caches.open(name)).keys()) cached.push(each.url);
    const values = await new Promise<string[]>((resolve) => {
      const opened = indexedDB.open("nura", 1);
      opened.onsuccess = () => {
        const all = opened.result.transaction("kv", "readonly").objectStore("kv").getAll();
        all.onsuccess = () => resolve(all.result.map((value: unknown) => JSON.stringify(value)));
      };
      opened.onerror = () => resolve([]);
    });
    return {
      blobs: document.querySelectorAll('img[src^="blob:"]').length,
      cached: cached.filter((url) => !new URL(url).pathname.startsWith("/app/")),
      local: localStorage.length,
      session: sessionStorage.length,
      paperBytes: values.filter((value) => /nura-paper-placeholder|iVBORw0KGgo|JVBERi0/.test(value)).length,
    };
  });
}

async function openPapers(page: Page, phone: string): Promise<void> {
  await signInThroughTheApp(page, phone, "Pa");
  await todayReady(page);
  await page.getByTestId("open-me").click();
  await page.getByTestId("open-papers").click();
  await expect(page.getByTestId("papers-lead")).toContainText("Nura sends nothing until you tap Send.");
}

test("papers from his photos: many at once, a grid he confirms, nothing sent before his yes, a review card each, a page that is not a health paper said so, no photo left on the phone", async ({ page, request }) => {
  const pa = await seedOwner(request, "Pa", []);
  const sent = captures(page);
  await openPapers(page, pa.phone);
  await expect(page.getByTestId("photos-input")).toHaveAttribute("multiple", "");
  await expect(page.getByTestId("photos-input")).toHaveAttribute("accept", "image/*,application/pdf");
  await page.getByTestId("photos-input").setInputFiles([
    paperPhoto("lipid-panel-2023-09-07"),
    paperPhoto("receipt-2026-09-01"),
    paperPdf("discharge-letter-2026-08-20"),
    paperPhoto("clinic-slip-2026-09-10"),
  ]);

  // The grid: every one in to begin with; a tap leaves one out, in words, not colour alone.
  const tiles = page.getByTestId("paper-tile");
  await expect(tiles).toHaveCount(4);
  for (let at = 0; at < 4; at++) await expect(tiles.nth(at)).toHaveAttribute("aria-pressed", "true");
  await expect(tiles.nth(0)).toContainText("Paper 1");
  await expect(tiles.nth(0)).toContainText("Nura will send this one.");
  await expect(page.getByTestId("send-papers")).toHaveText("Send 4 papers");
  await tiles.nth(3).click();
  await expect(tiles.nth(3)).toHaveAttribute("aria-pressed", "false");
  await expect(tiles.nth(3)).toContainText("Nura will not send this one.");
  await expect(page.getByTestId("send-papers")).toHaveText("Send 3 papers");
  expect(sent).toEqual([]); // nothing goes before his yes

  // His one yes: each chosen paper through E02's capture route, one at a time, in order.
  await page.getByTestId("send-papers").click();
  await expect(page.getByTestId("nothing-kept")).toHaveText("Nura kept no photo on this phone.");
  expect(sent).toEqual(["photos", "photos", "imports"]); // the one left out never went
  const results = page.getByTestId("paper-result");
  await expect(results).toHaveCount(3);
  await expect(results.nth(0)).toHaveAttribute("data-outcome", "card");
  await expect(results.nth(0)).toContainText("This is a blood test.");
  await expect(results.nth(1)).toHaveAttribute("data-outcome", "notHealth");
  await expect(results.nth(1).getByTestId("paper-not-health")).not.toBeEmpty();
  await expect(results.nth(2)).toHaveAttribute("data-outcome", "card");
  await expect(results.nth(2)).toContainText("This is a hospital letter.");

  // One card checked: its lines, one yes, the facts written.
  await results.nth(0).getByTestId("check-paper").click();
  await expect(page.getByTestId("review-card")).toContainText("This is a blood test.");
  await page.getByTestId("looks-right").click();
  await expect(page.getByTestId("paper-result").nth(0).getByTestId("paper-checked")).toHaveText("Nura wrote it down.");
  const facts = (await (await request.get(`${API}/profiles/${pa.profileId}/facts?subject=lipid_panel`, auth(pa.token))).json()) as unknown[];
  expect(facts.length).toBeGreaterThan(0);

  // Nothing of any photo stays on the phone.
  expect(await photosOnThePhone(page)).toEqual({ blobs: 0, cached: [], local: 0, session: 0, paperBytes: 0 });
  await page.getByTestId("papers-finish").click();
  await todayReady(page);
  expect(await photosOnThePhone(page)).toEqual({ blobs: 0, cached: [], local: 0, session: 0, paperBytes: 0 });
});

test("a photo too large for Nura: the backend's own sentence on that paper, and the rest of the batch still goes", async ({ page, request }) => {
  const pa = await seedOwner(request, "Pa", []);
  const sent = captures(page);
  await openPapers(page, pa.phone);
  // Past the photo route's cap of 10 MB: the layer in front of the app refuses it at once (#135).
  const huge = { name: "IMG_huge.png", mimeType: "image/png", buffer: Buffer.concat([Buffer.from([0x89, 0x50, 0x4e, 0x47, 0x0d, 0x0a, 0x1a, 0x0a]), Buffer.alloc(11 * 1024 * 1024, 7)]) };
  await page.getByTestId("photos-input").setInputFiles([paperPhoto("lipid-panel-2023-09-07"), huge, paperPhoto("receipt-2026-09-01")]);
  await expect(page.getByTestId("send-papers")).toHaveText("Send 3 papers");
  await page.getByTestId("send-papers").click();
  await expect(page.getByTestId("nothing-kept")).toBeVisible({ timeout: 30_000 });
  const results = page.getByTestId("paper-result");
  await expect(results).toHaveCount(3);
  await expect(results.nth(0)).toHaveAttribute("data-outcome", "card");
  await expect(results.nth(1)).toHaveAttribute("data-outcome", "refused");
  await expect(results.nth(1).getByRole("alert")).toHaveText("That photo is too big for Nura.");
  await expect(results.nth(2)).toHaveAttribute("data-outcome", "notHealth");
  expect(sent).toEqual(["photos", "photos", "photos"]);
});

/** A real one-by-one PNG: the grid decodes what is on screen. */
const DOT = Buffer.from("iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg==", "base64");

test("two years of photos: 240 picked at once are a grid in well under a minute on a slow phone, and nothing is sent", async ({ page, request }) => {
  const pa = await seedOwner(request, "Pa", []);
  const sent = captures(page);
  await openPapers(page, pa.phone);
  const slow = await throttleCpu(page, 4);
  const files = Array.from({ length: 240 }, (_, n) => ({ name: `IMG_${String(n).padStart(4, "0")}.png`, mimeType: "image/png", buffer: DOT }));
  const started = Date.now();
  await page.getByTestId("photos-input").setInputFiles(files);
  await expect(page.getByTestId("paper-tile")).toHaveCount(240, { timeout: 60_000 });
  await expect(page.getByTestId("send-papers")).toHaveText("Send 240 papers");
  const took = Date.now() - started;
  await slow();
  test.info().annotations.push({ type: "240 photos to a grid, ms (a processor 4 times slower)", description: String(took) });
  console.log("240 photos to a grid (ms):", took);
  expect(took).toBeLessThan(60_000);
  expect(sent).toEqual([]);
});

test("in the sitting: many photos at once, and each paper he checks joins the sitting", async ({ page, request }) => {
  const phone = freshPhone("+659777");
  await captureSpeech(page);
  await signInThroughTheApp(page, phone, "Pa");
  await page.getByTestId("door-for-me").click();
  await page.getByTestId("agree").click();
  await page.getByLabel("The name Nura uses").fill("Pa");
  await page.getByTestId("about-next").click();
  await page.getByTestId("about-lang-en").click();
  await page.getByTestId("decade-1950").click();
  await page.getByLabel("The doctor's name").fill("Dr Tan");
  await page.getByTestId("about-next").click();
  await page.getByTestId("breakfast-07:30").click();
  for (const item of ["large_text", "high_contrast", "voice_on", "big_targets", "one_thing_per_screen", "read_back", "repeat_prompts"]) await page.getByTestId(`${item}-no`).click();
  await page.getByTestId("density-simple").click();
  await page.getByTestId("cloud-done").click();
  await expect(page.locator("main.onboarding")).toHaveAttribute("data-stage", "records");

  const sent = captures(page);
  await page.getByTestId("choose-many").click();
  await expect(page.locator("main.onboarding")).toHaveAttribute("data-stage", "batch");
  await page.getByTestId("photos-input").setInputFiles([paperPhoto("lipid-panel-2023-09-07"), paperPhoto("receipt-2026-09-01")]);
  await expect(page.getByTestId("send-papers")).toHaveText("Send 2 papers");
  expect(sent).toEqual([]);
  await page.getByTestId("send-papers").click();
  await expect(page.getByTestId("nothing-kept")).toBeVisible();
  await page.getByTestId("paper-result").nth(0).getByTestId("check-paper").click();
  await page.getByTestId("looks-right").click();
  await expect(page.locator("main.onboarding")).toHaveAttribute("data-stage", "batch");
  await expect(page.getByTestId("paper-result").nth(0).getByTestId("paper-checked")).toHaveText("Nura wrote it down.");
  await page.getByTestId("batch-done").click();
  await expect(page.locator("main.onboarding")).toHaveAttribute("data-stage", "records");

  const token = (await import("./helpers")).apiToken;
  const bearer = await token(request, phone);
  const me = (await (await request.get(`${API}/me`, auth(bearer))).json()) as { profile_id: string };
  const bio = (await (await request.get(`${API}/profiles/${me.profile_id}/biography?language=en`, auth(bearer))).json()) as { papers: unknown[] };
  expect(bio.papers).toHaveLength(1);
});
