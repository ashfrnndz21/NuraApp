import { expect, test } from "@playwright/test";
import { API, fixClock, openMe, paperPhoto, seedOwner, signInThroughTheApp, todayReady } from "./helpers";
import { seedHome } from "./homeSeed";

/** The phone frame (owner's scope change 2026-09-21, docs/design/README.md item 7): above 600px
 *  wide, the whole app renders inside a 390px device frame on a plain dark page; below 600px (a
 *  real phone) there is no frame — full-bleed, exactly a phone app. Everything the app draws —
 *  the tab bar, a sheet — has to stay inside the frame on a wide screen. */

test.beforeEach(async ({ page }) => {
  await fixClock(page);
});

test("above 600px: the frame exists, is 390px wide, and the tab bar sits inside it", async ({ page, request }) => {
  await page.setViewportSize({ width: 1280, height: 800 });
  const pa = await seedHome(request);
  await signInThroughTheApp(page, pa.phone, "Pa");
  await todayReady(page);

  const frame = page.locator("#phone-frame");
  await expect(frame).toBeVisible();
  const frameBox = (await frame.boundingBox())!;
  expect(Math.round(frameBox.width)).toBe(390);
  expect(frameBox.height).toBeLessThanOrEqual(844.5);

  const bar = page.locator("nav.tabbar");
  await expect(bar).toBeVisible();
  const barBox = (await bar.boundingBox())!;
  expect(barBox.x).toBeGreaterThanOrEqual(frameBox.x - 1);
  expect(barBox.x + barBox.width).toBeLessThanOrEqual(frameBox.x + frameBox.width + 1);
  expect(barBox.y).toBeGreaterThanOrEqual(frameBox.y - 1);
  expect(barBox.y + barBox.height).toBeLessThanOrEqual(frameBox.y + frameBox.height + 1);

  // A plain dark page around the frame — the ground colour, not the app's own atmosphere.
  const pageGround = await page.evaluate(() => getComputedStyle(document.querySelector(".page-ground")!).backgroundColor);
  expect(pageGround).toBe("rgb(21, 17, 29)"); // #15111d
});

test("below 600px: there is no frame — the shell fills the viewport exactly like a phone app", async ({ page, request }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  const pa = await seedHome(request);
  await signInThroughTheApp(page, pa.phone, "Pa");
  await todayReady(page);

  const frame = page.locator("#phone-frame");
  const frameBox = (await frame.boundingBox())!;
  // Full-bleed: the frame fills the whole viewport, no bezel, no radius.
  expect(Math.round(frameBox.width)).toBe(390);
  expect(Math.round(frameBox.height)).toBe(844);
  expect(frameBox.x).toBe(0);
  expect(frameBox.y).toBe(0);
  const radius = await frame.evaluate((el) => getComputedStyle(el).borderRadius);
  expect(radius).toBe("0px");
});

test("a sheet opened above 600px lies inside the frame, not the full browser window", async ({ page, request }) => {
  await page.setViewportSize({ width: 1280, height: 800 });
  const pa = await seedHome(request);
  await signInThroughTheApp(page, pa.phone, "Pa");
  await todayReady(page);

  const frameBox = (await page.locator("#phone-frame").boundingBox())!;
  await openMe(page);
  const sheet = page.getByTestId("me-sheet");
  await expect(sheet).toBeVisible();
  // The sheet slides up over 0.55s: wait until it has come to rest before measuring it.
  await expect.poll(async () => { const box = await sheet.boundingBox(); return box ? box.y + box.height : Infinity; }).toBeLessThanOrEqual(frameBox.y + frameBox.height + 1);
  const sheetBox = (await sheet.boundingBox())!;
  expect(sheetBox.x).toBeGreaterThanOrEqual(frameBox.x - 1);
  expect(sheetBox.x + sheetBox.width).toBeLessThanOrEqual(frameBox.x + frameBox.width + 1);
  expect(sheetBox.y).toBeGreaterThanOrEqual(frameBox.y - 1);
  expect(sheetBox.y + sheetBox.height).toBeLessThanOrEqual(frameBox.y + frameBox.height + 1);
});

/** E02-07 library part A #1: the owner's own screenshot showed a bright vertical line down the
 *  left edge of the report table's panel, and every row's text touching it — a `<button>`
 *  row's user-agent default border (`report-table-row` set only `border-top`, never resetting
 *  the other three sides), and too little inner padding. Proved by computed style, not by eye,
 *  at desktop width inside the frame and full-bleed on a real phone. */
async function reportTableGeometry(page: import("@playwright/test").Page) {
  const panel = page.getByTestId("report-rows");
  await expect(panel).toBeVisible();
  const row = panel.locator(".report-table-row").first();
  await expect(row).toBeVisible();
  return page.evaluate(
    ([panelSel, rowSel]) => {
      const panelEl = document.querySelector(`[data-testid="${panelSel}"]`)!;
      const rowEl = panelEl.querySelector(rowSel)!;
      const panelStyle = getComputedStyle(panelEl);
      const panelRect = panelEl.getBoundingClientRect();
      const rowRect = rowEl.getBoundingClientRect();
      return {
        borderLeft: panelStyle.borderLeftWidth,
        borderRight: panelStyle.borderRightWidth,
        rowBorderLeft: getComputedStyle(rowEl).borderLeftWidth,
        rowBorderRight: getComputedStyle(rowEl).borderRightWidth,
        leftInset: rowRect.left - panelRect.left,
        rightInset: panelRect.right - rowRect.right,
      };
    },
    ["report-rows", ".report-table-row"] as const,
  );
}

for (const viewport of [
  { name: "1280x900 (desktop, inside the frame)", width: 1280, height: 900 },
  { name: "390x844 (full-bleed, a real phone)", width: 390, height: 844 },
]) {
  test(`the report table has no left border and its rows are inset >= 16px — ${viewport.name}`, async ({ page, request }) => {
    await page.setViewportSize({ width: viewport.width, height: viewport.height });
    const pa = await seedOwner(request, "Pa", []);
    const posted = await request.post(`${API}/profiles/${pa.profileId}/photos`, {
      headers: { Authorization: `Bearer ${pa.token}` },
      data: { data: paperPhoto("clinic-slip-2026-09-10").buffer.toString("base64"), content_type: "image/png", captured_at: "2026-09-10T09:00:00Z" },
    });
    expect(posted.status(), await posted.text()).toBe(201);
    const card = (await posted.json()) as { card_id: string };

    await signInThroughTheApp(page, pa.phone, "Pa");
    await todayReady(page);
    // The card above was made directly over the API: open it through the Record's own papers
    // list, where every card — waiting or not — is listed (library part B #1).
    await page.getByTestId("tab-health").click();
    await page.getByTestId("health-record-hub").click();
    await page.getByTestId("record-papers").click();
    const row = page.getByTestId("waiting-paper");
    await expect(row).toHaveAttribute("data-card-id", card.card_id);
    await row.click();

    const geometry = await reportTableGeometry(page);
    // No user-agent default border on the sides `border-top` never touched.
    expect(geometry.rowBorderLeft).toBe("0px");
    expect(geometry.rowBorderRight).toBe("0px");
    // The panel's own 1px glass border is even on both sides — never a heavier "line" on the left.
    expect(geometry.borderLeft).toBe(geometry.borderRight);
    // Inset from the panel's own edge, not just from the page: at least 16px either side.
    expect(geometry.leftInset).toBeGreaterThanOrEqual(16);
    expect(geometry.rightInset).toBeGreaterThanOrEqual(16);
  });
}
