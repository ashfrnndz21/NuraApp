import { expect, test } from "@playwright/test";
import { API, fixClock, seedMedicine } from "./helpers";
import { auth, EVERY_PART, letIn, LOOKS, lookAs, LPA_PDF, openOwn, placeholderPng, readable, setUpOnLpa, signInAs, signUp } from "./record-helpers";
import { freshPhone } from "./helpers";

/** Checkpoint 25, his papers (W5): E02-04 a paper forwarded on WhatsApp confirmed on the web,
 *  E02-08 a blood pressure read off the machine's screen with no typing, E12-09 the lasting
 *  power of attorney kept and shown backing the stewardship; and the Record's first screen. */

test.beforeEach(async ({ page }) => {
  await fixClock(page);
});

test("the Record's first screen: his medicines, his papers and his day first; a helper sees only what her key opens", async ({ page, request }) => {
  const pa = await openOwn(request);
  const siti = await letIn(request, pa, "Siti", "helper", ["medicines"]);

  await signInAs(page, pa, "Pa");
  await expect(page.getByTestId("tab-record")).toHaveText("Papers");
  expect(await page.locator("nav.tabbar button").allTextContents()).toEqual(["Today", "Papers", "Me"]);
  await page.getByTestId("tab-record").click();
  await expect(page.locator("h1")).toHaveText("Your papers");
  const his = await page.getByTestId("record-entries").locator("button").evaluateAll((buttons) => buttons.map((each) => each.getAttribute("data-testid")));
  expect(his.slice(0, 3)).toEqual(["record-medicines", "record-papers", "record-routine"]);
  await readable(page, "patient");

  await page.getByTestId("tab-me").click();
  await page.getByTestId("sign-out").click();
  await signInAs(page, siti, "Siti", true);
  await page.getByTestId("tab-record").click();
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
  await page.getByTestId("tab-record").click();
  await expect(page.getByTestId("demo-banner")).toBeVisible();
  await readable(page, "patient");
  for (const entry of ["medicines", "papers", "routine", "timeline", "trends", "providers", "changes", "documents"]) {
    await page.getByTestId(`record-${entry}`).click();
    await expect(page.getByTestId("demo-banner")).toBeVisible();
    await readable(page, "patient");
    await page.getByTestId("record-back").click();
  }
});

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
    await expect(waiting).toContainText("This is a blood test.");
    await expect(waiting.locator(`[data-card-id="${handled.review_card_id}"]`)).toHaveCount(1);
    await readable(page, look);

    await waiting.getByTestId("open-paper").click();
    await expect(page.locator(`main[data-card-id="${handled.review_card_id}"]`)).toBeVisible();
    await readable(page, look);
    await page.getByTestId("looks-right").click();
    await expect(page.getByTestId("record-note")).toHaveText("Nura wrote it down.");
    await expect(page.getByTestId("no-papers")).toHaveText("No paper is waiting for your yes.");
    const card = (await (await request.get(`${API}/profiles/${pa.profileId}/review-cards/${handled.review_card_id}`, auth(pa.token))).json()) as { confirmed_at: string | null };
    expect(card.confirmed_at).not.toBeNull();
  });

  test(`a blood pressure read off the machine's screen, confirmed with no typing (${look})`, async ({ page, request }) => {
    const pa = await openOwn(request);
    await signInAs(page, pa, "Pa");
    await lookAs(page, look);
    await page.getByTestId("tab-today").click();
    await page.getByTestId("write-reading").click();
    await expect(page.getByTestId("reading-photo")).toBeVisible();
    await readable(page, look);
    await page.getByTestId("photo-input").setInputFiles({ name: "cuff.png", mimeType: "image/png", buffer: placeholderPng("bp-cuff-2026-09-14") });
    await expect(page.getByTestId("review-card")).toContainText("This is the screen of a machine.");
    await expect(page.locator('input[name="field-systolic"]')).toHaveValue("138");
    await expect(page.locator('input[name="field-diastolic"]')).toHaveValue("84");
    await readable(page, look);
    await page.getByTestId("looks-right").click();
    await expect(page.getByTestId("reading-prompt")).toBeVisible();
    const facts = (await (await request.get(`${API}/profiles/${pa.profileId}/facts?subject=blood_pressure`, auth(pa.token))).json()) as { value: { systolic?: number; diastolic?: number } }[];
    expect(facts.some((fact) => fact.value.systolic === 138 && fact.value.diastolic === 84)).toBe(true);
  });

  test(`the family's papers (${look}): the lasting power of attorney kept and shown backing the stewardship`, async ({ page, request }) => {
    const mei = await signUp(request, freshPhone("+659336"), "Mei");
    await setUpOnLpa(request, mei);
    await signInAs(page, mei, "Mei", true);
    await lookAs(page, look);
    await page.getByTestId("record-documents").click();
    await expect(page.getByTestId("no-documents")).toHaveText("Nura keeps no papers like this yet.");
    await readable(page, look);
    await page.getByTestId("tag-lpa").click();
    await page.getByTestId("file-input").setInputFiles({ name: "lpa.pdf", mimeType: "application/pdf", buffer: LPA_PDF });
    await expect(page.getByTestId("document-added")).toHaveText("Nura kept the paper.");
    const kept = page.getByTestId("document");
    await expect(kept.locator("h2")).toHaveText("Lasting power of attorney");
    await expect(kept).toContainText("Looking after these papers rests on it.");
    await readable(page, look);
  });
}
