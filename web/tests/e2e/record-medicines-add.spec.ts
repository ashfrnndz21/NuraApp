import { expect, test } from "@playwright/test";
import { API, fixClock, seedMedicine } from "./helpers";
import { auth, letIn, openOwn, openRecord, placeholderPng, signInAs } from "./record-helpers";

/** Add a medicine — by photo, by a class-only box (#302), or typed — and what happens on a
 *  duplicate (redesign package 11). `record-medicines.spec.ts` covers the baseline photo →
 *  confirm → check → add walk and the high-risk refusal; this covers what is new: the live
 *  reading trace ending in a real registry row, the which-statin question and its "I'm not
 *  sure" branch, typed entry with no photo at all, a duplicate add, and the medicines scope. */

interface Line {
  line_id: string;
  generic: string;
  strength: string;
  source: string;
}

test.beforeEach(async ({ page }) => {
  await fixClock(page);
});

test("add a medicine by photo (warfarin label): the live reading, the confirmation card, its real fields, and the strength safety check", async ({ page, request }) => {
  const pa = await openOwn(request);
  await signInAs(page, pa, "Pa");
  await openRecord(page);
  await page.getByTestId("record-medicines").click();
  await page.getByTestId("add-medicine").click();
  await expect(page.getByTestId("add-entry")).toBeVisible();

  await page.getByTestId("photo-input").setInputFiles({ name: "warfarin.png", mimeType: "image/png", buffer: placeholderPng("warfarin-label-2024-03-12") });

  // The confirmation card: the extracted fields, each real, none invented, its unit shown;
  // the doctor's name was read at low confidence on this fixture, so it carries "Check this one".
  const confirm = page.getByTestId("add-confirm");
  await expect(confirm).toBeVisible();
  await expect(page.getByTestId("add-confirm-row-name")).toContainText("Warfarin");
  await expect(page.getByTestId("add-confirm-row-strength")).toContainText("5");
  await expect(page.getByTestId("add-confirm-row-strength")).toContainText("mg");
  await expect(page.getByTestId("add-confirm-row-prescriber").getByTestId("add-check-this-one")).toBeVisible();

  // "Looks right" runs the label straight through the register's own check (redesign package
  // 11 does not bypass it): this fixture's own printed strength, 5 mg, is not the strength on
  // file for warfarin (3 mg — a high-risk generic, so a strength that does not match is never
  // silently taken), and the register's existing safety refusal is shown, not swallowed.
  await page.getByTestId("looks-right").click();
  await expect(page.getByTestId("notice")).toContainText("Nura found the medicine but not how strong it is.");
  await expect(page.getByTestId("add-check")).toHaveCount(0);

  // "Fix" opens the same typed form, prefilled with what was read; correcting the strength to
  // the one on file lets the check — and the add — go through.
  await page.getByTestId("add-fix").click();
  const strengthField = page.getByLabel("How strong it is");
  await expect(strengthField).toHaveValue("5 mg");
  await strengthField.fill("3 mg");
  await page.getByTestId("check-medicine").click();
  await expect(page.getByTestId("add-check")).toBeVisible();
  await expect(page.getByTestId("outcome")).toHaveText("This is a new medicine for your list.");
  await expect(page.getByTestId("no-interactions")).toBeVisible();

  await page.getByTestId("add-it").click();
  await expect(page.getByTestId("add-done")).toContainText("Added to your tablets.");
  await page.getByTestId("see-in-registry").click();

  const row = page.getByTestId("medicine-line").filter({ hasText: "Warfarin" }).first();
  await expect(row).toBeVisible();
  const [line] = (await (await request.get(`${API}/profiles/${pa.profileId}/medicines?language=en`, auth(pa.token))).json()) as Line[];
  expect(line!.generic).toBe("warfarin");
  await expect(row.getByTestId("source")).toContainText("label");
});

test("a box naming only a family of medicines (#302): the which-one question, picking a member, confirming it", async ({ page, request }) => {
  const pa = await openOwn(request);
  await signInAs(page, pa, "Pa");
  await openRecord(page);
  await page.getByTestId("record-medicines").click();
  await page.getByTestId("add-medicine").click();
  await page.getByTestId("photo-input").setInputFiles({ name: "statin.png", mimeType: "image/png", buffer: placeholderPng("statin-box-2026-09-19") });

  await expect(page.getByTestId("add-confirm")).toBeVisible();
  await expect(page.getByTestId("add-confirm-row-name")).toContainText("STATIN");
  await page.getByTestId("looks-right").click();

  // The which-one question: the register's own members, never a guess from the box's text.
  const which = page.getByTestId("add-which");
  await expect(which).toBeVisible();
  await expect(which).toContainText("Statin");
  await expect(which).toContainText("Which one is it?");
  await expect(page.getByTestId("which-atorvastatin")).toBeVisible();
  await expect(page.getByTestId("which-simvastatin")).toBeVisible();
  await expect(page.getByTestId("which-rosuvastatin")).toBeVisible();
  await expect(page.getByTestId("which-not-sure")).toBeVisible();

  await page.getByTestId("which-atorvastatin").click();
  await expect(page.getByTestId("add-check")).toBeVisible();
  await expect(page.getByTestId("chemical")).toContainText("atorvastatin");

  await page.getByTestId("add-it").click();
  await expect(page.getByTestId("add-done")).toBeVisible();
  const lines = (await (await request.get(`${API}/profiles/${pa.profileId}/medicines?language=en`, auth(pa.token))).json()) as Line[];
  expect(lines.map((each) => each.generic)).toEqual(["atorvastatin"]);
});

test("\"I'm not sure\" (#302): nothing is registered", async ({ page, request }) => {
  const pa = await openOwn(request);
  await signInAs(page, pa, "Pa");
  await openRecord(page);
  await page.getByTestId("record-medicines").click();
  await page.getByTestId("add-medicine").click();
  await page.getByTestId("photo-input").setInputFiles({ name: "statin.png", mimeType: "image/png", buffer: placeholderPng("statin-box-2026-09-19") });
  await page.getByTestId("looks-right").click();
  await page.getByTestId("which-not-sure").click();

  await expect(page.getByTestId("add-not-sure")).toContainText("Nothing is added until you say which one it is.");
  const lines = (await (await request.get(`${API}/profiles/${pa.profileId}/medicines`, auth(pa.token))).json()) as Line[];
  expect(lines).toEqual([]);
});

test("typed entry: no photo at all, its own source, and the register still screens it", async ({ page, request }) => {
  const pa = await openOwn(request);
  await signInAs(page, pa, "Pa");
  await openRecord(page);
  await page.getByTestId("record-medicines").click();
  await page.getByTestId("add-medicine").click();
  await page.getByTestId("add-type-it").click();

  const labelStep = page.getByTestId("add-label");
  await expect(labelStep).toBeVisible();
  await page.getByLabel("The name on the label").fill("fish oil");
  await page.getByLabel("How strong it is").fill("1000 mg");
  await page.getByLabel("The form (tablet, capsule, inhaler…)").fill("capsule");
  await page.getByLabel("How to take it").fill("1 cap OD");
  await page.getByLabel("How many are in the box").fill("30");
  await page.getByTestId("check-medicine").click();

  await expect(page.getByTestId("add-check")).toBeVisible();
  await page.getByTestId("add-it").click();
  await expect(page.getByTestId("add-done")).toBeVisible();

  const [line] = (await (await request.get(`${API}/profiles/${pa.profileId}/medicines?language=en`, auth(pa.token))).json()) as Line[];
  expect(line!.generic).toBe("fish oil");
  // Typed, not a label: its own source line, never the label's wording.
  expect(line!.source).toContain("typed");
});

test("adding the same medicine twice: put to him as a question, not a bare refusal", async ({ page, request }) => {
  const pa = await openOwn(request);
  await seedMedicine(request, pa.token, pa.profileId, { generic: "amlodipine", strength: "5 mg", dose_text: "1 tab OD", quantity: 30 });
  await signInAs(page, pa, "Pa");
  await openRecord(page);
  await page.getByTestId("record-medicines").click();
  await page.getByTestId("add-medicine").click();
  await page.getByTestId("add-type-it").click();
  await page.getByLabel("The name on the label").fill("amlodipine");
  await page.getByLabel("How strong it is").fill("5 mg");
  await page.getByLabel("How to take it").fill("1 tab OD");
  await page.getByTestId("check-medicine").click();

  await expect(page.getByTestId("add-duplicate")).toContainText("You already have this.");
  await expect(page.getByTestId("add-duplicate")).toContainText("Is this a new box of the same one?");
  await expect(page.getByTestId("add-it")).toHaveCount(0);

  await page.getByTestId("duplicate-no").click();
  await expect(page.getByTestId("record-medicines")).toBeVisible();
  const lines = (await (await request.get(`${API}/profiles/${pa.profileId}/medicines`, auth(pa.token))).json()) as Line[];
  expect(lines).toHaveLength(1);
});

test("a key with no medicines scope sees a refusal, never the list", async ({ page, request }) => {
  const pa = await openOwn(request);
  await seedMedicine(request, pa.token, pa.profileId, { generic: "amlodipine", strength: "5 mg", dose_text: "1 tab OD", quantity: 30 });
  const kit = await letIn(request, pa, "Kit", "viewer", ["readings"]);
  await signInAs(page, kit, "Kit", true);
  await page.getByTestId("tab-health").click();
  await page.getByTestId("health-record-hub").click();
  const row = page.getByTestId("record-medicines");
  // A key that does not hold the medicines scope is never offered the entry at all
  // (`hubEntries`): the block is not there for her to open, never a page with rows she
  // should not see.
  await expect(row).toHaveCount(0);
});

test("Mei's wording: \"Pa's tablets\", never \"your tablets\", on her key", async ({ page, request }) => {
  const pa = await openOwn(request);
  await seedMedicine(request, pa.token, pa.profileId, { generic: "amlodipine", strength: "5 mg", dose_text: "1 tab OD", quantity: 30 });
  const mei = await letIn(request, pa, "Mei", "chief", ["medicines"]);
  await signInAs(page, mei, "Mei", true);
  await page.getByTestId("tab-health").click();
  await page.getByTestId("health-record-hub").click();
  await page.getByTestId("record-medicines").click();
  await expect(page.getByTestId("record-medicines")).toContainText("Pa");
  await expect(page.getByTestId("record-medicines").locator("h1")).not.toContainText("Your");
});
