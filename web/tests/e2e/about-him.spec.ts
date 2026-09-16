import { expect, test, type Page } from "@playwright/test";
import { openMe, signInThroughTheApp, todayReady } from "./helpers";
import { seedHome } from "./homeSeed";

/** A line that speaks to him about his own papers ("your tablets", "You have 5 left", "I am not
 *  feeling well"). "For you today" and "See more for you" speak to her, and are hers. */
const TO_HIM = /\b(your|yours|you have|you took|you see|you saw|you told|you kept|you wrote|you can|you are|when you|I am)\b/i;

/** Lines that speak to whoever is reading about their own doing, not about his record: the box
 *  where she writes her own message to the family is hers to fill, and says so, on his screens
 *  and on hers alike. These are the reader's, so the sweep lets them by. */
const HERS = [/^Your message to the family$/];

const aboutHim = (line: string): boolean => TO_HIM.test(line) && !HERS.some((hers) => hers.test(line));

async function linesOn(page: Page): Promise<string[]> {
  const text = await page.getByTestId("shell-scroll").innerText();
  return text.split("\n").map((line) => line.trim()).filter(Boolean);
}

/** D1: her screens say his papers about him by name — the backend's twins and the catalogue's —
 *  never to him; the pill is "Pa is not feeling well", the same button flow. */
test("her Home, her Medicines and her Papers say his papers about him by name, never to him", async ({ page, request }) => {
  const family = await seedHome(request);
  await signInThroughTheApp(page, family.meiPhone, "Mei");
  await page.getByTestId("door-key").click();
  await todayReady(page);
  await expect(page.locator("html")).toHaveAttribute("data-density", "caregiver");
  await expect(page.getByTestId("not-well")).toHaveText(/Pa is not feeling well/);
  await expect(page.getByTestId("home-hero")).toBeVisible();
  const home = await linesOn(page);
  expect(home.filter((line) => TO_HIM.test(line))).toEqual([]);

  for (const tab of ["tab-medicines", "tab-timeline"]) {
    await page.getByTestId(tab).click();
    await expect(page.getByTestId(tab)).toHaveAttribute("aria-current", "page");
    await page.waitForLoadState("networkidle");
    const lines = await linesOn(page);
    expect(lines.length, tab).toBeGreaterThan(0);
    expect(lines.filter(aboutHim), tab).toEqual([]);
  }
});

/** D1, stage 2: the sweep. Every screen a chief can reach in the caregiver density — each tab,
 *  each place in his Record, each part of Family, the feed, a card, the emergency card and the
 *  symptom log — says his papers about him by name. Not one of them says "your" or "you" of his
 *  record, and not one puts words in his mouth ("I am not feeling well"). The screens that are
 *  hers to act on ("For you today", "See more for you") speak to her and are hers: TO_HIM is
 *  written to catch the second person about his record, not every "you" on the phone. */
test("no caregiver-density screen says a second-person line about his record", async ({ page, request }) => {
  test.setTimeout(600_000);
  const family = await seedHome(request);
  await signInThroughTheApp(page, family.meiPhone, "Mei");
  await page.getByTestId("door-key").click();
  await todayReady(page);
  await expect(page.locator("html")).toHaveAttribute("data-density", "caregiver");

  const seen: string[] = [];
  const check = async (where: string) => {
    // Wait for what the screen drew, not for the network to fall idle: a screen that keeps a
    // request open (the family thread polls) never goes idle, and this reads as soon as there
    // are lines to read.
    await expect(page.getByTestId("shell-scroll")).toBeVisible();
    await expect.poll(async () => (await linesOn(page)).length, { timeout: 10_000, intervals: [100, 200, 300, 500, 1_000] }).toBeGreaterThan(0);
    const lines = await linesOn(page);
    seen.push(`${where} (${lines.length})`);
    expect.soft(lines.length, `${where} drew nothing`).toBeGreaterThan(0);
    expect.soft(lines.filter(aboutHim), where).toEqual([]);
  };

  const tab = async (id: string) => {
    await page.getByTestId(id).click();
    await expect(page.getByTestId(id)).toHaveAttribute("aria-current", "page");
  };

  for (const id of ["tab-today", "tab-timeline", "tab-medicines", "tab-plan", "tab-family"]) {
    await tab(id);
    await check(id);
  }

  // Every place in his Record her key opens. In her density they are the chips under the title
  // (`record-places`), so each is one tap from whichever Record screen is open.
  await tab("tab-timeline");
  for (const entry of ["medicines", "papers", "routine", "timeline", "trends", "providers", "changes"]) {
    const chip = page.getByTestId(`place-${entry}`);
    if (!(await chip.isVisible().catch(() => false))) continue;
    await chip.click();
    await check(`record-${entry}`);
  }

  // Every part of Family her key opens.
  await tab("tab-family");
  const parts = ["trail", "keys", "roster", "thread", "messages", "metrics", "calendar", "deliveries", "settings", "documents", "consents", "onlyMe"];
  for (const part of parts) {
    await tab("tab-family");
    const pill = page.getByTestId(`open-${part}`);
    if (!(await pill.isVisible().catch(() => false))) continue;
    await pill.click();
    await check(`family-${part}`);
  }

  // The feed, one of its cards, the emergency card and the symptom log.
  await tab("tab-today");
  await page.getByTestId("open-feed").click();
  await check("feed");
  await page.goto("./");
  await todayReady(page);
  await openMe(page);
  await page.getByTestId("me-emergency").click();
  await expect(page.getByTestId("emergency-screen")).toBeVisible();
  await check("emergency");
  await page.goto("./");
  await todayReady(page);
  await page.getByTestId("open-symptoms").click();
  await check("symptoms");

  // The pill is about him, and it is the same button: it opens what it says it opens.
  await page.goto("./");
  await todayReady(page);
  await expect(page.getByTestId("not-well")).toHaveText(/Pa is not feeling well/);
  await page.getByTestId("not-well").click();
  await check("not-well");
  expect(seen.length).toBeGreaterThan(20);
});
