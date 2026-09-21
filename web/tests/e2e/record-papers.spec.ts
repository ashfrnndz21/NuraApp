import { expect, test } from "@playwright/test";
import { hubEntries } from "../../src/record/model";
import { API, fixClock, openMe, seedMedicine, TAB_SET } from "./helpers";
import { auth, EVERY_PART, letIn, LOOKS, lookAs, openOwn, openRecord, placeholderPng, readable, signInAs, yes } from "./record-helpers";

/** Checkpoint 25, his papers (W5): E02-04 a paper forwarded on WhatsApp confirmed on the web,
 *  E02-08 a blood pressure read off the machine's screen with no typing, and the Record's
 *  first screen. (The family's papers, E12-09, are walked by W6's Family specs.) */

test.beforeEach(async ({ page }) => {
  await fixClock(page);
});

test("the Record's first screen: his medicines, his papers and his day first; a helper sees only what her key opens", async ({ page, request }) => {
  const pa = await openOwn(request);
  const siti = await letIn(request, pa, "Siti", "helper", ["medicines"]);

  await signInAs(page, pa, "Pa");
  await expect(page.getByTestId("tab-health")).toHaveText("Health");
  expect(await page.locator("nav.tabbar button").allTextContents()).toEqual([...TAB_SET]);
  await openRecord(page);
  await expect(page.locator("h1")).toHaveText("Your papers");
  const his = await page.getByTestId("record-entries").locator("button").evaluateAll((buttons) => buttons.map((each) => each.getAttribute("data-testid")));
  expect(his.slice(0, 3)).toEqual(["record-medicines", "record-papers", "record-routine"]);
  await readable(page, "patient");

  await openMe(page);
  await page.getByTestId("sign-out").click();
  // Signing out finishes before the next person signs in: nothing of his papers stays behind.
  await expect(page.getByLabel("Your phone number")).toBeVisible();
  await signInAs(page, siti, "Siti", true);
  await openRecord(page);
  await expect(page.locator("h1")).toHaveText("Pa's papers");
  const hers = await page.getByTestId("record-entries").locator("button").evaluateAll((buttons) => buttons.map((each) => each.getAttribute("data-testid")));
  expect(hers).toEqual(["record-changes", "record-medicines", "record-routine"]);
  await readable(page, "caregiver");
});

test("on a demo deployment the banner is on every Record screen, and still nothing is drawn over a line", async ({ page, request }) => {
  // ADR 0008: a demo shows its banner first on every screen. The backend's answer is set to
  // a demo for this walk only; everything else is the dev run's.
  await page.route("**/api/deployment", (route) => route.fulfill({ json: { region: "SG", demo: true } }));
  const pa = await openOwn(request);
  await seedMedicine(request, pa.token, pa.profileId, { generic: "amlodipine", strength: "5 mg", dose_text: "1 tab OD", quantity: 5 });
  await signInAs(page, pa, "Pa");
  await openRecord(page);
  await expect(page.getByTestId("demo-banner")).toBeVisible();
  await readable(page, "patient");
  for (const entry of ["medicines", "papers", "routine", "timeline", "trends", "providers", "changes"]) {
    await page.getByTestId(`record-${entry}`).click();
    await expect(page.getByTestId("demo-banner")).toBeVisible();
    await readable(page, "patient");
    await page.getByTestId("record-back").click();
  }
});


for (const look of LOOKS) {
  test(`a closing account (${look}): every Record screen says the backend's AccountClosing sentence, and none of his papers`, async ({ page, request }) => {
    const pa = await openOwn(request);
    await seedMedicine(request, pa.token, pa.profileId, { generic: "amlodipine", strength: "5 mg", dose_text: "1 tab OD", quantity: 5 });
    const mei = await letIn(request, pa, "Mei", "chief", EVERY_PART);
    // Pa reads his papers in his density; Mei, his chief, in hers.
    const reader = look === "patient" ? pa : mei;
    await signInAs(page, reader, look === "patient" ? "Pa" : "Mei", look === "caregiver");
    await lookAs(page, look);
    const entries = await page.getByTestId("record-entries").locator("button").evaluateAll((buttons) => buttons.map((each) => each.getAttribute("data-testid")!));
    // Every entry the screen registry (record/model.ts) opens for this density on every
    // part: the registry names the Record's screens, not a count typed here by hand.
    const registered = hubEntries(look === "patient" ? "patient" : "caregiver", EVERY_PART);
    expect(entries).toEqual(registered.map((entry) => `record-${entry}`));

    // Pa closes his account (#151) on his yes while the Record is open: every key and his own
    // reads are refused by name.
    const said = await yes(request, pa.token, pa.profileId, { subject: "close_account", language: "en" });
    const closed = await request.post(`${API}/profiles/${pa.profileId}/closure`, { ...auth(pa.token), data: { confirmation_id: said, language: "en" } });
    expect(closed.status(), await closed.text()).toBe(201);
    const refused = await request.get(`${API}/profiles/${pa.profileId}/medicines`, auth(reader.token));
    expect(refused.status()).toBe(403);
    expect(await refused.json()).toEqual({ refusal: "AccountClosing" });

    // Each Record screen says the catalogue's sentence for that class, and nothing of his papers.
    for (const entry of entries) {
      await page.getByTestId(entry).click();
      if (entry === "record-trends") await page.getByTestId("analyte-total_cholesterol").click();
      await expect(page.getByTestId("notice").first()).toHaveText("Nura has stopped keeping these papers.");
      await expect(page.getByTestId("medicine-line")).toHaveCount(0);
      await expect(page.locator("main")).not.toContainText(/AccountClosing|amlodipine|blood pressure tablet/);
      await readable(page, look);
      await page.getByTestId("record-back").click();
      if (entry === "record-trends") await page.getByTestId("record-back").click();
      await expect(page.getByTestId("record-hub")).toBeVisible();
    }
  });
}

for (const look of LOOKS) {
  test(`a paper forwarded on WhatsApp is confirmed on the web (${look})`, async ({ page, request }) => {
    const pa = await openOwn(request);
    const mei = await letIn(request, pa, "Mei", "chief", EVERY_PART);
    const agreed = await request.post(`${API}/profiles/${pa.profileId}/consents/whatsapp`, { ...auth(pa.token), data: { language: "en", captured_via: "app" } });
    expect(agreed.status(), await agreed.text()).toBe(201);
    const forwarded = await request.post(`${API}/dev/whatsapp/inbound`, { data: { from_e164: mei.phone, media_id: "lipid-panel-photo", content_type: "image/png" } });
    expect(forwarded.ok(), await forwarded.text()).toBe(true);
    const handled = (await forwarded.json()) as { outcome: string; review_card_id: string | null };
    expect(handled.outcome).toBe("document");

    await signInAs(page, pa, "Pa");
    await lookAs(page, look);
    await page.getByTestId("record-papers").click();
    const waiting = page.getByTestId("waiting-paper");
    await expect(waiting).toHaveCount(1);
    await expect(waiting).toContainText("Blood test");
    await expect(waiting).toHaveAttribute("data-card-id", handled.review_card_id!);
    await readable(page, look);

    await waiting.click();
    await expect(page.locator(`main[data-card-id="${handled.review_card_id}"]`)).toBeVisible();
    await readable(page, look);
    await page.getByTestId("looks-right").click();
    await expect(page.getByTestId("record-note")).toHaveText("Nura wrote it down.");
    // Confirmed, not gone: it is now a checked paper in the same list (library part B #2).
    await expect(page.getByTestId("waiting-paper")).toHaveCount(0);
    const checked = page.getByTestId("checked-paper");
    await expect(checked).toHaveCount(1);
    await expect(checked).toHaveAttribute("data-card-id", handled.review_card_id!);
    const card = (await (await request.get(`${API}/profiles/${pa.profileId}/review-cards/${handled.review_card_id}`, auth(pa.token))).json()) as { confirmed_at: string | null };
    expect(card.confirmed_at).not.toBeNull();

    // Reopened, it is read-only: "You checked this on", and nothing to correct.
    await checked.click();
    await expect(page.getByTestId("report-checked-on")).toBeVisible();
    await expect(page.getByTestId("looks-right")).toHaveCount(0);
    await readable(page, look);
  });

  test(`a blood pressure read off the machine's screen, confirmed with no typing (${look})`, async ({ page, request }) => {
    const pa = await openOwn(request);
    await signInAs(page, pa, "Pa");
    await lookAs(page, look);
    // His Today has the blood pressure card; hers is under Visits, with getting ready for the
    // next visit (D1: one tab set, so the same tab for both).
    if (look === "patient") {
      await page.getByTestId("tab-home").click();
      await page.getByTestId("write-reading").click();
    } else {
      await page.getByTestId("tab-services").click();
      await page.getByTestId("plan-reading").click();
    }
    await expect(page.getByTestId("reading-photo")).toBeVisible();
    await readable(page, look);
    await page.getByTestId("photo-input").setInputFiles({ name: "cuff.png", mimeType: "image/png", buffer: placeholderPng("bp-cuff-2026-09-14") });
    await expect(page.getByTestId("review-card")).toContainText("Machine screen");
    await expect(page.getByTestId("field-systolic")).toContainText("138");
    await expect(page.getByTestId("field-diastolic")).toContainText("84");
    await readable(page, look);
    await page.getByTestId("looks-right").click();
    // Back where the reading was begun from: his Today with its blood pressure card, her Home (D1).
    await expect(page.getByTestId(look === "patient" ? "reading-prompt" : "home-screen")).toBeVisible();
    const facts = (await (await request.get(`${API}/profiles/${pa.profileId}/facts?subject=blood_pressure`, auth(pa.token))).json()) as { value: { systolic?: number; diastolic?: number } }[];
    expect(facts.some((fact) => fact.value.systolic === 138 && fact.value.diastolic === 84)).toBe(true);
  });
}
