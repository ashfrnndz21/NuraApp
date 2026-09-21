import { expect, test, type Page } from "@playwright/test";
import { API, fixClock, nothingDrawnOverLines, seedOwner, todayReady } from "./helpers";
import { seedHome } from "./homeSeed";
import { letIn, signInAs } from "./record-helpers";

const auth = (token: string) => ({ headers: { Authorization: `Bearer ${token}` } });

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

// --- The ring's number never crosses its own stroke (owner's required fix on PR #294) ---------
// Reproduced with NURA_DEMO_SEED=1, "Try it as Pa", the Health tab (the seeded week gave
// "5 of 5"): the figure was set larger than the ring's own inner space and ran across the
// stroke, and the label ("Tablets taken this week") was wider than the ring and ran across its
// bottom stroke. `ProgressRing` now holds only the number inside the circle (`ring-centre`); the
// label and the source line are both their own line under it. Proved geometrically here — not
// by eye — for three real figures (`5 of 5`, `12 of 14`, `0 of 0`), framed (1280x800), full-bleed
// (390x844) and with his large-text setting on.

interface Box {
  x: number;
  y: number;
  width: number;
  height: number;
}

function boxContains(outer: Box, inner: Box): boolean {
  return inner.x >= outer.x - 0.5 && inner.y >= outer.y - 0.5 && inner.x + inner.width <= outer.x + outer.width + 0.5 && inner.y + inner.height <= outer.y + outer.height + 0.5;
}

function boxesIntersect(a: Box, b: Box): boolean {
  return !(a.x + a.width <= b.x || b.x + b.width <= a.x || a.y + a.height <= b.y || b.y + b.height <= a.y);
}

async function mockRing(page: Page, words: string, value: number, total: number): Promise<void> {
  await page.route("**/health/overview*", (route) =>
    route.fulfill({
      json: {
        ring: { kind: "doses", label: "Tablets taken this week", words, value, total, week_starts_on: "2026-09-14", as_of: "2026-09-14T10:00:00+08:00" },
        metrics: [],
      },
    }),
  );
}

async function ringGeometry(page: Page): Promise<{ circle: Box; number: Box; label: Box; source: Box }> {
  const ring = page.getByTestId("health-ring");
  await expect(ring).toBeVisible();
  const circle = await ring.locator(".ring-circle").boundingBox();
  const number = await page.getByTestId("health-ring-figure").boundingBox();
  const label = await ring.locator(".ring-label").boundingBox();
  const source = await page.getByTestId("health-ring-source").boundingBox();
  if (!circle || !number || !label || !source) throw new Error("the ring did not lay out");
  return { circle, number, label, source };
}

function assertRingHolds(g: { circle: Box; number: Box; label: Box; source: Box }, where: string): void {
  expect(boxContains(g.circle, g.number), `${where}: the number strays outside the ring`).toBe(true);
  expect(boxesIntersect(g.circle, g.label), `${where}: the label crosses the ring's stroke`).toBe(false);
  expect(boxesIntersect(g.circle, g.source), `${where}: the source line crosses the ring's stroke`).toBe(false);
}

// "0 of 0" itself is no longer a figure the ring ever draws (package 10): a total of zero
// means there is nothing for the ring to count, so `ThisWeek` shows the calm empty state
// (`health-ring-empty`) in its place instead — see the dedicated test below. The geometry
// check here stays for every total the ring still draws a real figure for.
const FIGURES: { words: string; value: number; total: number }[] = [
  { words: "5 of 5", value: 5, total: 5 },
  { words: "12 of 14", value: 12, total: 14 },
];

for (const { words, value, total } of FIGURES) {
  test(`the ring holds "${words}" without crossing its stroke — framed at 1280x800`, async ({ page, request }) => {
    await page.setViewportSize({ width: 1280, height: 800 });
    const pa = await seedHome(request);
    await mockRing(page, words, value, total);
    await signInAs(page, pa, "Pa");
    await page.getByTestId("tab-health").click();
    await expect(page.getByTestId("health-ring-figure")).toHaveText(words);
    assertRingHolds(await ringGeometry(page), `"${words}" framed`);
  });

  test(`the ring holds "${words}" without crossing its stroke — full-bleed at 390x844`, async ({ page, request }) => {
    await page.setViewportSize({ width: 390, height: 844 });
    const pa = await seedHome(request);
    await mockRing(page, words, value, total);
    await signInAs(page, pa, "Pa");
    await page.getByTestId("tab-health").click();
    await expect(page.getByTestId("health-ring-figure")).toHaveText(words);
    assertRingHolds(await ringGeometry(page), `"${words}" full-bleed`);
  });

  test(`the ring holds "${words}" without crossing its stroke — his large-text setting on`, async ({ page, request }) => {
    const pa = await seedHome(request);
    const current = (await (await request.get(`${API}/profiles/${pa.profileId}/settings`, auth(pa.token))).json()) as Record<string, unknown>;
    const saved = await request.put(`${API}/profiles/${pa.profileId}/settings`, {
      ...auth(pa.token),
      data: {
        language: "en",
        conditions: (current.conditions as string[] | null) ?? [],
        density: "simple",
        large_text: true,
        high_contrast: false,
        voice_on: false,
        big_targets: false,
        one_thing_per_screen: false,
        read_back: false,
        repeat_prompts: false,
        preferred_name: "Pa",
        doctor_name: null,
        breakfast_time: null,
        birth_decade: null,
      },
    });
    expect(saved.ok(), await saved.text()).toBe(true);
    await mockRing(page, words, value, total);
    await signInAs(page, pa, "Pa");
    await expect(page.locator("html")).toHaveAttribute("data-text", "large");
    await page.getByTestId("tab-health").click();
    await expect(page.getByTestId("health-ring-figure")).toHaveText(words);
    assertRingHolds(await ringGeometry(page), `"${words}" large-text`);
  });
}

// --- The ring's calm empty state (package 10): a fresh profile with no active medicines has
// nothing for "doses taken this week" to count. The backend's own words for that count are
// "0 of 0" (`ring_words`), which reads as a broken score, not a calm nothing-yet, so the ring
// itself is never drawn with a zero in it — `ThisWeek` shows this line in its place, at every
// breakpoint the ring's own geometry tests already cover above.

for (const [label, size] of [
  ["framed at 1280x800", { width: 1280, height: 800 }],
  ["full-bleed at 390x844", { width: 390, height: 844 }],
] as const) {
  test(`the week ring shows a calm empty state, never "0 of 0" — ${label}`, async ({ page, request }) => {
    await page.setViewportSize(size);
    const pa = await seedHome(request);
    await mockRing(page, "0 of 0", 0, 0);
    await signInAs(page, pa, "Pa");
    await page.getByTestId("tab-health").click();
    await expect(page.getByTestId("health-ring")).toHaveCount(0);
    const empty = page.getByTestId("health-ring-empty");
    await expect(empty).toBeVisible();
    await expect(empty).not.toHaveText("0 of 0");
    // Still grounded in the same card, never floating loose or crossing another line.
    const card = page.getByTestId("health-week");
    const cardBox = await card.boundingBox();
    const emptyBox = await empty.boundingBox();
    if (!cardBox || !emptyBox) throw new Error("the empty ring state did not lay out");
    expect(boxContains(cardBox, emptyBox)).toBe(true);
  });
}
