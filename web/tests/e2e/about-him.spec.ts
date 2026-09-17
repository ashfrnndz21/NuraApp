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

/** The screen's own lines — its chrome and its cards — minus the ordinary feed cards
 *  (`feed-card`, `flag-card`) and `reach-lines`, whose innerText mixes titles, bodies and
 *  provenance in a shape this line-by-line sweep cannot read reliably; those are held to the
 *  rule by the tests that read them directly instead. The feed's "Sent to Pa this week" panel
 *  (`sent`), the family's grant lines (`grant-lines`) and the consent wording (`consent-words`)
 *  used to be excluded here too, while #210 and #214 were open; now that both are fixed, they
 *  are swept like everything else on the screen. */
async function linesOn(page: Page): Promise<string[]> {
  const { all, cards } = await page.getByTestId("shell-scroll").evaluate((root) => ({
    all: (root as HTMLElement).innerText,
    cards: [...root.querySelectorAll<HTMLElement>("[data-testid=feed-card], [data-testid=flag-card], [data-testid=reach-lines]")].map((card) => card.innerText),
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

  // Her Medicines is a place in Health now (the warm tabs): the tab, then the place; and Health
  // itself, the hub of his papers.
  for (const [tab, place] of [["tab-health", "record-medicines"], ["tab-health", null]] as const) {
    await page.getByTestId(tab).click();
    if (place) {
      await page.getByTestId("health-record-hub").click();
      await page.getByTestId(place).click();
    }
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
    // family thread polls) never goes idle, so this is bounded; a Record screen says it is busy
    // while its reads are in flight, and the lines this sweep is about often arrive with them.
    // Without both, a screen can be read before it has said anything and pass by saying nothing
    // (which is how the family's grant lines slipped past locally and were caught in CI).
    await page.waitForLoadState("networkidle", { timeout: 5_000 }).catch(() => undefined);
    await page
      .locator("main[aria-busy=true]")
      .waitFor({ state: "detached", timeout: 8_000 })
      .catch(() => undefined);
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

  // Profile is not in this sweep, as the Me sheet it holds never was: it is the reader's own
  // settings — her sign-in, her language, her look — so its "you" is hers.
  for (const id of ["tab-home", "tab-health", "tab-connect", "tab-services"]) {
    await tab(id);
    await check(id);
  }
  // Her Medicines, a place in Health, as the Medicines tab was.
  await tab("tab-health");
  await page.getByTestId("health-record-hub").click();
  await page.getByTestId("record-medicines").click();
  await check("medicines");
  // The places Home's grid names that are not built yet: said about him, never to him, too.
  await tab("tab-home");
  await page.getByTestId("do-care").click();
  await check("soon");

  // Every place in his Record her key opens: the Papers tab, then the place — two taps, which
  // is the most any feature is allowed to be.
  for (const entry of ["medicines", "papers", "routine", "timeline", "trends", "providers", "changes"]) {
    await tab("tab-health");
    await page.getByTestId("health-record-hub").click();
    const row = page.getByTestId(`record-${entry}`);
    if (!(await row.isVisible().catch(() => false))) continue;
    await row.click();
    await check(`record-${entry}`);
  }

  // Every part of Family her key opens: Connect's own overview first (its "See everyone with
  // a key" is the way in now, not the tab itself), then each row.
  await tab("tab-connect");
  await page.getByTestId("connect-family-all").click();
  await check("family-home");
  const parts = ["trail", "keys", "roster", "thread", "messages", "metrics", "calendar", "deliveries", "settings", "documents", "consents", "onlyMe"];
  for (const part of parts) {
    await tab("tab-connect");
    await page.getByTestId("connect-family-all").click();
    const pill = page.getByTestId(`open-${part}`);
    if (!(await pill.isVisible().catch(() => false))) continue;
    await pill.click();
    await check(`family-${part}`);
  }

  // The feed, the emergency card, the symptom log and the pill — reached the way she reaches
  // them, through the tab bar, never by reloading the app: a reload puts her back through the
  // doors and is not what this sweep is about.
  await tab("tab-home");
  await page.getByTestId("open-feed").click();
  await check("feed");

  await tab("tab-home");
  await openMe(page);
  // The sheet fills in what it reads (his proud number), which re-renders it: let that land
  // before tapping, or the tap lands on a button that is about to be replaced.
  await page.waitForLoadState("networkidle", { timeout: 5_000 }).catch(() => undefined);
  await page.getByTestId("me-emergency").click();
  await expect(page.getByTestId("emergency-screen")).toBeVisible();
  await check("emergency");

  await tab("tab-home");
  await page.getByTestId("open-symptoms").click();
  await check("symptoms");

  // The pill is about him, and it is the same button: it opens what it says it opens.
  await tab("tab-home");
  await expect(page.getByTestId("not-well")).toHaveText(/Pa is not feeling well/);
  await page.getByTestId("not-well").click();
  await check("not-well");

  expect(seen.length).toBeGreaterThan(20);
  expect(outside, "every screen the tab bar reaches is inside the shell").toEqual([]);
});

/** The defect #177 left, closed by #210: the feed's new formats — "Your week, in 30 seconds",
 *  "From your blood pressure book", "How your blood pressure moved" — used to be drawn on her
 *  Home in his voice. The catalogue twins existed (`HEADLINES_THEIRS`, `LINES_THEIRS`,
 *  `WHY_THEIRS`, added for #194) but the path that serves "Sent to Pa this week" — `GET
 *  /profiles/{id}/feed/week` — did not call the reader the way `GET /feed` does; it does now. */
test("her Home's feed cards say his papers about him by name", async ({ page, request }) => {
  const family = await seedHome(request);
  await signInThroughTheApp(page, family.meiPhone, "Mei");
  await page.getByTestId("door-key").click();
  await todayReady(page);
  const lines = await everyLineOn(page);
  expect(lines.filter(aboutHim)).toEqual([]);
});

/** The same defect on a second path, closed by #210: the family's grant lines used to say what
 *  a key opens in his voice — "Mei is the person who runs your care.", "- your medicines", "Mei
 *  can see them until you say stop." — on her Family screen, where they are about him. `GET
 *  /profiles/{id}/grants` (`app/channels/api/family.py`) now passes its lines through the
 *  reader that says his lines about him, and `app/family/strings.py` and `app/consent/texts.py`
 *  carry the twins for them to be said with (`ROLE_IS`, `WINDOW_LINES_THEIRS`,
 *  `SCOPE_WORDS_THEIRS`). */
test("her Family screen says what a key opens about him by name", async ({ page, request }) => {
  const family = await seedHome(request);
  await signInThroughTheApp(page, family.meiPhone, "Mei");
  await page.getByTestId("door-key").click();
  await todayReady(page);
  await page.getByTestId("tab-connect").click();
  await page.getByTestId("connect-family-all").click();
  await expect(page.getByTestId("grant-lines").first()).toBeVisible();
  const lines = (await page.getByTestId("grant-lines").first().innerText()).split("\n").map((line) => line.trim()).filter(Boolean);
  expect(lines.filter(aboutHim)).toEqual([]);
});

/** A different kind of finding from the two above, closed by #214: not a missing reader on a
 *  backend path, but a verbatim quotation that used to carry nothing marking it as one. Her
 *  Family consents screen (`ConsentsPart`, `web/src/screens/family/Consents.tsx`) shows the
 *  words *he* read and agreed to — `consent.wording_text`, from `app/consent/texts.py`'s
 *  `HOLD_HEALTH_RECORD` and `SHARE_WITH_PERSON` wordings — and used to show them exactly as he
 *  read them, on *her* phone: "You are letting Mei, your daughter, see some of your record. —
 *  your medicines — …". `GET /profiles/{id}/consents` now passes the wording through the same
 *  reader as everything else about him (`CONSENT_THEIRS`, `SCOPE_WORDS_THEIRS`), so what she
 *  reads is never left in his voice to begin with. */
test("her Family consents screen names whose words the quote is", async ({ page, request }) => {
  const family = await seedHome(request);
  await signInThroughTheApp(page, family.meiPhone, "Mei");
  await page.getByTestId("door-key").click();
  await todayReady(page);
  await page.getByTestId("tab-connect").click();
  await page.getByTestId("connect-family-all").click();
  await page.getByTestId("open-consents").click();
  await expect(page.getByTestId("consent-words").first()).toBeVisible();
  const words = page.getByTestId("consent-words");
  const count = await words.count();
  expect(count).toBeGreaterThan(0);
  for (let at = 0; at < count; at += 1) {
    const lines = (await words.nth(at).innerText()).split("\n").map((line) => line.trim()).filter(Boolean);
    expect(lines.filter(aboutHim), `consent-words[${at}]`).toEqual([]);
  }
});
