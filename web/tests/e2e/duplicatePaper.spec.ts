import { expect, test } from "@playwright/test";
import { fixClock, todayReady } from "./helpers";
import { confirmPhoto, openOwn, placeholderPng, signInAs } from "./record-helpers";

/** D-4, duplicates (audit-2026-09-22.md §3.2, §5): re-uploading the exact same bytes (D-4a)
 *  and re-photographing the same paper under a new digest (D-4b), walked through the real
 *  app — Home's own "Add a paper". Every check here is against the real backend on fixtures. */

test.beforeEach(async ({ page }) => {
  await fixClock(page);
});

test("D-4a: the same bytes re-uploaded show the existing card back, with a calm line — never a second read", async ({ page, request }) => {
  const pa = await openOwn(request, "Pa");
  await signInAs(page, pa, "Pa");
  await todayReady(page);

  const bytes = placeholderPng("lipid-panel-2025-08-29");
  await page.getByTestId("report-input").setInputFiles({ name: "lipid.png", mimeType: "image/png", buffer: bytes });
  await page.getByTestId("report-send").click();
  await expect(page.getByTestId("reading-headline")).toBeVisible();

  await page.getByTestId("reading-back").click();
  await todayReady(page);
  await page.getByTestId("report-input").setInputFiles({ name: "lipid-again.png", mimeType: "image/png", buffer: bytes });
  await page.getByTestId("report-send").click();

  await expect(page.getByTestId("duplicate-added-on")).toBeVisible();
  await expect(page.getByTestId("duplicate-added-on")).toContainText("You added this paper on");
  // The ordinary preview still draws underneath the notice — the existing card, not a blank.
  await expect(page.getByTestId("reading-headline")).toBeVisible();
});

test("D-4b: a re-photographed paper asks whether it is the same one, instead of filing silently", async ({ page, request }) => {
  const pa = await openOwn(request, "Pa");
  await confirmPhoto(request, pa.token, pa.profileId, placeholderPng("lipid-panel-2025-08-29"));
  await signInAs(page, pa, "Pa");
  await todayReady(page);

  await page.getByTestId("report-input").setInputFiles({
    name: "lipid-rephoto.png",
    mimeType: "image/png",
    buffer: placeholderPng("lipid-panel-2025-08-29-again"),
  });
  await page.getByTestId("report-send").click();

  const clarify = page.getByTestId("reading-result-duplicate");
  await expect(clarify).toBeVisible();
  await expect(page.getByTestId("clarify-lead").locator(".sr-only")).toContainText("you added on");
  await expect(page.getByTestId("clarify-same")).toContainText("same paper");
  await expect(page.getByTestId("clarify-different")).toContainText("different one");
  await expect(page.getByTestId("reading-headline")).toHaveCount(0);

  await page.getByTestId("clarify-different").click();
  await expect(page.getByTestId("reading-headline")).toBeVisible();
  await expect(page.getByTestId("see-report")).toBeVisible();
});
