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

      // The hero is the backend's count and words, never one worked out on the phone.
      const now = (await (await request.get(`${API}/profiles/${pa.profileId}/medicines/now?language=en`, auth(pa.token))).json()) as { count: number | null; words: string | null };
      if (now.count === null) await expect(page.getByTestId("hero-figure")).toHaveCount(0);
      else {
        await expect(page.getByTestId("today-hero").getByTestId("hero-figure")).toHaveText(String(now.count));
        await expect(page.getByTestId("today-hero").getByTestId("hero-words")).toHaveText(now.words!);
      }
      const slots = (await (await request.get(`${API}/profiles/${pa.profileId}/medicines/today?language=en`, auth(pa.token))).json()) as { due_now: boolean; taken: boolean }[];
      await expect(page.getByTestId("now-card")).toHaveCount(slots.filter((slot) => slot.due_now && !slot.taken).length);
      if (now.count !== null && slots.some((slot) => slot.due_now)) await expect(page.getByTestId("now-card")).toHaveCount(now.count);

      // One tab set (D1, the reset), his ask bar, the family's note, the visit, and the coral
      // pill under the hero.
      await expect(page.locator("nav.tabbar button")).toHaveText([...TAB_SET]);
      await expect(page.getByTestId("askbar").getByTestId("ask-input")).toHaveAttribute("placeholder", "Ask Nura a question");
      await expect(page.getByTestId("family-note")).toContainText("From Mei");
      await expect(page.getByTestId("family-note")).toContainText("The grandchildren were at the park this morning.");
      await expect(page.getByTestId("visit-tile")).toBeVisible();
      // The way in when he feels unwell comes before anything ranked: right under the hero.
      expect(await page.getByTestId("today-hero").evaluate((hero) => hero.nextElementSibling?.getAttribute("data-testid"))).toBe("not-well");
      await expect(page.getByTestId("not-well")).toHaveAttribute("class", /coral/);
      // At most one Plum-filled button on the screen.
      expect(await page.locator("main button.plum, main .askbar-go").count()).toBeLessThanOrEqual(1);

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
      const hero = page.getByTestId("home-hero");
      await expect(hero.getByTestId("hero-figure")).toHaveText(state.word);
      await expect(hero.getByTestId("hero-words")).toHaveText(state.line);
      if (state.drivers.length > 0) await expect(page.getByTestId("drivers").locator(".glass-chip")).toHaveText(state.drivers.map((driver) => driver.text));
      await expect(hero.getByTestId("sparkline")).toBeVisible();
      await expect(hero.getByTestId("sparkline").locator("svg")).toHaveAttribute("aria-label", "The last blood pressure had a top number of 138.");
      // Where the State came from, and the way in when he is unwell, on her Home too.
      await expect(hero.getByTestId("home-from")).toContainText("Nura worked this out on");
      expect(await page.getByTestId("home-hero").evaluate((hero) => hero.nextElementSibling?.getAttribute("data-testid"))).toBe("not-well");

      // "What changed" is not on her Home: `GET /changes` is itself the looking — it writes the
      // look on his trail and the next read counts from it — so it lives on the Record's own
      // screen, where looking is what she came to do.
      await expect(page.getByTestId("what-changed")).toHaveCount(0);
      await expect(page.getByTestId("ask-about")).toHaveText("Ask about Pa");
      await expect(page.getByTestId("next-visit-tile")).toBeVisible();
      await expect(page.getByTestId("supply-tile")).toContainText("left");

      // The same list for her: density changes the look, never the tabs.
      await expect(page.locator("nav.tabbar button")).toHaveText([...TAB_SET]);
      await expect(page.locator(".shell-ask").getByTestId("ask-input")).toHaveAttribute("placeholder", "Ask about Pa");
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

/** A red word typed into Ask or search (on the top of his Today) goes the red-flag path first,
 *  on the backend, exactly as the same word tapped on the feeling cloud: what to do now, never
 *  an answer looked up first. */
test("a red word typed into Ask or search: the red-flag path first, then what to do now", async ({ page, request }) => {
  const pa = await seedHome(request);
  await signInThroughTheApp(page, pa.phone, "Pa");
  await todayReady(page);
  const ask = page.getByTestId("askbar").getByTestId("ask-input");
  await ask.fill("My chest is tight");
  await ask.press("Enter");
  await expect(page.getByTestId("what-to-do-screen")).toBeVisible();
  await expect(page.getByTestId("what-to-do-lines").locator("p").first()).toBeVisible();
  await expect(page.getByTestId("answer")).toHaveCount(0);
});
