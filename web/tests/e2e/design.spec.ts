import { expect, test, type Page } from "@playwright/test";
import { API, fixClock, nothingDrawnOverLines, openMe, signInThroughTheApp, TAB_SET, todayReady } from "./helpers";
import { seedHome } from "./homeSeed";

/** D1, the design pass: his Today and her Home as designed, on the patient's phone and a small
 *  one. The hero's number and the State's word are the backend's; nothing is drawn over a line;
 *  the tab bar and the ask bar reserve their own space and are never covered, at any scroll. */

test.beforeEach(async ({ page }) => {
  await fixClock(page);
});

const auth = (token: string) => ({ headers: { Authorization: `Bearer ${token}` } });

/** The shell's promise, checked at the top, the middle and the end of the page: the page ends
 *  above the tab bar, the ask bar (hers) sits above the page, and every tab and every control
 *  of the ask bar is what the page hits at its centre. The problems found, or none. */
async function shellHolds(page: Page): Promise<string[]> {
  return page.evaluate(async () => {
    const frame = () => new Promise((done) => requestAnimationFrame(() => requestAnimationFrame(() => done(null))));
    const problems: string[] = [];
    const region = document.querySelector<HTMLElement>("[data-testid=shell-scroll]")!;
    const bar = document.querySelector<HTMLElement>("nav.tabbar")!;
    const ask = document.querySelector<HTMLElement>(".shell-ask");
    const hit = (element: Element) => {
      const box = element.getBoundingClientRect();
      const at = document.elementFromPoint(box.left + box.width / 2, box.top + box.height / 2);
      return at !== null && (at === element || element.contains(at));
    };
    const page = region.getBoundingClientRect();
    const tabs = bar.getBoundingClientRect();
    if (page.bottom > tabs.top + 0.5) problems.push(`the page runs under the tab bar by ${Math.round(page.bottom - tabs.top)}px`);
    if (tabs.bottom > window.innerHeight + 0.5) problems.push("the tab bar is below the screen");
    if (ask && ask.getBoundingClientRect().bottom > page.top + 0.5) problems.push("the ask bar sits over the page");
    for (const at of [0, 0.5, 1]) {
      region.scrollTop = (region.scrollHeight - region.clientHeight) * at;
      await frame();
      for (const button of bar.querySelectorAll("button")) if (!hit(button)) problems.push(`tab covered at ${at}: ${button.textContent}`);
      if (ask) for (const control of ask.querySelectorAll("button, input")) if (!hit(control)) problems.push(`ask bar covered at ${at}`);
    }
    region.scrollTop = 0;
    return problems;
  });
}

for (const [label, viewport] of [
  ["Pixel 5", null],
  ["a small phone, 360 by 640", { width: 360, height: 640 }],
] as const) {
  test.describe(`D1 — ${label}`, () => {
    if (viewport) test.use({ viewport });

    test("his Today: the backend's number on the wash, a tile per dose due, the coral pill under the hero, nothing covered", async ({ page, request }) => {
      const pa = await seedHome(request);
      await signInThroughTheApp(page, pa.phone, "Pa");
      await todayReady(page);
      await expect(page.locator("html")).toHaveAttribute("data-density", "patient");

      // Home's own doses still come from the backend's own numbers, never one worked out on
      // the phone (cp3-home moved the hero's old "count/words" figure into the Now section and
      // the busy-day insight card; `hero-figure`/`hero-words` no longer exist on Home).
      const slots = (await (await request.get(`${API}/profiles/${pa.profileId}/medicines/today?language=en`, auth(pa.token))).json()) as { due_now: boolean; taken: boolean }[];
      await expect(page.getByTestId("now-card")).toHaveCount(slots.filter((slot) => slot.due_now && !slot.taken).length);

      // One tab set (D1, the reset), his own docked ask bar with the orb, the family's note,
      // the visit, and the coral "Not well?" pill in the header (cp3-home).
      await expect(page.locator("nav.tabbar button")).toHaveText([...TAB_SET]);
      await expect(page.getByTestId("home-ask-bar").getByTestId("home-ask-open")).toHaveText("Ask Nura anything");
      await expect(page.getByTestId("home-ask-bar").getByTestId("home-ask-orb")).toBeVisible();
      await expect(page.getByTestId("family-note")).toContainText("From Mei");
      await expect(page.getByTestId("family-note")).toContainText("The grandchildren were at the park this morning.");
      await expect(page.getByTestId("visit-tile")).toBeVisible();
      // The way in when he feels unwell is in the header, beside the greeting (cp3-home).
      await expect(page.getByTestId("home-head").getByTestId("not-well")).toBeVisible();
      await expect(page.getByTestId("not-well")).toHaveAttribute("class", /coral/);
      // At most one Plum-filled button on the screen.
      expect(await page.locator("main button.plum").count()).toBeLessThanOrEqual(1);

      expect(await nothingDrawnOverLines(page.locator("main"), { lines: "h1, h2, p, .label", controls: "button", minTarget: 56 })).toEqual([]);
      expect(await shellHolds(page)).toEqual([]);
      expect(await page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth)).toBeLessThanOrEqual(0);

      // Me is a sheet from the avatar: everything that was on the Me tab, 56 by 56, then Close.
      await openMe(page);
      const sheet = page.getByTestId("me-sheet");
      for (const id of ["lang-en", "density-patient", "switch-profile", "me-emergency", "sign-out"]) await expect(sheet.getByTestId(id)).toBeVisible();
      // Family is a tab for everyone now (D1, the reset), so the sheet no longer carries it.
      await expect(sheet.getByTestId("me-family")).toHaveCount(0);
      await expect(page.getByTestId("tab-connect")).toBeVisible();
      // The chosen language and look are outlined, not filled: at most one Plum button in the sheet.
      await expect(sheet.getByTestId("lang-en")).toHaveAttribute("aria-pressed", "true");
      expect(await sheet.locator("button.plum").count()).toBeLessThanOrEqual(1);
      expect(await nothingDrawnOverLines(sheet, { lines: "h2, p, .label", controls: "button", minTarget: 56 })).toEqual([]);
      await page.keyboard.press("Escape");
      await expect(sheet).toHaveCount(0);

      // The emergency card is one tap from the sheet: the backend's own page, and Print.
      await openMe(page);
      await page.getByTestId("me-emergency").click();
      await expect(page.getByTestId("me-sheet")).toHaveCount(0);
      await expect(page.getByTestId("emergency-screen")).toBeVisible();
      // W4's card, in the shell: the backend's lines, kept on the phone, with its own Print.
      await expect(page.getByTestId("emergency-card")).toContainText("This is Pa's emergency card.");
      expect(await shellHolds(page)).toEqual([]);
    });

    test("her Home: the State's word and drivers, his pressures, what changed, the next visit, nothing covered", async ({ page, request }) => {
      const family = await seedHome(request);
      await signInThroughTheApp(page, family.meiPhone, "Mei");
      await page.getByTestId("door-key").click();
      await todayReady(page);
      await expect(page.locator("html")).toHaveAttribute("data-density", "caregiver");

      const state = (await (await request.get(`${API}/profiles/${family.profileId}/state?language=en`, auth(family.meiToken))).json()) as { word: string; line: string; drivers: { text: string }[] };
      // cp3-home: the State's word, line and provenance sit in their own panel under the header
      // (`home-state`), shown whenever there is a current State — unchanged from before this
      // rebuild — with the drivers and the sparkline; the safety/boundary sentences themselves
      // stay to once per screen, on the State card when one is also on the page, else in the
      // foot note (`home-safety-note`).
      const panel = page.getByTestId("home-state");
      await expect(panel).toContainText(state.word);
      await expect(panel).toContainText(state.line);
      if (state.drivers.length > 0) await expect(page.getByTestId("drivers").locator(".glass-chip")).toHaveText(state.drivers.map((driver) => driver.text));
      await expect(panel.getByTestId("sparkline")).toBeVisible();
      await expect(panel.getByTestId("sparkline").locator("svg")).toHaveAttribute("aria-label", "The last blood pressure had a top number of 138.");
      await expect(panel.getByTestId("home-from")).toContainText("Nura worked this out on");
      // The way in when he is unwell is in the header, beside her greeting (cp3-home).
      await expect(page.getByTestId("home-head").getByTestId("not-well")).toBeVisible();

      // "What changed" is back on her Home (#207): `GET /changes?peek=true` answers the same
      // words without spending his look, so the tile draws without writing his trail — it is
      // visible, not absent (§3).
      await expect(page.getByTestId("what-changed")).toBeVisible();
      // His next visit and what to buy, side by side, under "What changed" — the reference's
      // own row of two (docs/design/full-experience.html, the Mei persona), not two stacked
      // cards under a "Coming up" heading.
      const nextVisitRow = page.getByTestId("next-visit-and-reorder");
      await expect(nextVisitRow).toHaveClass("two-up");
      await expect(nextVisitRow.getByTestId("next-visit-tile")).toBeVisible();
      await expect(nextVisitRow.getByTestId("supply-tile")).toContainText("left");
      // What Nura is watching for him and what was sent to him this week come right after: her
      // key's own two panels, immediately below the row (F1, #177).
      await expect(page.getByTestId("watching")).toBeVisible();
      await expect(page.getByTestId("sent")).toBeVisible();
      // "Ask about Pa" is Home's own docked ask bar now (cp3-home's `home-ask-bar`), not a
      // separate pill in the flow.
      await expect(page.getByTestId("home-ask-bar").getByTestId("home-ask-open")).toHaveText("Ask about Pa");

      // The same list for her: density changes the look, never the tabs.
      await expect(page.locator("nav.tabbar button")).toHaveText([...TAB_SET]);
      expect(await nothingDrawnOverLines(page.locator("main"), { lines: "h1, h2, p, .label" })).toEqual([]);
      expect(await shellHolds(page)).toEqual([]);
      expect(await page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth)).toBeLessThanOrEqual(0);

      // "Ask about Pa" stays on her other screens, and asks.
      await page.getByTestId("tab-health").click();
      await page.getByTestId("health-record-hub").click();
      await page.getByTestId("record-medicines").click();
      await expect(page.getByTestId("medicine-line").first()).toBeVisible();
      await page.locator(".shell-ask").getByTestId("ask-input").fill("When is his next visit?");
      await page.locator(".shell-ask").getByTestId("ask-input").press("Enter");
      await expect(page.getByTestId("ask-screen")).toBeVisible();
      await expect(page.getByTestId("answer")).toBeVisible();
    });
  });
}

/** A red word typed into Ask (reached from Home's own docked ask bar, cp3-home) goes the
 *  red-flag path first, on the backend, exactly as the same word tapped on the feeling cloud:
 *  what to do now, never an answer looked up first. */
test("a red word typed into Ask or search: the red-flag path first, then what to do now", async ({ page, request }) => {
  const pa = await seedHome(request);
  await signInThroughTheApp(page, pa.phone, "Pa");
  await todayReady(page);
  await page.getByTestId("home-ask-open").click();
  await expect(page.getByTestId("ask-screen")).toBeVisible();
  await page.getByLabel("Your question").fill("My chest is tight");
  await page.getByTestId("ask-send").click();
  await expect(page.getByTestId("what-to-do-screen")).toBeVisible();
  await expect(page.getByTestId("what-to-do-lines").locator("p").first()).toBeVisible();
  await expect(page.getByTestId("answer")).toHaveCount(0);
});
