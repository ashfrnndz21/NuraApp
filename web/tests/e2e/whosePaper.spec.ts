import { expect, test } from "@playwright/test";
import { fixClock, todayReady } from "./helpers";
import { confirmPhoto, openOwn, placeholderPng, signInAs } from "./record-helpers";

/** D-2, "whose paper is it" (audit-2026-09-22.md §3.2, §5; docs/design/build-spec.md's "Owner
 *  requirement added 2026-09-22"): the reading screen's one plain clarifying question, walked
 *  through the real app — Home's own "Add a paper", the same path `warm-home.spec.ts` walks
 *  for the happy case. Every check here is against the real backend on fixtures, no model call. */

test.beforeEach(async ({ page }) => {
  await fixClock(page);
});

test("a demo-style lab sheet against a profile with his own paper on file asks whose it is, in the blueprint's conversation shape", async ({ page, request }) => {
  const pa = await openOwn(request, "Pa");
  // His own first paper, confirmed: the record now holds person.birth_year 1951 — the 1950s
  // — for the identity check to compare the next paper against (`_pa_with_papers_on_file`
  // in `backend/tests/test_whose_paper.py` mirrors this exact setup).
  await confirmPhoto(request, pa.token, pa.profileId, placeholderPng("lipid-panel-2025-08-29"));

  await signInAs(page, pa, "Pa");
  await todayReady(page);

  await page.getByTestId("report-input").setInputFiles({
    name: "lab-report-not-his.png",
    mimeType: "image/png",
    buffer: placeholderPng("lab-report-not-his-2026-09-20"),
  });
  await page.getByTestId("report-send").click();

  // The one plain question, an orb beside it, never a stack of chips: a lead line naming
  // what the paper itself said, then the question, then exactly three choices.
  const clarify = page.getByTestId("reading-result-whose");
  await expect(clarify).toBeVisible();
  const lead = page.getByTestId("clarify-lead").locator(".sr-only");
  await expect(lead).toContainText("Demo Patient Name");
  await expect(lead).toContainText("1986");
  await expect(page.getByTestId("clarify-question").locator(".sr-only")).toHaveText("Is it yours?");
  await expect(page.getByTestId("clarify-mine")).toBeVisible();
  await expect(page.getByTestId("clarify-someone_elses")).toContainText("someone else's");
  await expect(page.getByTestId("clarify-not_sure")).toContainText("not sure");

  // Nothing is filed while it stands: nothing below the question is drawn at all — no
  // headline, no report rows, no "See the full table".
  await expect(page.getByTestId("reading-headline")).toHaveCount(0);
  await expect(page.getByTestId("see-report")).toHaveCount(0);

  await page.getByTestId("clarify-someone_elses").click();

  // "Someone else's" keeps the paper out of the record, with a calm line — never an error,
  // never a claim that something broke.
  await expect(page.getByTestId("clarify-lead")).toHaveCount(0);
});

test("answering mine lets the paper go on to the ordinary report table", async ({ page, request }) => {
  const pa = await openOwn(request, "Pa");
  await confirmPhoto(request, pa.token, pa.profileId, placeholderPng("lipid-panel-2025-08-29"));
  await signInAs(page, pa, "Pa");
  await todayReady(page);

  await page.getByTestId("report-input").setInputFiles({
    name: "lab-report-not-his.png",
    mimeType: "image/png",
    buffer: placeholderPng("lab-report-not-his-2026-09-20"),
  });
  await page.getByTestId("report-send").click();
  await expect(page.getByTestId("clarify-mine")).toBeVisible();
  await page.getByTestId("clarify-mine").click();

  // The question is answered: the ordinary preview draws now, same as any other paper.
  await expect(page.getByTestId("reading-headline")).toBeVisible();
  await expect(page.getByTestId("see-report")).toBeVisible();
});
