import { expect, test, type APIRequestContext, type Page } from "@playwright/test";
import { FROZEN_CLOCK } from "../../playwright.config";
import { API, apiToken, backendClock, fixClock, freshPhone, seedFeed, signInThroughTheApp, todayReady } from "./helpers";

/** Natural clarifying questions (W2): the rule-based asker's two deterministic cases, real
 *  through the app — never a stall, only when the question genuinely cannot be answered
 *  without a choice. */

const PNG = Buffer.from([0x89, 0x50, 0x4e, 0x47, 0x0d, 0x0a, 0x1a, 0x0a]);

test.beforeAll(async ({ request }) => {
  const backend = await backendClock(request);
  if (!backend.frozen || Date.parse(backend.now) !== Date.parse(FROZEN_CLOCK)) {
    throw new Error(`the backend's clock is not frozen at ${FROZEN_CLOCK} (it says ${JSON.stringify(backend)}): let Playwright start it, or start make dev with NURA_FROZEN_CLOCK`);
  }
});

test.beforeEach(async ({ page }) => {
  await fixClock(page);
});

async function openAsk(page: Page): Promise<void> {
  await page.getByTestId("home-ask-open").click();
  await expect(page.getByTestId("ask-screen")).toBeVisible();
}

async function ask(page: Page, question: string): Promise<void> {
  await page.getByLabel("Your question").fill(question);
  await page.getByTestId("ask-send").click();
}

/** A confirmed lab_report paper, HUNG off an open episode (E02 the review flow, E03-02 the
 *  attach) — a confirmed review card alone never shows up in Ask's own corpus of papers
 *  (`app.search.ask._corpus_stream`'s RECORDS branch only ever populates `corpus.papers` for
 *  an artefact `Attachment` names): a card confirmed WITH an open episode's id hangs off it
 *  under the same yes (`app.ingestion.review.confirm_review`'s own docstring,
 *  `attach_from_ingestion`), so this must pass `episode_id` through the mint and the confirm
 *  both, or the paper is invisible to the rule-based asker's paper-kind clarify (and to the
 *  ordinary "your blood test is in your papers" answer it would otherwise give). `fixture`
 *  names a JSON file under `backend/tests/fixtures/paper` the `FixtureExtractor` reads back by
 *  (the same upload-and-confirm shape `helpers.ts`'s own `seedWarfarinLabel` uses, minus the
 *  episode it never needed). */
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
  const opened = await request.post(`${API}/profiles/${profileId}/episodes`, {
    headers,
    data: { kind: "other", label: "check-up" },
  });
  if (opened.status() !== 201) throw new Error(`episode: ${opened.status()} ${await opened.text()}`);
  const episodeId = ((await opened.json()) as { episode_id: string }).episode_id;
  await seedConfirmedLabReport(request, token, profileId, episodeId, "lipid-panel-2025-08-29", "2025-08-29T08:00:00Z");
  await seedConfirmedLabReport(request, token, profileId, episodeId, "lab-report-vitals-2026-09-10", "2026-09-10T08:00:00Z");
}

/** Mei, granted a caregiver's key on Pa's profile and signed in (the same flow
 *  `feed.spec.ts`'s "the caregiver's list" test uses). */
async function addAndSignInMei(request: APIRequestContext, page: Page, pa: { phone: string; token: string; profileId: string }): Promise<void> {
  const mei = freshPhone("+659666");
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
}

test("two blood tests seeded: 'what about my blood test?' asks which one, tapping answers about the chosen one", async ({ page, request }) => {
  const pa = await seedFeed(request);
  await seedTwoBloodTests(request, pa.token, pa.profileId);
  await signInThroughTheApp(page, pa.phone, "Pa");
  await todayReady(page);
  await openAsk(page);

  await ask(page, "what about my blood test");
  await expect(page.getByTestId("answer-lines")).toBeVisible({ timeout: 15_000 });
  const questionLine = page.getByTestId("answer-line-text").first();
  await expect(questionLine).toContainText("blood test");
  const options = page.getByTestId("ask-clarify-options").getByRole("button");
  await expect(options).toHaveCount(2);
  const firstLabel = (await options.first().innerText()).trim();
  expect(firstLabel).toContain("blood test");

  await options.first().click();
  // The tapped chip's own label becomes his right-aligned bubble, the chips gone at once, a
  // fresh thinking line starts.
  await expect(page.getByTestId("ask-earlier-turns")).toBeVisible();
  await expect(page.getByTestId("ask-question")).toContainText(firstLabel);
  await expect(page.getByTestId("ask-clarify-options")).toHaveCount(0);
  await expect(page.getByTestId("answer")).toBeVisible({ timeout: 15_000 });
});

test("never two clarifying questions in a row: paper clarify, then a cost clarify, then a typed reply never re-asks", async ({ page, request }) => {
  test.slow(); // four real turns, two with a photo upload and confirm each — genuinely heavier than the rest of this file.
  const pa = await seedFeed(request);
  await seedTwoBloodTests(request, pa.token, pa.profileId);
  await signInThroughTheApp(page, pa.phone, "Pa");
  await todayReady(page);
  await openAsk(page);

  // Turn A: the paper-kind clarify fires, with real chips.
  await ask(page, "what about my blood test");
  const paperOptions = page.getByTestId("ask-clarify-options").getByRole("button");
  await expect(paperOptions).toHaveCount(2, { timeout: 15_000 });
  await paperOptions.first().click();
  await expect(page.getByTestId("answer")).toBeVisible({ timeout: 15_000 });

  // Turn C: a cost question, free text, no chips.
  await ask(page, "how much will this cost");
  await expect(page.getByTestId("answer-lines").last()).toBeVisible({ timeout: 15_000 });
  await expect(page.getByTestId("answer-line-text").last()).toContainText("What is this cost for");
  await expect(page.getByTestId("ask-clarify-options")).toHaveCount(0);

  // Turn D: a typed reply that also happens to name "blood test" — never a second clarifying
  // question in a row, whatever the referent: this answers with what it has (it matches his
  // real papers) or says plainly nothing is written down, but it never asks again.
  await ask(page, "It is for a blood test");
  await expect(page.getByTestId("ask-earlier-turns")).toBeVisible();
  await expect(page.getByTestId("answer")).toBeVisible({ timeout: 15_000 });
  await expect(page.getByTestId("ask-clarify-options")).toHaveCount(0);
  // `.catch(() => "")` alone is not enough here: resolving `.last()` on a testid with zero
  // matches on the page still waits out the full actionability timeout before rejecting (a
  // past turn may have no "answer-honest" line at all) — guarded by `.count()` first instead.
  const lineLocator = page.getByTestId("answer-line-text");
  const finalText = (await lineLocator.count()) > 0 ? await lineLocator.last().innerText() : "";
  const honestLocator = page.getByTestId("answer-honest");
  const honestText = (await honestLocator.count()) > 0 ? await honestLocator.last().innerText() : "";
  expect(finalText + honestText).not.toContain("Which blood test is this about");
});

test("a cost question with no procedure named asks what it is for, free text, no options", async ({ page, request }) => {
  const pa = await seedFeed(request);
  await signInThroughTheApp(page, pa.phone, "Pa");
  await todayReady(page);
  await openAsk(page);

  await ask(page, "how much will this cost");
  await expect(page.getByTestId("answer-lines")).toBeVisible({ timeout: 15_000 });
  const question = page.getByTestId("answer-line-text").first();
  await expect(question).toContainText("What is this cost for");
  // Free text: no chips at all — `allow_other` with no options.
  await expect(page.getByTestId("ask-clarify-options")).toHaveCount(0);
});

test("a typed reply to a clarifying question dismisses it and starts the next turn", async ({ page, request }) => {
  const pa = await seedFeed(request);
  await signInThroughTheApp(page, pa.phone, "Pa");
  await todayReady(page);
  await openAsk(page);

  await ask(page, "how much will this cost");
  await expect(page.getByTestId("answer-lines")).toBeVisible({ timeout: 15_000 });
  await ask(page, "It is for a blood test");
  await expect(page.getByTestId("ask-earlier-turns")).toBeVisible();
  await expect(page.getByTestId("ask-clarify-options")).toHaveCount(0);
  await expect(page.getByTestId("answer")).toBeVisible({ timeout: 15_000 });
});

test("Mei's wording: a clarifying question is never 'Please specify', and its chips read caregiver voice", async ({ page, request }) => {
  const pa = await seedFeed(request);
  await seedTwoBloodTests(request, pa.token, pa.profileId);
  await addAndSignInMei(request, page, pa);
  await todayReady(page);
  await openAsk(page);

  await ask(page, "what about his blood test");
  await expect(page.getByTestId("answer-lines")).toBeVisible({ timeout: 15_000 });
  const text = (await page.getByTestId("answer-line-text").first().innerText()).toLowerCase();
  expect(text).not.toContain("please specify");
  expect(text).not.toContain("i need more information");
  const options = page.getByTestId("ask-clarify-options").getByRole("button");
  await expect(options).toHaveCount(2);
  const label = await options.first().innerText();
  expect(label).not.toContain("Your");
  expect(label).toContain("Pa");
});

for (const viewport of [
  { width: 390, height: 844, name: "390x844" },
  { width: 360, height: 640, name: "360x640" },
] as const) {
  test(`geometry ${viewport.name}: a clarifying question's chips sit fully above the composer and the tab bar`, async ({ page, request }) => {
    await page.setViewportSize({ width: viewport.width, height: viewport.height });
    const pa = await seedFeed(request);
    await seedTwoBloodTests(request, pa.token, pa.profileId);
    await signInThroughTheApp(page, pa.phone, "Pa");
    await todayReady(page);
    await openAsk(page);

    await ask(page, "what about my blood test");
    const options = page.getByTestId("ask-clarify-options").getByRole("button");
    await expect(options).toHaveCount(2, { timeout: 15_000 });
    const composer = page.getByTestId("ask-composer");
    const tabbar = page.locator("nav.tabbar");
    const composerBox = (await composer.boundingBox())!;
    const tabbarBox = (await tabbar.boundingBox())!;
    const chipsBox = (await page.getByTestId("ask-clarify-options").boundingBox())!;
    // The chips block sits above the composer, which sits above (or level with) the tab bar —
    // never under either.
    expect(chipsBox.y + chipsBox.height).toBeLessThanOrEqual(composerBox.y + 1);
    expect(composerBox.y + composerBox.height).toBeLessThanOrEqual(tabbarBox.y + 1);
  });
}
