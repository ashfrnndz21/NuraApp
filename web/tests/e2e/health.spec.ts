import { expect, test } from "@playwright/test";
import { fixClock, nothingDrawnOverLines, seedOwner, todayReady } from "./helpers";
import { seedHome } from "./homeSeed";
import { letIn, signInAs } from "./record-helpers";

/** The Health tab (docs/design/nura-concept-board.html, "3 · Health"): "This week"'s ring, his
 *  readings, his day, his medicines and what is coming up — the same screen for the owner and
 *  for a key, each in its own voice, a key without the readings scope seeing that block
 *  withheld, named, never left off the screen in silence. */

test.beforeEach(async ({ page }) => {
  await fixClock(page);
});

test("his own Health: the ring, his readings, his medicines and his next visit, all grounded", async ({ page, request }) => {
  const pa = await seedHome(request);
  await signInAs(page, pa, "Pa");
  await page.getByTestId("tab-health").click();
  const screen = page.getByTestId("health-screen");
  await expect(screen).toBeVisible();
  await expect(screen.locator("h1")).toHaveText("Your health");

  // "This week": the ring is never drawn without its source line (ProgressRing, warm.test.tsx).
  const ring = page.getByTestId("health-ring");
  await expect(ring).toBeVisible();
  await expect(ring.getByTestId("health-ring-source")).not.toBeEmpty();

  // His readings: the newest blood pressure, from his blood pressure book, with its date.
  const readings = page.getByTestId("readings");
  await expect(readings).toBeVisible();
  await expect(readings.getByTestId("reading-bp")).toContainText("138/84");
  await expect(readings.getByTestId("reading-bp")).toContainText("From your blood pressure book");
  await expect(page.getByTestId("readings-withheld")).toHaveCount(0);

  // His medicines today: the existing dose tiles, the same "Now" section Today shows.
  await expect(page.getByRole("heading", { name: "Now" })).toBeVisible();

  // Coming up: his visit with Dr Tan, the board's own tile.
  const comingUp = page.getByTestId("next-visit-tile");
  await expect(comingUp).toBeVisible();
  await expect(comingUp).toContainText("Dr Tan");

  // A way to the rest of his papers, one tap further on.
  await expect(page.getByTestId("health-record-hub")).toContainText("Your papers");

  // Every tap target is 56px in his density (#118).
  await page.waitForFunction(() => document.querySelector("main")?.getAttribute("aria-busy") !== "true");
  expect(await nothingDrawnOverLines(page.locator("main"), { minTarget: 56 })).toEqual([]);
});

test("her Health: his readings said about him by name, his ring, his next visit", async ({ page, request }) => {
  const pa = await seedHome(request);
  await signInAs(page, { phone: pa.meiPhone }, "Mei", true);
  await page.getByTestId("tab-health").click();
  const screen = page.getByTestId("health-screen");
  await expect(screen.locator("h1")).toHaveText("Pa's health");
  await expect(page.getByTestId("readings-withheld")).toHaveCount(0);
  await expect(page.getByTestId("readings").getByTestId("reading-bp")).toContainText("138/84");
  await expect(page.getByTestId("next-visit-tile")).toBeVisible();
});

test("a key without the readings scope sees the block withheld, named, never silent", async ({ page, request }) => {
  const pa = await seedHome(request);
  const helper = await letIn(request, pa, "Siti", "helper", ["medicines"]);
  await signInAs(page, helper, "Siti", true);
  await page.getByTestId("tab-health").click();
  const withheld = page.getByTestId("readings-withheld");
  await expect(withheld).toBeVisible();
  await expect(withheld).toContainText("Pa's blood pressure book");
  await expect(page.getByTestId("readings")).toHaveCount(0);
  // His medicines today still show: her key opens them.
  await expect(page.getByRole("heading", { name: "Now" })).toBeVisible();
});

test("an empty day: no meals said, no row of placeholders", async ({ page, request }) => {
  const pa = await seedOwner(request, "Ash", []);
  await signInAs(page, pa, "Ash");
  await page.getByTestId("tab-health").click();
  await expect(page.getByTestId("health-screen")).toBeVisible();
  await expect(page.getByTestId("day-logs")).toHaveCount(0);
  // No blood pressure written down yet either: named, not blank.
  await expect(page.getByTestId("readings")).toContainText("Nothing written down yet.");
});
