import { expect, test } from "@playwright/test";
import { BASE_URL } from "../../playwright.config";
import { API, apiToken, expireKeptPages, fixClock, freshPhone, medicinesInIndexedDb, seedMedicine, shot, signInThroughTheApp } from "./helpers";

test.beforeEach(async ({ page }) => {
  await fixClock(page);
});

/** With the network gone, the app opens on the page the phone kept: the service worker serves
 *  the shell, IndexedDB holds today's page under the key that read it, and the page says when
 *  it was read. It is today's list, not a Now card — a kept page cannot know what is due — and
 *  there is no Taken and no spinner. Past the local midnight the kept page is deleted and only
 *  the emergency card and one line show: no dose from old data. */
test("offline: the kept page as a dated list with no Taken; past midnight only the emergency card", async ({ page, context, request }) => {
  test.skip(BASE_URL.includes(":5173"), "needs the built app the backend serves (the worker is not built in dev)");
  const phone = freshPhone();
  const token = await apiToken(request, phone);
  const words = (await (await request.get(`${API}/consent/wording?language=en`)).json()) as { version: string };
  const opened = await request.post(`${API}/profiles/mine`, {
    headers: { Authorization: `Bearer ${token}` },
    data: { consent: { wording_version: words.version, language: "en", captured_via: "app" }, display_name: "Pa", language: "en" },
  });
  const profileId = ((await opened.json()) as { profile_id: string }).profile_id;
  await seedMedicine(request, token, profileId, { generic: "amlodipine", strength: "5 mg", dose_text: "1 tab QDS", quantity: 120 });

  await signInThroughTheApp(page, phone, "Pa");
  await expect(page.getByTestId("proud")).toBeVisible();
  await expect.poll(async () => (await medicinesInIndexedDb(page)).length).toBeGreaterThan(0);
  await page.evaluate(async () => {
    await navigator.serviceWorker.ready;
    if (!navigator.serviceWorker.controller) {
      await new Promise<void>((done) => navigator.serviceWorker.addEventListener("controllerchange", () => done(), { once: true }));
    }
  });

  await context.setOffline(true);
  await page.reload();
  const offline = page.getByTestId("offline");
  await expect(offline).toContainText("Nura cannot reach the internet right now.");
  await expect(offline).toContainText("This is your Today page from earlier.");
  await expect(offline).toContainText(/Nura last read your papers on [A-Z][a-z]+day \d{1,2} [A-Z][a-z]+ at \d{1,2}:\d{2}\s?[ap]m\./);
  const list = page.getByTestId("today-list");
  await expect(list).toContainText("Your tablets for today");
  await expect(list).toContainText("Take 1 tablet of your blood pressure tablet with breakfast.");
  await expect(list).toContainText("This comes from your Today page.");
  await expect(page.getByTestId("now-card")).toHaveCount(0);
  await expect(page.getByTestId("missed-card")).toHaveCount(0);
  await expect(page.getByTestId("taken")).toHaveCount(0);
  // Both clocks stand at 10:00 (the backend's is frozen for the run), so the kept page carries
  // the feed's cards for today, and they stand in "For you today" in place of the State card.
  await expect(page.getByTestId("feed-card").first()).toContainText("Your tablets today");
  await expect(page.getByTestId("state-card")).toHaveCount(0);
  await expect(page.getByTestId("proud-number")).toBeVisible();
  expect(await page.locator("[role=progressbar], .spinner").count()).toBe(0);
  await shot(page, "offline-kept");

  // The next morning, still offline: the kept page is past its midnight.
  expect(await expireKeptPages(page)).toBe(1);
  await page.reload();
  await expect(page.getByTestId("cannot-reach")).toContainText("Nura cannot reach your papers right now.");
  await expect(page.getByTestId("emergency-placeholder")).toContainText("Emergency card");
  for (const gone of ["today-list", "now-card", "taken", "state-card", "medicines-card", "proud", "offline", "reading-prompt"]) {
    await expect(page.getByTestId(gone)).toHaveCount(0);
  }
  expect(await medicinesInIndexedDb(page)).toEqual([]);
  expect(await page.locator("[role=progressbar], .spinner").count()).toBe(0);
  await shot(page, "offline-expired");
  await context.setOffline(false);
});
