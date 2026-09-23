import { expect, test, type APIRequestContext, type Page } from "@playwright/test";
import { API, fixClock, seedOwner, signInThroughTheApp, todayReady, type Owner } from "./helpers";

/** D-1/D-3 (docs/design/audit-2026-09-22.md §3.1/§5): Ask states a fact it holds. Reproduced
 *  by the audit on fixtures — "How is my cholesterol?" answered with no number, "Is it high?"
 *  answered "Nura does not have that written down." — about a paper he had already confirmed.
 *  These walks prove the opposite now, on the same two real fixtures the audit used
 *  (`backend/tests/fixtures/paper/lipid-panel-2025-08-29.json`, no printed range, quoted in the
 *  audit's own finding (e); `lab-report-vitals-2026-09-10.json`, an LDL of 140 against a
 *  printed "<130"), through the app the owner actually uses — the rule-based asker
 *  (`NURA_ASKER=rule`, this suite's own default), never a mock. */

const PNG = Buffer.from([0x89, 0x50, 0x4e, 0x47, 0x0d, 0x0a, 0x1a, 0x0a]);

test.beforeEach(async ({ page }) => {
  await fixClock(page);
});

/** A confirmed lab report, hung off an open episode — the same shape `ask-clarify.spec.ts`'s
 *  own `seedConfirmedLabReport` uses, so the paper is visible to Ask's corpus
 *  (`app.search.ask._corpus_stream`'s RECORDS branch only populates `corpus.papers` for an
 *  artefact an `Attachment` names). */
async function seedConfirmedLabReport(request: APIRequestContext, owner: Owner, fixture: string, capturedAt: string): Promise<void> {
  const headers = { Authorization: `Bearer ${owner.token}` };
  const opened = await request.post(`${API}/profiles/${owner.profileId}/episodes`, {
    headers,
    data: { kind: "other", label: "check-up" },
  });
  if (opened.status() !== 201) throw new Error(`episode: ${opened.status()} ${await opened.text()}`);
  const episodeId = ((await opened.json()) as { episode_id: string }).episode_id;
  const bytes = Buffer.concat([PNG, Buffer.from(`nura-paper-placeholder:${fixture}\n`)]);
  const photo = await request.post(`${API}/profiles/${owner.profileId}/photos`, {
    headers,
    data: { data: bytes.toString("base64"), content_type: "image/png", captured_at: capturedAt },
  });
  if (photo.status() !== 201) throw new Error(`photo ${fixture}: ${photo.status()} ${await photo.text()}`);
  const card = (await photo.json()) as { card_id: string; fields: { field_id: string; attribute: string }[] };
  const decisions = card.fields.map((field) => ({ field_id: field.field_id, decision: "confirmed" }));
  const minted = await request.post(`${API}/profiles/${owner.profileId}/confirmations`, {
    headers,
    data: { subject: "review_card", card_id: card.card_id, decisions, episode_id: episodeId },
  });
  if (minted.status() !== 201) throw new Error(`mint ${fixture}: ${minted.status()} ${await minted.text()}`);
  const confirmation_id = ((await minted.json()) as { confirmation_id: string }).confirmation_id;
  const confirmed = await request.post(`${API}/profiles/${owner.profileId}/review-cards/${card.card_id}/confirm`, {
    headers,
    data: { decisions, confirmation_id, episode_id: episodeId },
  });
  if (!confirmed.ok()) throw new Error(`confirm ${fixture}: ${confirmed.status()} ${await confirmed.text()}`);
}

async function openAsk(page: Page): Promise<void> {
  await page.getByTestId("home-ask-open").click();
  await expect(page.getByTestId("ask-screen")).toBeVisible();
}

async function ask(page: Page, question: string): Promise<void> {
  await page.getByLabel("Your question").fill(question);
  await page.getByTestId("ask-send").click();
}

test("a confirmed lab value with no printed range: the number and its date, never silenced", async ({ page, request }) => {
  const pa = await seedOwner(request);
  // The audit's own fixture, quoted verbatim in finding (e): "Your cholesterol was 212 on …"
  // is what the onboarding read-back already gets right; this proves Ask now does too.
  await seedConfirmedLabReport(request, pa, "lipid-panel-2025-08-29", "2025-08-29T08:00:00Z");
  await signInThroughTheApp(page, pa.phone, "Pa");
  await todayReady(page);
  await openAsk(page);

  // "total cholesterol", not the shorter "cholesterol" alone: this one paper carries four
  // lipid analytes (total cholesterol, HDL, LDL, triglycerides), all under the same
  // "lipid_panel" subject — naming the one this question is about is what picks out its own
  // fact over a sibling's (the retriever's own longest-phrase-wins rule, `KeywordRetriever`).
  await ask(page, "What is my total cholesterol?");
  await expect(page.getByTestId("answer-lines")).toBeVisible({ timeout: 15_000 });
  const text = (await page.getByTestId("answer-line-text").allInnerTexts()).join(" ");
  // The number, plain — never "mg/dL" (plain words rule 12: no unit he does not use), and
  // never the old silent `RECALL["paper"]` line ("…is in your papers.", no number at all).
  expect(text).toContain("212");
  expect(text.toLowerCase()).not.toContain("mg/dl");
  expect(text).not.toBe("Your cholesterol test from Friday 29 August is in your papers.");

  await ask(page, "Is my cholesterol high?");
  await expect(page.getByTestId("answer-lines").last()).toBeVisible({ timeout: 15_000 });
  const second = (await page.getByTestId("answer-line-text").allInnerTexts()).join(" ");
  // Never "Nura does not have that written down" about a paper he confirmed himself (the
  // audit's exact reproduction) — the honest truth about the paper instead: it prints no
  // range, so ask the doctor, never a guess.
  expect(second).not.toContain("does not have that written down");
  expect(second.toLowerCase()).toContain("no range");
});

test("a confirmed lab value above its printed range: the paper's own comparison, never the app's judgement", async ({ page, request }) => {
  const pa = await seedOwner(request);
  // LDL 140 against a printed "<130" (backend/tests/fixtures/paper/lab-report-vitals-2026-09-10.json).
  await seedConfirmedLabReport(request, pa, "lab-report-vitals-2026-09-10", "2026-09-10T08:00:00Z");
  await signInThroughTheApp(page, pa.phone, "Pa");
  await todayReady(page);
  await openAsk(page);

  await ask(page, "Is my cholesterol high?");
  await expect(page.getByTestId("answer-lines")).toBeVisible({ timeout: 15_000 });
  const text = (await page.getByTestId("answer-line-text").allInnerTexts()).join(" ");
  expect(text).toContain("140");
  // Above the range printed ON THE PAPER — never "high" (the app's own word would be a
  // judgement the boundary rule forbids; the paper's own printed comparison is not).
  expect(text.toLowerCase()).toContain("range");
  expect(text.toLowerCase()).toContain("paper");
  expect(text.toLowerCase()).not.toMatch(/\bhigh\b/);
});
