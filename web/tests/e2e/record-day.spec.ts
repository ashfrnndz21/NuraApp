import { expect, test } from "@playwright/test";
import { API, fixClock, seedMedicine } from "./helpers";
import { auth, confirmPhoto, EVERY_PART, letIn, LOOKS, lookAs, openOwn, placeholderPng, readable, signInAs } from "./record-helpers";

/** Checkpoint 25, his blood tests and his day (W5): E09-01 a lab trend against its range, the
 *  direction in words, the boundary last; E10-01 the day set once on the chief's yes, as lines
 *  to him and a table to her. */

test.beforeEach(async ({ page }) => {
  await fixClock(page);
});

for (const look of LOOKS) {
  test(`his cholesterol over time (${look}): each result against its range, the direction in words, the boundary last`, async ({ page, request }) => {
    const pa = await openOwn(request);
    await confirmPhoto(request, pa.token, pa.profileId, placeholderPng("lipid-panel-2023-09-07"));
    await confirmPhoto(request, pa.token, pa.profileId, placeholderPng("lipid-panel-2025-08-29"));
    const trend = (await (await request.get(`${API}/profiles/${pa.profileId}/trends/total_cholesterol?language=en`, auth(pa.token))).json()) as {
      lines: string[];
      boundary: string;
      points: unknown[];
    };
    expect(trend.points).toHaveLength(2);
    const boundary = trend.boundary.split("\n").filter((line) => line.trim().length > 0);

    await signInAs(page, pa, "Pa");
    await lookAs(page, look);
    await page.getByTestId("record-trends").click();
    await readable(page, look);
    await page.getByTestId("analyte-total_cholesterol").click();
    const tile = page.getByTestId("trend");
    for (const line of trend.lines.filter((each) => !boundary.includes(each))) await expect(tile.getByTestId("trend-lines")).toContainText(line);
    const points = tile.getByTestId("trend-point");
    await expect(points).toHaveCount(2);
    for (const point of await points.all()) await expect(point).toContainText("The range is");
    await expect(tile.locator(":scope > .lines").last()).toHaveAttribute("data-testid", "boundary");
    for (const line of boundary) await expect(tile.getByTestId("boundary")).toContainText(line);
    await readable(page, look);
  });
}

test("the day: the chief sets it once on her yes; it reads to him as one line per moment and to her as a table", async ({ page, request }) => {
  const pa = await openOwn(request);
  await seedMedicine(request, pa.token, pa.profileId, { generic: "amlodipine", strength: "5 mg", dose_text: "1 tab OD", quantity: 30 });
  const mei = await letIn(request, pa, "Mei", "chief", EVERY_PART);

  // Mei, in her density: the default day as a table, nobody has set it yet.
  await signInAs(page, mei, "Mei", true);
  await page.getByTestId("tab-record").click();
  await page.getByTestId("record-routine").click();
  await expect(page.getByTestId("routine-not-set")).toHaveText("Nobody has set the day yet.");
  await expect(page.getByTestId("routine-table")).toBeVisible();
  await readable(page, "caregiver");

  // Her builder: a blood pressure when he wakes, a walk after dinner; the day read back, her yes.
  await page.getByTestId("set-day").click();
  await readable(page, "caregiver");
  await page.getByTestId("reading-blood_pressure-wake").click();
  await page.getByTestId("walk-dinner").click();
  await page.getByTestId("check-day").click();
  await expect(page.getByTestId("day-ask")).toContainText("Is this the day?");
  await readable(page, "caregiver");
  await page.getByTestId("day-yes").click();
  await expect(page.getByTestId("record-note")).toHaveText("Nura wrote down the day.");
  await expect(page.getByTestId("routine-not-set")).toHaveCount(0);
  const table = page.getByTestId("routine-table");
  await expect(table.locator('tr[data-anchor="wake"]')).toContainText("Blood pressure");
  await expect(table.locator('tr[data-anchor="dinner"]')).toContainText("A walk");
  await expect(table.locator('tr[data-anchor="breakfast"]')).toContainText("amlodipine 5 mg");
  await readable(page, "caregiver");

  // His day, as he reads it: one line per moment, the backend's own.
  const his = (await (await request.get(`${API}/profiles/${pa.profileId}/routine?language=en`, auth(pa.token))).json()) as { persona: string; lines: string[]; set: boolean };
  expect(his.persona).toBe("patient");
  expect(his.set).toBe(true);
  expect(his.lines.length).toBeGreaterThanOrEqual(3);
  await lookAs(page, "patient");
  await page.getByTestId("record-routine").click();
  const lines = page.getByTestId("routine-lines");
  for (const line of his.lines) await expect(lines).toContainText(line);
  await expect(page.getByTestId("set-day")).toHaveCount(0);
  await readable(page, "patient");
});
