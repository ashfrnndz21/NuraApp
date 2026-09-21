import { mkdirSync } from "node:fs";
import { expect, test, type APIRequestContext, type Page } from "@playwright/test";
import { API, apiToken, freshPhone, seedFeed, signInThroughTheApp, todayReady } from "../e2e/helpers";

/** W2 (natural clarifying questions): screen captures of the real app — real backend words,
 *  streamed for real, never a faked delay inside the app itself.
 *
 *  Unlike `cp4AskShots.spec.ts`, this does NOT sign in against the shared demo deployment
 *  (`NURA_DEMO_SEED=1`, "Try it as Pa"): the demo seed carries no confirmed lab report at all
 *  today (`backend/app/demo_seed.py`), so the paper-kind clarifying question — the one with
 *  real chips to show — could never fire there without changing shared demo data every other
 *  builder's own captures depend on. Instead this seeds its own fresh Pa through the real API
 *  (`seedFeed` + two confirmed lab reports, the same upload-and-confirm flow `ask-clarify.
 *  spec.ts` uses), then signs in through the Welcome screen exactly as the demo captures do.
 *  Everything on screen past that point is the real, running app.
 *
 *  Not a gate — `npx playwright test -c playwright.visual.config.ts tests/visual/
 *  cp4AskClarifyShots.spec.ts` writes pictures for a person to look at, into
 *  `NURA_ASK_CLARIFY_SHOTS` (default: this checkpoint's own folder under the scratchpad). */

const OUT = process.env.NURA_ASK_CLARIFY_SHOTS ?? "/private/tmp/claude-501/-Users-ashleyfernandez-SingleIDContext/e8f60261-760e-4178-a18b-74e3888c414c/scratchpad/shots/cp4-ask-clarify";
mkdirSync(OUT, { recursive: true });

test.use({ actionTimeout: 20_000 });

const PNG = Buffer.from([0x89, 0x50, 0x4e, 0x47, 0x0d, 0x0a, 0x1a, 0x0a]);

/** See `ask-clarify.spec.ts`'s own longer note: a confirmed review card only shows up in
 *  Ask's corpus of papers once it is HUNG off an open episode, so `episode_id` must ride both
 *  the mint and the confirm. */
async function seedConfirmedLabReport(request: APIRequestContext, token: string, profileId: string, episodeId: string, fixture: string, capturedAt: string): Promise<void> {
  const headers = { Authorization: `Bearer ${token}` };
  const bytes = Buffer.concat([PNG, Buffer.from(`nura-paper-placeholder:${fixture}\n`)]);
  const photo = await request.post(`${API}/profiles/${profileId}/photos`, {
    headers,
    data: { data: bytes.toString("base64"), content_type: "image/png", captured_at: capturedAt },
  });
  if (photo.status() !== 201) throw new Error(`photo ${fixture}: ${photo.status()} ${await photo.text()}`);
  const card = (await photo.json()) as { card_id: string; fields: { field_id: string; attribute: string }[] };
  const decisions = card.fields.map((field) => ({ field_id: field.field_id, decision: "confirmed" }));
  const minted = await request.post(`${API}/profiles/${profileId}/confirmations`, {
    headers,
    data: { subject: "review_card", card_id: card.card_id, decisions, episode_id: episodeId },
  });
  if (minted.status() !== 201) throw new Error(`mint ${fixture}: ${minted.status()} ${await minted.text()}`);
  const confirmation_id = ((await minted.json()) as { confirmation_id: string }).confirmation_id;
  const confirmed = await request.post(`${API}/profiles/${profileId}/review-cards/${card.card_id}/confirm`, {
    headers,
    data: { decisions, confirmation_id, episode_id: episodeId },
  });
  if (!confirmed.ok()) throw new Error(`confirm ${fixture}: ${confirmed.status()} ${await confirmed.text()}`);
}

async function seedTwoBloodTests(request: APIRequestContext, token: string, profileId: string): Promise<void> {
  const headers = { Authorization: `Bearer ${token}` };
  const opened = await request.post(`${API}/profiles/${profileId}/episodes`, { headers, data: { kind: "other", label: "check-up" } });
  if (opened.status() !== 201) throw new Error(`episode: ${opened.status()} ${await opened.text()}`);
  const episodeId = ((await opened.json()) as { episode_id: string }).episode_id;
  await seedConfirmedLabReport(request, token, profileId, episodeId, "lipid-panel-2025-08-29", "2025-08-29T08:00:00Z");
  await seedConfirmedLabReport(request, token, profileId, episodeId, "lab-report-vitals-2026-09-10", "2026-09-10T08:00:00Z");
}

async function openAsk(page: Page): Promise<void> {
  await page.getByTestId("home-ask-open").click();
  await expect(page.getByTestId("ask-screen")).toBeVisible();
}

async function delayAskStream(page: Page, ms: number): Promise<void> {
  await page.route(/\/(ask|turns)\/stream$/, async (route) => {
    const response = await route.fetch();
    await new Promise((resolve) => setTimeout(resolve, ms));
    await route.fulfill({ response });
  });
}

async function askClarifyingQuestion(page: Page, question: string, prefix: string): Promise<void> {
  await delayAskStream(page, 900);
  await page.getByLabel("Your question").fill(question);
  const clicked = page.getByTestId("ask-send").click();
  await expect(page.getByTestId("ask-orb")).toBeVisible({ timeout: 5_000 });
  await page.evaluate(() => document.fonts.ready);
  await page.screenshot({ path: `${OUT}/${prefix}-question-streaming.png`, animations: "disabled" });

  await clicked;
  await expect(page.getByTestId("answer-lines").last()).toBeVisible({ timeout: 15_000 });
  await page.evaluate(() => document.fonts.ready);
  await page.unroute(/\/(ask|turns)\/stream$/);
}

test.describe("cp4 Ask Clarify at 390x844", () => {
  test.use({ viewport: { width: 390, height: 844 }, deviceScaleFactor: 1, isMobile: true, hasTouch: true });

  test("390x844: question streaming, chips shown, after tap, typed reply, Mei", async ({ page, request }) => {
    const pa = await seedFeed(request);
    await seedTwoBloodTests(request, pa.token, pa.profileId);
    await signInThroughTheApp(page, pa.phone, "Pa");
    await todayReady(page);
    await openAsk(page);

    await askClarifyingQuestion(page, "what about my blood test", "phone-paper");
    await page.screenshot({ path: `${OUT}/phone-chips-shown.png`, animations: "disabled" });

    const options = page.getByTestId("ask-clarify-options").getByRole("button");
    await expect(options).toHaveCount(2);
    await options.first().click();
    await expect(page.getByTestId("answer")).toBeVisible({ timeout: 15_000 });
    await page.evaluate(() => document.fonts.ready);
    await page.screenshot({ path: `${OUT}/phone-after-tap.png`, animations: "disabled" });

    // A cost question, then a typed reply instead of a tap (no chips to tap: free text).
    await askClarifyingQuestion(page, "how much will this cost", "phone-cost");
    await page.screenshot({ path: `${OUT}/phone-typed-reply-before.png`, animations: "disabled" });
    await page.getByLabel("Your question").fill("It is for a blood test");
    await page.getByTestId("ask-send").click();
    await expect(page.getByTestId("answer")).toBeVisible({ timeout: 15_000 });
    await page.evaluate(() => document.fonts.ready);
    await page.screenshot({ path: `${OUT}/phone-typed-reply-after.png`, animations: "disabled" });
  });
});

test.describe("cp4 Ask Clarify: Mei, 1280x900", () => {
  test.use({ viewport: { width: 1280, height: 900 }, deviceScaleFactor: 2 });

  test("1280x900: Mei's own wording, clipped to the phone frame", async ({ page, request }) => {
    const pa = await seedFeed(request);
    await seedTwoBloodTests(request, pa.token, pa.profileId);
    const mei = freshPhone("+659667");
    const scopes = ["medicines", "visits", "readings", "records", "emergency", "ask"];
    const headers = { Authorization: `Bearer ${pa.token}` };
    const agreed = await request.post(`${API}/profiles/${pa.profileId}/consents/sharing`, {
      headers,
      data: { holder_phone_e164: mei, holder_display_name: "Mei", scopes, role: "caregiver", window: "always", relationship: "daughter", language: "en", captured_via: "app" },
    });
    if (agreed.status() !== 201) throw new Error(`sharing: ${agreed.status()} ${await agreed.text()}`);
    const key = await request.post(`${API}/profiles/${pa.profileId}/keys`, { headers, data: { holder_phone_e164: mei, role: "caregiver", scopes } });
    if (key.status() !== 201) throw new Error(`key: ${key.status()} ${await key.text()}`);
    await apiToken(request, mei);
    await signInThroughTheApp(page, mei, "Mei");
    await page.getByTestId("door-key").click();
    await expect(page.locator("html")).toHaveAttribute("data-density", "caregiver");
    await todayReady(page);
    await openAsk(page);

    await askClarifyingQuestion(page, "what about his blood test", "wide-mei");
    await page.evaluate(() => document.fonts.ready);
    await page.locator("#phone-frame").screenshot({ path: `${OUT}/wide-mei-chips.png`, animations: "disabled" });
  });
});
