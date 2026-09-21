import { mkdirSync } from "node:fs";
import { expect, test, type APIRequestContext, type Page } from "@playwright/test";
import { API, fixClock } from "../e2e/helpers";
import { auth, EVERY_PART, letIn, openOwn, placeholderPng, signInAs, yes, type Papers } from "../e2e/record-helpers";

/** Package 12a's own capture spec, not a gate — `npx playwright test -c playwright.visual.
 *  config.ts tests/visual/cp5InsuranceShots.spec.ts` writes pictures into
 *  `/private/tmp/claude-501/-Users-ashleyfernandez-SingleIDContext/e8f60261-760e-4178-a18b-74e3888c414c/scratchpad/shots/cp5-insurance/`
 *  for a person (and the operator's own review) to look at, against the real app and the real
 *  fixture extractor — never a synthetic mock of the screen itself. */

const OUT = "/private/tmp/claude-501/-Users-ashleyfernandez-SingleIDContext/e8f60261-760e-4178-a18b-74e3888c414c/scratchpad/shots/cp5-insurance";
mkdirSync(OUT, { recursive: true });

test.use({ actionTimeout: 20_000 });

const SIZES = [
  { name: "390x844", width: 390, height: 844, mobile: true },
  { name: "1280x900", width: 1280, height: 900, mobile: false },
] as const;
type Size = (typeof SIZES)[number];

async function phone(page: Page, size: Size): Promise<void> {
  await page.setViewportSize({ width: size.width, height: size.height });
}

async function snap(page: Page, size: Size, name: string): Promise<void> {
  await page.evaluate(() => document.fonts.ready);
  const clip = size.mobile ? page : page.locator(".phone-frame").first();
  await clip.screenshot({ path: `${OUT}/${name}-${size.name}.png`, animations: "disabled" });
}

async function openInsurance(page: Page): Promise<void> {
  await page.getByTestId("tab-profile").click();
  await page.getByTestId("profile-insurance").click();
  await expect(page.getByTestId("insurance-screen")).toBeVisible();
}

async function seedPolicy(
  request: APIRequestContext,
  pa: Papers,
  over: Partial<{
    insurer_name: string;
    renewal_date: string | null;
    ends_on: string | null;
    status: string;
    covers: string | null;
    coverage_items: { text: string; page: number | null }[];
  }> = {},
): Promise<string> {
  const body = {
    insurer_name: over.insurer_name ?? "Great Eastern",
    policy_type: "hospital",
    status: over.status ?? "active",
    guarantee_letter: false,
    renewal_date: over.renewal_date ?? null,
    ends_on: over.ends_on ?? null,
    covers: over.covers ?? null,
    covered: over.covers ? "Pa and Mum" : null,
    coverage_items: over.coverage_items ?? [],
  };
  const confirmation_id = await yes(request, pa.token, pa.profileId, { subject: "policy", ...body });
  const written = await request.post(`${API}/profiles/${pa.profileId}/insurance/policies`, { ...auth(pa.token), data: { ...body, confirmation_id } });
  expect(written.status(), await written.text()).toBe(201);
  return ((await written.json()) as { policy_id: string }).policy_id;
}

for (const size of SIZES) {
  test(`insurance passport, ${size.name}`, async ({ page, request, browser }) => {
    await fixClock(page);
    await phone(page, size);

    // 1. Empty: no policy on file yet.
    const paEmpty = await openOwn(request);
    await signInAs(page, paEmpty, "Pa");
    await openInsurance(page);
    await expect(page.getByTestId("insurance-none")).toBeVisible();
    await snap(page, size, "1-empty");

    // 2. Mid-reading: the thumbnail bubble and one in-place status line. The fixture reads
    // near-instantly, so the SSE response is held a little longer here — test tooling only,
    // nothing about the backend's own real stages is faked.
    await page.route(/\/photos\/stream$/, async (route) => {
      try {
        const response = await route.fetch();
        await new Promise((resolve) => setTimeout(resolve, 900));
        await route.fulfill({ response });
      } catch {
        // A second, overlapping call to the same route (a retried connection): let it through
        // rather than fail the whole capture over a held-response timing aid.
        await route.continue().catch(() => undefined);
      }
    });
    await page.getByTestId("add-policy").click();
    await page.getByTestId("file-input").setInputFiles({ name: "policy.png", mimeType: "image/png", buffer: placeholderPng("insurance-policy-2026-09-13") });
    await expect(page.getByTestId("reading-status")).toBeVisible({ timeout: 15_000 });
    await snap(page, size, "2-mid-reading");
    await page.unroute(/\/photos\/stream$/);

    // 3. The confirmation card: the policy's own read fields, not a lab table.
    await expect(page.getByTestId("see-report")).toBeVisible({ timeout: 15_000 });
    await page.getByTestId("see-report").click();
    await expect(page.getByTestId("field-insurer")).toBeVisible();
    await snap(page, size, "3-confirmation-card");
    await page.getByTestId("looks-right").click();
    await expect(page.getByTestId("propose-policy-sheet")).toBeVisible({ timeout: 20_000 });
    await page.getByTestId("action-sheet-cta").click();
    await expect(page.getByTestId("propose-policy-sheet")).toHaveCount(0, { timeout: 20_000 });

    // 4. The passport: the passport card and the four sections, top of the screen.
    const passport = page.getByTestId("policy-passport").first();
    await expect(passport).toBeVisible();
    await snap(page, size, "4-passport-top");

    // 5. Scrolled: the sections and the claims list, further down. The shell scrolls inside
    // `[data-testid=shell-scroll]`, not the page itself — the mouse must be over it first.
    const scroller = page.getByTestId("shell-scroll");
    const box = await scroller.boundingBox();
    if (box) await page.mouse.move(box.x + box.width / 2, box.y + box.height / 2);
    await page.mouse.wheel(0, 700);
    await page.waitForTimeout(200);
    await snap(page, size, "5-passport-scrolled");
    await page.mouse.wheel(0, -900);

    // 6. Ended policy: a second, separately-seeded person, so the fresh policy is never
    // confused with an ended one on the same profile.
    const paEnded = await openOwn(request, "Uncle Wong");
    await seedPolicy(request, paEnded, { renewal_date: "2026-01-01" });
    const endedCtx = await browser.newContext({ viewport: { width: size.width, height: size.height }, timezoneId: "Asia/Singapore" });
    const endedPage = await endedCtx.newPage();
    await fixClock(endedPage);
    await phone(endedPage, size);
    await signInAs(endedPage, paEnded, "Uncle Wong");
    await openInsurance(endedPage);
    await expect(endedPage.getByTestId("policy-passport")).toBeVisible();
    await snap(endedPage, size, "6-ended-policy");
    await endedCtx.close();

    // 7. Two policies: never merged into one card.
    const paTwo = await openOwn(request, "Auntie Lim");
    await seedPolicy(request, paTwo, { insurer_name: "Great Eastern" });
    await seedPolicy(request, paTwo, { insurer_name: "AIA" });
    const twoCtx = await browser.newContext({ viewport: { width: size.width, height: size.height }, timezoneId: "Asia/Singapore" });
    const twoPage = await twoCtx.newPage();
    await fixClock(twoPage);
    await phone(twoPage, size);
    await signInAs(twoPage, paTwo, "Auntie Lim");
    await openInsurance(twoPage);
    await expect(twoPage.getByTestId("policy-passport")).toHaveCount(2);
    await snap(twoPage, size, "7-two-policies");
    await twoCtx.close();

    // 8. Mei, a caregiver: "Pa's insurance", never the first person.
    const paMei = await openOwn(request, "Pa");
    await seedPolicy(request, paMei);
    const mei = await letIn(request, paMei, "Mei", "chief", EVERY_PART);
    const meiCtx = await browser.newContext({ viewport: { width: size.width, height: size.height }, timezoneId: "Asia/Singapore" });
    const meiPage = await meiCtx.newPage();
    await fixClock(meiPage);
    await phone(meiPage, size);
    await signInAs(meiPage, mei, "Mei", true);
    await openInsurance(meiPage);
    await expect(meiPage.locator("h1")).toHaveText("Pa's insurance");
    await expect(meiPage.getByTestId("policy-passport")).toBeVisible();
    await snap(meiPage, size, "8-mei-caregiver");
    await meiCtx.close();

    // 9. A policy loaded from paper, ends_on only (never renewal_date) — the reviewer's own
    // probe (independent review, fix round, item 1): a chip that once read "in force" forever.
    const paPaperEnded = await openOwn(request, "Uncle Tan");
    await seedPolicy(request, paPaperEnded, { renewal_date: null, ends_on: "2021-12-31" });
    const paperEndedCtx = await browser.newContext({ viewport: { width: size.width, height: size.height }, timezoneId: "Asia/Singapore" });
    const paperEndedPage = await paperEndedCtx.newPage();
    await fixClock(paperEndedPage);
    await phone(paperEndedPage, size);
    await signInAs(paperEndedPage, paPaperEnded, "Uncle Tan");
    await openInsurance(paperEndedPage);
    await expect(paperEndedPage.getByTestId("policy-passport")).toBeVisible();
    await snap(paperEndedPage, size, "9-ended-from-paper-date");
    await paperEndedCtx.close();

    // 10. A pre-existing typed policy: `covers` in his own words, no essentials at all — every
    // policy written before this package, or typed by hand (independent review, item 3).
    const paTyped = await openOwn(request, "Pa Typed");
    await seedPolicy(request, paTyped, { covers: "Hospital stays, up to $500 a day." });
    const typedCtx = await browser.newContext({ viewport: { width: size.width, height: size.height }, timezoneId: "Asia/Singapore" });
    const typedPage = await typedCtx.newPage();
    await fixClock(typedPage);
    await phone(typedPage, size);
    await signInAs(typedPage, paTyped, "Pa Typed");
    await openInsurance(typedPage);
    await expect(typedPage.getByTestId("policy-passport")).toBeVisible();
    await snap(typedPage, size, "10-pre-existing-typed-policy");
    await typedCtx.close();

    // 11. A list cut at 12: the silent-truncation notice (independent review, item 4).
    const paCut = await openOwn(request, "Pa Cut");
    await seedPolicy(request, paCut, {
      coverage_items: Array.from({ length: 15 }, (_, i) => ({ text: `Covered item number ${i + 1}`, page: 2 })),
    });
    const cutCtx = await browser.newContext({ viewport: { width: size.width, height: size.height }, timezoneId: "Asia/Singapore" });
    const cutPage = await cutCtx.newPage();
    await fixClock(cutPage);
    await phone(cutPage, size);
    await signInAs(cutPage, paCut, "Pa Cut");
    await openInsurance(cutPage);
    await expect(cutPage.getByTestId("policy-passport")).toBeVisible();
    await snap(cutPage, size, "11-essentials-list-cut");
    await cutCtx.close();
  });
}
