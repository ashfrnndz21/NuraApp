import { expect, test } from "@playwright/test";
import { cutKey, fixClock, nothingDrawnOverLines, paperPdf, paperPhoto, seedOwner, signInThroughTheApp, todayReady } from "./helpers";
import { seedHome } from "./homeSeed";

/** The warm pass (docs/design-direction.md): the welcome before a phone's first sign-in, Home's
 *  greeting, check-in, grid, "Add a health report" and Coming up, the five tabs, and the places
 *  not built yet — each tap going somewhere real, every line the backend's or the catalogue's. */

test.beforeEach(async ({ page }) => {
  await fixClock(page);
});

test("the welcome shows once a phone: Sign in reaches the phone number, and it is not shown again", async ({ page }) => {
  await page.goto("./");
  const welcome = page.getByTestId("welcome-screen");
  await expect(welcome).toBeVisible();
  await expect(welcome.locator("h1")).toHaveText("Nura");
  await expect(welcome.locator(".welcome-tagline")).toHaveText("Your health, kept simple. Your family, close by.");
  await expect(welcome.locator(".value-tile")).toHaveCount(3);
  await expect(welcome.locator("[data-illustration]")).toHaveAttribute("aria-hidden", "true");
  await page.getByTestId("welcome-sign-in").click();
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

  const hero = page.getByTestId("today-hero");
  await expect(hero.locator(".hero-greeting")).toHaveText("Good morning, Pa.");
  await expect(hero.locator(".hero-ask")).toHaveText("How are you feeling today?");
  await expect(hero.locator("[data-illustration=couple]")).toHaveAttribute("aria-hidden", "true");
  await expect(hero.locator(".hero-wave")).toHaveAttribute("aria-hidden", "true");
  await expect(page.locator("nav.tabbar button")).toHaveText(["Home", "Health", "Connect", "Services", "Profile"]);
  await expect(page.getByTestId("tab-home")).toHaveAttribute("aria-current", "page");

  // Check in opens the way to say how he feels.
  await page.getByTestId("open-symptoms").click();
  await expect(page.getByTestId("symptoms-screen")).toBeVisible();
  await page.getByTestId("tab-home").click();
  await todayReady(page);

  // Every tile opens its place, or says plainly it is not built yet; none is a dead tap.
  await expect(page.getByTestId("do-grid").locator("button")).toHaveCount(6);
  for (const [tile, tab] of [
    ["do-health", "tab-health"],
    ["do-medicines", "tab-health"],
    ["do-connect", "tab-connect"],
  ] as const) {
    await page.getByTestId(tile).click();
    await expect(page.getByTestId(tab)).toHaveAttribute("aria-current", "page");
    await page.getByTestId("tab-home").click();
    await todayReady(page);
  }
  for (const [tile, words] of [
    ["do-activities", "Things to do"],
    ["do-care", "Care services"],
    ["do-resources", "Guides"],
  ] as const) {
    await page.getByTestId(tile).click();
    const soon = page.getByTestId("soon-screen");
    await expect(soon.locator("h1")).toHaveText(words);
    await expect(soon).toContainText("Nura cannot do this yet.");
    await page.getByTestId("soon-back").click();
    await todayReady(page);
  }

  // Coming up: his next visit, and See all opens his visits under Services.
  await expect(page.getByTestId("upcoming").getByTestId("visit-tile")).toBeVisible();
  await page.getByTestId("upcoming-all").click();
  await expect(page.getByTestId("visits-screen")).toBeVisible();
  await expect(page.getByTestId("tab-services")).toHaveAttribute("aria-current", "page");

  // Profile is his settings, as the Me sheet holds them.
  await page.getByTestId("tab-profile").click();
  await expect(page.getByTestId("profile-screen").getByTestId("lang-en")).toBeVisible();

  await page.getByTestId("tab-home").click();
  await todayReady(page);
  expect(await nothingDrawnOverLines(page.locator("main"), { lines: "h1, h2, p", controls: "button", minTarget: 56 })).toEqual([]);
});

test("Add a health report: a PDF or a photo, through the one upload path, straight onto its review card", async ({ page, request }) => {
  const pa = await seedOwner(request, "Pa", []);
  const sent: string[] = [];
  page.on("request", (each) => {
    const found = new URL(each.url()).pathname.match(/\/(photos|imports)$/);
    if (each.method() === "POST" && found) sent.push(found[1]!);
  });
  await signInThroughTheApp(page, pa.phone, "Pa");
  await todayReady(page);
  const add = page.getByTestId("add-report");
  await expect(add).toContainText("Add a health report");
  await expect(add).toContainText("A file, or a photo of a paper");
  await expect(page.getByTestId("report-input")).toHaveAttribute("accept", "application/pdf,image/*");
  // No `capture`: the phone offers its files, its photos and its camera.
  expect(await page.getByTestId("report-input").getAttribute("capture")).toBeNull();

  // A report Nura can read: its review card, the same as every paper's.
  await page.getByTestId("report-input").setInputFiles(paperPdf("discharge-letter-2026-08-20"));
  await expect(page.getByTestId("review-card")).toContainText("This is a hospital letter.");
  expect(sent).toEqual(["imports"]);
  await page.getByTestId("looks-right").click();
  await expect(page.getByTestId("paper-checked")).toHaveText("Nura wrote it down.");

  // One it cannot read: the backend's own words, never a claim that it was read.
  await page.getByTestId("papers-finish").click();
  await todayReady(page);
  await page.getByTestId("report-input").setInputFiles(paperPhoto("receipt-2026-09-01"));
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
  const hero = page.getByTestId("home-hero");
  await expect(hero.locator(".hero-greeting")).toHaveText("Good morning, Mei.");
  await expect(hero.locator(".hero-ask")).toHaveText("How is Pa feeling today?");
  await expect(page.getByTestId("daily-check-in")).toContainText("Take a minute to say how Pa feels.");
  await expect(page.locator("#do-title")).toHaveText("Places to go");
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
  await expect(page.locator("nav.tabbar button")).toHaveText(["Home", "Health", "Profile"]);
  await expect(page.getByTestId("do-connect")).toHaveCount(0);
  await expect(page.getByTestId("do-medicines")).toBeVisible();
  await expect(page.getByTestId("upcoming-all")).toHaveCount(0);
});
