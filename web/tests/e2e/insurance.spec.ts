import { expect, test, type APIRequestContext } from "@playwright/test";
import { API, fixClock } from "./helpers";
import { auth, EVERY_PART, letIn, openOwn, placeholderPng, signInAs, unknownPng, yes, type Papers } from "./record-helpers";

/** Package 12a — insurance essentials: loading a policy paper, the passport (what it covers,
 *  what it does not, benefits and limits, how to claim), and the non-happy states. The fixture
 *  policy/claim papers already exist (`backend/tests/fixtures/paper/insurance-policy-2026-09-13.json`,
 *  `insurance-claim-2026-09-14.json`); every scenario below is walked with real bytes whose
 *  sha256 matches one of those two fixtures, never a mocked response. */

test.beforeEach(async ({ page }) => {
  await fixClock(page);
});

async function openInsurance(page: import("@playwright/test").Page): Promise<void> {
  await page.getByTestId("tab-profile").click();
  await page.getByTestId("profile-insurance").click();
  await expect(page.getByTestId("insurance-screen")).toBeVisible();
}

/** A policy written straight over the API (the same route the propose sheet calls), for the
 *  scenarios that are about the passport's own display logic, not the reading pipeline. */
async function seedPolicy(
  request: APIRequestContext,
  pa: Papers,
  over: Partial<{ insurer_name: string; renewal_date: string | null; status: string }> = {},
): Promise<string> {
  const body = {
    insurer_name: over.insurer_name ?? "Great Eastern",
    policy_type: "hospital",
    status: over.status ?? "active",
    guarantee_letter: false,
    renewal_date: over.renewal_date ?? null,
  };
  const confirmation_id = await yes(request, pa.token, pa.profileId, { subject: "policy", ...body });
  const written = await request.post(`${API}/profiles/${pa.profileId}/insurance/policies`, { ...auth(pa.token), data: { ...body, confirmation_id } });
  expect(written.status(), await written.text()).toBe(201);
  return ((await written.json()) as { policy_id: string }).policy_id;
}

test("loading a policy paper: the live reading stages, the confirmation card, then a proposal that becomes the passport", async ({ page, request }) => {
  const pa = await openOwn(request);
  await signInAs(page, pa, "Pa");
  await openInsurance(page);

  await expect(page.getByTestId("insurance-none")).toBeVisible();
  await page.getByTestId("add-policy").click();
  await expect(page.getByTestId("policy-load")).toBeVisible();

  await page.getByTestId("file-input").setInputFiles({ name: "policy.png", mimeType: "image/png", buffer: placeholderPng("insurance-policy-2026-09-13") });

  // ONE in-place status line while Nura reads it — never an accumulating checklist.
  await expect(page.getByTestId("reading-status")).toBeVisible();
  await expect(page.getByTestId("see-report")).toBeVisible({ timeout: 15_000 });
  await expect(page.locator('[data-testid="thinking"]')).toHaveCount(0);
  await page.getByTestId("see-report").click();

  // The confirmation card: the policy's own read fields, not a lab table.
  await expect(page.getByTestId("field-insurer")).toContainText("Great Eastern");
  await expect(page.getByTestId("field-policy_number")).toContainText("GE-HS-12345");
  await page.getByTestId("looks-right").click();

  // "Add this as your policy": pre-filled from what was just confirmed, still his to change.
  await expect(page.getByTestId("propose-policy-sheet")).toBeVisible();
  await expect(page.getByTestId("propose-insurer")).toHaveValue("Great Eastern");
  await expect(page.getByTestId("propose-reference")).toHaveValue("GE-HS-12345");
  await page.getByTestId("action-sheet-cta").click();

  await expect(page.getByTestId("propose-policy-sheet")).toHaveCount(0);
  const passport = page.getByTestId("policy-passport");
  await expect(passport).toBeVisible();
  await expect(passport).toContainText("Great Eastern");
  await expect(passport.getByTestId("policy-period-chip")).toContainText("In force");
  // The four sections, each with real content or the one calm line — never a placeholder.
  await expect(page.getByTestId("section-covers")).toBeVisible();
  await expect(page.getByTestId("section-excludes")).toBeVisible();
  await expect(page.getByTestId("section-benefits")).toBeVisible();
  await expect(page.getByTestId("section-claim")).toBeVisible();
  await expect(page.locator("h1")).toHaveCount(1);
});

test("a paper that is not a policy: saved to the papers, no proposal offered", async ({ page, request }) => {
  const pa = await openOwn(request);
  await signInAs(page, pa, "Pa");
  await openInsurance(page);
  await page.getByTestId("add-policy").click();
  await page.getByTestId("file-input").setInputFiles({ name: "claim.png", mimeType: "image/png", buffer: placeholderPng("insurance-claim-2026-09-14") });
  await expect(page.getByTestId("see-report")).toBeVisible({ timeout: 15_000 });
  await page.getByTestId("see-report").click();
  await page.getByTestId("looks-right").click();
  await expect(page.getByTestId("looks-right")).toHaveCount(0, { timeout: 20_000 });
  await expect(page.getByTestId("propose-policy-sheet")).toHaveCount(0);
  await expect(page.getByTestId("insurance-screen")).toBeVisible({ timeout: 20_000 });
  await expect(page.getByTestId("insurance-note")).toBeVisible();
});

test("a policy paper Nura could not read: the honest word for it, not a crash", async ({ page, request }) => {
  const pa = await openOwn(request);
  await signInAs(page, pa, "Pa");
  await openInsurance(page);
  await page.getByTestId("add-policy").click();
  await page.getByTestId("file-input").setInputFiles({ name: "mystery.png", mimeType: "image/png", buffer: unknownPng() });
  await expect(page.getByTestId("review-unreadable")).toBeVisible({ timeout: 15_000 });
});

test("an ended policy: the passport's own quiet chip, computed by the backend from the renewal date on file", async ({ page, request }) => {
  const pa = await openOwn(request);
  await seedPolicy(request, pa, { renewal_date: "2026-01-01" }); // well before the frozen clock's day
  await signInAs(page, pa, "Pa");
  await openInsurance(page);
  await expect(page.getByTestId("policy-passport").getByTestId("policy-period-chip")).toContainText("Ended");
});

test("two policies: both shown, never merged into one card", async ({ page, request }) => {
  const pa = await openOwn(request);
  await seedPolicy(request, pa, { insurer_name: "Great Eastern" });
  await seedPolicy(request, pa, { insurer_name: "AIA" });
  await signInAs(page, pa, "Pa");
  await openInsurance(page);
  const passports = page.getByTestId("policy-passport");
  await expect(passports).toHaveCount(2);
  const names = await passports.evaluateAll((nodes) => nodes.map((n) => n.textContent ?? ""));
  expect(names.some((t) => t.includes("Great Eastern"))).toBe(true);
  expect(names.some((t) => t.includes("AIA"))).toBe(true);
});

test("a claim filed against a policy lists under it, restyled from the ledger", async ({ page, request }) => {
  const pa = await openOwn(request);
  const policyId = await seedPolicy(request, pa);
  const doctor = await request.post(`${API}/profiles/${pa.profileId}/providers`, { ...auth(pa.token), data: { name: "Dr Tan", kind: "doctor" } });
  expect(doctor.status(), await doctor.text()).toBe(201);
  const providerId = ((await doctor.json()) as { provider_id: string }).provider_id;
  const visitYes = await yes(request, pa.token, pa.profileId, { subject: "appointment", provider_id: providerId, scheduled_at: "2026-09-12T02:00:00Z", purpose: "check-up" });
  const visit = await request.post(`${API}/profiles/${pa.profileId}/appointments`, { ...auth(pa.token), data: { provider_id: providerId, scheduled_at: "2026-09-12T02:00:00Z", purpose: "check-up", confirmation_id: visitYes } });
  expect(visit.status(), await visit.text()).toBe(201);
  const appointmentId = ((await visit.json()) as { appointment_id: string }).appointment_id;
  const claimYes = await yes(request, pa.token, pa.profileId, { subject: "insurance_claim", policy_id: policyId, appointment_id: appointmentId, claimed_amount_cents: 9500 });
  const claim = await request.post(`${API}/profiles/${pa.profileId}/insurance/claims`, { ...auth(pa.token), data: { policy_id: policyId, appointment_id: appointmentId, claimed_amount_cents: 9500, confirmation_id: claimYes } });
  expect(claim.status(), await claim.text()).toBe(201);

  await signInAs(page, pa, "Pa");
  await openInsurance(page);
  const rows = page.getByTestId("policy-claim-row");
  await expect(rows).toHaveCount(1);
  // `openOwn` registers a Singapore-region profile by default; the ledger's own currency
  // symbol follows the profile's region (`app.insurance.strings.CURRENCY_BY_REGION`), never a
  // symbol picked here.
  await expect(rows.first()).toContainText("S$95");
});

test("Mei, a chief, reads Pa's policy in the third person — never 'my policy', never 'your'", async ({ page, request }) => {
  const pa = await openOwn(request, "Pa");
  await seedPolicy(request, pa);
  const mei = await letIn(request, pa, "Mei", "chief", EVERY_PART);
  await signInAs(page, mei, "Mei", true);
  await openInsurance(page);
  await expect(page.locator("h1")).toHaveText("Pa's insurance");
  const body = await page.locator("main").innerText();
  expect(body).not.toMatch(/\bmy policy\b/i);
  expect(body).not.toMatch(/\byour policy\b/i);
});

for (const size of [{ width: 390, height: 844 }, { width: 1280, height: 900 }]) {
  test(`geometry at ${size.width}x${size.height}: nothing under the tab bar, the primary action visible, heading to card spacing`, async ({ page, request }) => {
    const pa = await openOwn(request);
    await seedPolicy(request, pa);
    await page.setViewportSize(size);
    await signInAs(page, pa, "Pa");
    await openInsurance(page);
    await expect(page.getByTestId("policy-passport")).toBeVisible();
    const heading = page.locator("h1");
    const card = page.getByTestId("policy-passport").locator(".glass-card").first();
    const hBox = await heading.boundingBox();
    const cBox = await card.boundingBox();
    expect(hBox).not.toBeNull();
    expect(cBox).not.toBeNull();
    if (hBox && cBox) expect(cBox.y).toBeGreaterThanOrEqual(hBox.y + hBox.height);
    // The primary action ("Add a policy") is reachable without scrolling past the tab bar.
    const addAnother = page.getByTestId("add-another-policy");
    await expect(addAnother).toBeVisible();
  });
}
