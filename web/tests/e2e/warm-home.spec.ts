import { expect, test } from "@playwright/test";
import { cutKey, fixClock, paperPdf, paperPhoto, seedOwner, signInThroughTheApp, TAB_SET, TAB_SET_MEDICINES_ONLY, todayReady } from "./helpers";
import { seedHome } from "./homeSeed";

/** The warm pass (docs/design-direction.md): the welcome before a phone's first sign-in, Home's
 *  greeting, check-in, grid, "Add a health report" and Coming up, the five tabs, and the places
 *  not built yet — each tap going somewhere real, every line the backend's or the catalogue's. */

test.beforeEach(async ({ page }) => {
  await fixClock(page);
});

test("the welcome shows once a phone: Get started reaches the phone number, and it is not shown again", async ({ page }) => {
  await page.goto("./");
  const welcome = page.getByTestId("welcome-screen");
  await expect(welcome).toBeVisible();
  await expect(welcome.locator("h1")).toHaveText("Nura");
  await expect(welcome.locator(".welcome-tagline")).toHaveText("Your health, kept together. Your family, close by.");
  await expect(welcome.locator(".value-tile")).toHaveCount(3);
  await expect(welcome.locator("[data-illustration]")).toHaveAttribute("aria-hidden", "true");
  await page.getByTestId("welcome-start").click();
  await expect(page.getByLabel("Your phone number")).toBeVisible();
  await page.reload();
  await expect(page.getByLabel("Your phone number")).toBeVisible();
  await expect(welcome).toHaveCount(0);
});

test("his Home: the greeting and its picture, the check-in, a grid where every tile goes somewhere, Coming up, and the five tabs", async ({ page, request }) => {
  const pa = await seedHome(request);
  await signInThroughTheApp(page, pa.phone, "Pa");
  await todayReady(page);
  await expect(page.getByTestId("home-skeleton")).toHaveCount(0);

  // cp3-home: the greeting and the question are the header's own now, and there is no more
  // illustration or wave beside them — the living orb is Home's picture (`home-ask-orb`, its
  // ask bar, and the quiet day's own large orb, checked in a11y.spec.ts and design.spec.ts).
  await expect(page.getByTestId("home-head-hello")).toHaveText("Good morning, Pa.");
  await expect(page.getByTestId("home-head").locator("h1")).toHaveText("How are you feeling today?");
  await expect(page.locator("nav.tabbar button")).toHaveText([...TAB_SET]);
  await expect(page.getByTestId("tab-home")).toHaveAttribute("aria-current", "page");

  // Check in opens the way to say how he feels.
  await page.getByTestId("open-symptoms").click();
  await expect(page.getByTestId("symptoms-screen")).toBeVisible();
  await page.getByTestId("tab-home").click();
  await todayReady(page);

  // Every tile opens its place; none is a dead tap or a placeholder any more.
  await expect(page.getByTestId("do-grid").locator("button")).toHaveCount(6);
  for (const [tile, tab] of [
    ["do-health", "tab-health"],
    ["do-medicines", "tab-health"],
    ["do-connect", "tab-connect"],
    ["do-care", "tab-services"],
    ["do-resources", "tab-services"],
  ] as const) {
    await page.getByTestId(tile).click();
    await expect(page.getByTestId(tab)).toHaveAttribute("aria-current", "page");
    await page.getByTestId("tab-home").click();
    await todayReady(page);
  }
  // "Things to do": his own real screen — the week ring, and his steps, water and meals.
  await page.getByTestId("do-activities").click();
  await expect(page.getByTestId("activity-screen")).toBeVisible();
  await expect(page.getByTestId("activity-screen").locator("h1")).toHaveText("Things to do");
  await page.getByTestId("tab-home").click();
  await todayReady(page);

  // Coming up: his next visit, and See all opens his visits under Services.
  await expect(page.getByTestId("upcoming").getByTestId("visit-tile")).toBeVisible();
  await page.getByTestId("upcoming-all").click();
  await expect(page.getByTestId("visits-screen")).toBeVisible();
  await expect(page.getByTestId("tab-services")).toHaveAttribute("aria-current", "page");

  // Profile is his settings, as the Me sheet holds them.
  await page.getByTestId("tab-profile").click();
  await expect(page.getByTestId("profile-screen").getByTestId("lang-en")).toBeVisible();
});

test("Add a health report: a PDF or a photo, through the one upload path, straight onto its review card", async ({ page, request }) => {
  const pa = await seedOwner(request, "Pa", []);
  // The one upload path (`papers.spec.ts`'s own `captures`): `photos` or `imports`, whether
  // the plain route answers at once or the streamed twin narrates its trace first.
  const sent: string[] = [];
  page.on("request", (each) => {
    const found = new URL(each.url()).pathname.match(/\/(photos|imports)(?:\/stream)?$/);
    if (each.method() === "POST" && found) sent.push(found[1]!);
  });
  await signInThroughTheApp(page, pa.phone, "Pa");
  await todayReady(page);
  const add = page.getByTestId("add-report");
  await expect(add).toContainText("Add a paper");
  await expect(add).toContainText("Take a photo of it, or choose the one your doctor sent you.");
  await expect(page.getByTestId("report-input")).toHaveAttribute("accept", "application/pdf,image/*");
  // No `capture`: the phone offers its files, its photos and its camera.
  expect(await page.getByTestId("report-input").getAttribute("capture")).toBeNull();

  // Choosing the file only picks it: its name is shown, and nothing goes until his own "Send it"
  // (reviewer #237 item 6 — a chosen file is never sent on its own).
  await page.getByTestId("report-input").setInputFiles(paperPdf("discharge-letter-2026-08-20"));
  await expect(page.getByTestId("report-confirm-name")).toContainText("discharge-letter-2026-08-20");
  expect(sent).toEqual([]);
  await page.getByTestId("report-send").click();

  // A report Nura can read: its review card, the same as every paper's.
  await expect(page.getByTestId("review-card")).toContainText("This is a hospital letter.");
  expect(sent).toEqual(["imports"]);
  await page.getByTestId("looks-right").click();
  await expect(page.getByTestId("paper-checked")).toHaveText("Nura wrote it down.");

  // One it cannot read: the backend's own words, never a claim that it was read.
  await page.getByTestId("papers-finish").click();
  await todayReady(page);
  await page.getByTestId("report-input").setInputFiles(paperPhoto("receipt-2026-09-01"));
  await page.getByTestId("report-send").click();
  const result = page.getByTestId("paper-result");
  await expect(result).toHaveAttribute("data-outcome", "notHealth");
  await expect(result.getByTestId("paper-not-health")).not.toBeEmpty();
  await expect(page.getByTestId("review-card")).toHaveCount(0);
});

test("her Home says his check-in and her places about him by name", async ({ page, request }) => {
  const family = await seedHome(request);
  await signInThroughTheApp(page, family.meiPhone, "Mei");
  await page.getByTestId("door-key").click();
  await todayReady(page);
  await expect(page.getByTestId("home-head-hello")).toHaveText("Good morning, Mei.");
  await expect(page.getByTestId("home-head").locator("h1")).toHaveText("How is Pa feeling today?");
  // The reference's own reading order (docs/design/full-experience.html, the Mei persona):
  // what changed, his next visit and what to buy, what Nura is watching for him and what was
  // sent to him this week, all above the warm check-in and "What to do for Pa" grid.
  const main = page.locator("main");
  // His visits and his medicines are their own reads after Today is ready (`useToday`'s
  // `visits` and `page.lines`), so the row they make is awaited before its place is checked.
  for (const id of ["what-changed", "next-visit-and-reorder", "watching", "sent", "daily-check-in"]) {
    await expect(page.getByTestId(id)).toBeAttached();
  }
  for (const [before, after] of [
    ["what-changed", "next-visit-and-reorder"],
    ["next-visit-and-reorder", "watching"],
    ["watching", "sent"],
    ["sent", "daily-check-in"],
  ] as const) {
    const order = await main.evaluate(
      (el, [a, b]) => {
        const first = el.querySelector(`[data-testid="${a}"]`);
        const second = el.querySelector(`[data-testid="${b}"]`);
        if (!first || !second) return "missing";
        const position = first.compareDocumentPosition(second);
        return position & Node.DOCUMENT_POSITION_FOLLOWING ? "in order" : "out of order";
      },
      [before, after],
    );
    expect(order, `${before} before ${after}`).toBe("in order");
  }
  await expect(page.getByTestId("daily-check-in")).toContainText("Tell Nura how Pa feels today");
  // The caregiver twin (bcd96c99): "What to do for Pa.", not the generic second-person line.
  await expect(page.locator("#do-title")).toHaveText("What to do for Pa.");
  const tiles = await page.getByTestId("do-grid").locator("button").evaluateAll((all) => all.map((each) => each.getAttribute("data-testid")));
  expect(tiles[0]).toBe("do-health");
  expect(tiles.slice(-3)).toEqual(["do-activities", "do-care", "do-resources"]);
});

test("a key with only the medicines: no Connect or Services tab, no Connect tile, no See all visits", async ({ page, request }) => {
  const pa = await seedOwner(request);
  const kim = await cutKey(request, pa, { name: "Kim", prefix: "+659559" }, "caregiver", ["medicines"]);
  await signInThroughTheApp(page, kim.phone, "Kim");
  await page.getByTestId("door-key").click();
  await todayReady(page);
  await expect(page.locator("nav.tabbar button")).toHaveText([...TAB_SET_MEDICINES_ONLY]);
  await expect(page.getByTestId("do-connect")).toHaveCount(0);
  await expect(page.getByTestId("do-medicines")).toBeVisible();
  await expect(page.getByTestId("upcoming-all")).toHaveCount(0);
});
