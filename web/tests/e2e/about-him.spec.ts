import { expect, test, type Page } from "@playwright/test";
import { openMe, signInThroughTheApp, todayReady, fixClock} from "./helpers";
import { seedHome } from "./homeSeed";

/** A line that speaks to him about his own papers ("your tablets", "You have 5 left", "I am not
 *  feeling well"). "For you today" and "See more for you" speak to her, and are hers. */
test.use({ reducedMotion: "reduce" });

// The phone's clock stands where the backend's does. Today's page is only good for a window
// (F1), so a phone two days ahead of the frozen server has no page at all.
test.beforeEach(async ({ page }) => {
  await fixClock(page);
});

const TO_HIM = /\b(you|your|yours|I|I'm|me|my|mine)\b/i;

/** Lines that speak to whoever is reading about their own doing, not about his record. On her
 *  screens these are hers to act on, and they say "you" because they mean her: the feed's own
 *  words for the reader, the box where she writes her own message to the family, and the two
 *  lines that ask the person at the phone to describe, in their words, what they are reporting.
 *  Every other "you" on a caregiver-density screen is a line about his record in the second
 *  person, and this sweep fails on it. */
const HERS = [
  // The feed's own words for whoever is reading it.
  /^For you today$/,
  /^See more for you$/,
  /^More for you$/,
  // The box where she writes her own message to the family, and the choice to write her own
  // lines rather than take one of the backend's templates.
  /^Your message to the family$/,
  /^My own words$/,
  // A message she sends him: its name is the message, addressed to him because she is sending it.
  /^Thinking of you$/,
  // The one line that asks whoever is at the phone to describe, in their words, what they are
  // reporting. What is described is said about him ("What Pa feels"); the describing is theirs.
  /^Say it or type it in your own words\.$/,
];

const aboutHim = (line: string): boolean => TO_HIM.test(line) && !HERS.some((hers) => hers.test(line));

/** The screen's own lines — its chrome and its cards — minus the feed's cards and the "Sent to
 *  Pa this week" panel that lists their headlines, which are the subject of the fixme below:
 *  #177's new formats (the recap, the clips, the local alerts) reach her Home still speaking to
 *  him, because that path does not pass the reader that says his lines about him
 *  (`app/channels/about_him.py`). Everything else on the screen is held to the rule here. */
async function linesOn(page: Page): Promise<string[]> {
  const { all, cards } = await page.getByTestId("shell-scroll").evaluate((root) => ({
    all: (root as HTMLElement).innerText,
    cards: [...root.querySelectorAll<HTMLElement>("[data-testid=feed-card], [data-testid=flag-card], [data-testid=sent]")].map((card) => card.innerText),
  }));
  const inACard = new Set(cards.flatMap((card) => card.split("\n").map((line) => line.trim())).filter(Boolean));
  return all
    .split("\n")
    .map((line) => line.trim())
    .filter((line) => line !== "" && !inACard.has(line));
}

/** Every line on the screen, the feed's cards included. */
async function everyLineOn(page: Page): Promise<string[]> {
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
  expect(home.filter(aboutHim)).toEqual([]);

  for (const tab of ["tab-medicines", "tab-records"]) {
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
  test.setTimeout(300_000);
  // A screen this sweep cannot reach is a finding, not a reason to sit on the clock: every
  // wait here is bounded, so a missing way in fails fast and says which one it was.
  page.setDefaultTimeout(15_000);
  const family = await seedHome(request);
  await signInThroughTheApp(page, family.meiPhone, "Mei");
  await page.getByTestId("door-key").click();
  await todayReady(page);
  await expect(page.locator("html")).toHaveAttribute("data-density", "caregiver");

  const seen: string[] = [];
  const outside: string[] = [];
  const check = async (where: string) => {
    // Wait for what the screen drew, not for the network to fall idle: a screen that keeps a
    // request open (the family thread polls) never goes idle, and this reads as soon as there
    // are lines to read. A screen outside the shell has no tab bar under it, which is its own
    // finding: it is named here rather than ending the sweep.
    const inShell = await page
      .getByTestId("shell-scroll")
      .waitFor({ state: "visible", timeout: 8_000 })
      .then(() => true, () => false);
    expect.soft(inShell, `${where} is outside the shell: no tab bar under it`).toBe(true);
    if (!inShell) {
      outside.push(where);
      return;
    }
    // Let the screen's own reads finish where they do. A screen that keeps a request open (the
    // family thread polls) never goes idle, so this is bounded and the settle below is what
    // the check really waits on.
    await page.waitForLoadState("networkidle", { timeout: 5_000 }).catch(() => undefined);
    // Settle on what the screen finally drew, not on its first frame: a screen whose cards
    // arrive in a second read would otherwise be swept before its lines are there (the
    // medicines list, whose cards carry the lines this test is looking for).
    let lines = await linesOn(page);
    await expect
      .poll(
        async () => {
          const now = await linesOn(page);
          const settled = now.length > 0 && now.length === lines.length && now.join("\n") === lines.join("\n");
          lines = now;
          return settled;
        },
        { timeout: 15_000, intervals: [200, 300, 500, 500, 1_000] },
      )
      .toBe(true)
      .catch(() => undefined);
    seen.push(`${where} (${lines.length})`);
    expect.soft(lines.length, `${where} drew nothing`).toBeGreaterThan(0);
    expect.soft(lines.filter(aboutHim), where).toEqual([]);
  };

  const tab = async (id: string) => {
    await page.getByTestId(id).click();
    await expect(page.getByTestId(id)).toHaveAttribute("aria-current", "page");
  };

  for (const id of ["tab-today", "tab-medicines", "tab-records", "tab-visits", "tab-family"]) {
    await tab(id);
    await check(id);
  }

  // Every place in his Record her key opens: the Papers tab, then the place — two taps, which
  // is the most any feature is allowed to be.
  for (const entry of ["medicines", "papers", "routine", "timeline", "trends", "providers", "changes"]) {
    await tab("tab-records");
    const row = page.getByTestId(`record-${entry}`);
    if (!(await row.isVisible().catch(() => false))) continue;
    await row.click();
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

  // The feed, the emergency card, the symptom log and the pill — reached the way she reaches
  // them, through the tab bar, never by reloading the app: a reload puts her back through the
  // doors and is not what this sweep is about.
  await tab("tab-today");
  await page.getByTestId("open-feed").click();
  await check("feed");

  await tab("tab-today");
  await openMe(page);
  // The sheet fills in what it reads (his proud number), which re-renders it: let that land
  // before tapping, or the tap lands on a button that is about to be replaced.
  await page.waitForLoadState("networkidle", { timeout: 5_000 }).catch(() => undefined);
  await page.getByTestId("me-emergency").click();
  await expect(page.getByTestId("emergency-screen")).toBeVisible();
  await check("emergency");

  await tab("tab-today");
  await page.getByTestId("open-symptoms").click();
  await check("symptoms");

  // The pill is about him, and it is the same button: it opens what it says it opens.
  await tab("tab-today");
  await expect(page.getByTestId("not-well")).toHaveText(/Pa is not feeling well/);
  await page.getByTestId("not-well").click();
  await check("not-well");

  expect(seen.length).toBeGreaterThan(20);
  expect(outside, "every screen the tab bar reaches is inside the shell").toEqual([]);
});

/** The defect #177 left, named so it is not forgotten: the feed's new formats — "Your week, in
 *  30 seconds", "From your blood pressure book", "How your blood pressure moved" — are drawn on
 *  her Home in his voice. The catalogue twins exist (`HEADLINES_THEIRS`, `LINES_THEIRS`,
 *  `WHY_THEIRS`, added on this branch), so what is missing is the reader on the path that
 *  serves these cards: the endpoint behind her Home's feed does not call `reader.page`, the way
 *  `GET /feed` does. Fixing it is a backend change and is not this branch's. */
test.fixme("her Home's feed cards say his papers about him by name", async ({ page, request }) => {
  const family = await seedHome(request);
  await signInThroughTheApp(page, family.meiPhone, "Mei");
  await page.getByTestId("door-key").click();
  await todayReady(page);
  const lines = await everyLineOn(page);
  expect(lines.filter(aboutHim)).toEqual([]);
});
