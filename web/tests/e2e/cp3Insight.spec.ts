import { expect, test } from "@playwright/test";
import { API, fixClock, freshPhone, signInThroughTheApp } from "./helpers";
import { addProvider, auth, book, daysFromNow, EVERY_PART, letIn, openOwn, openRecord, placeholderPng, signInAs } from "./record-helpers";

/** Checkpoint 3, "What it means for you" (package 7, `docs/design/experience-blueprint.html`
 *  scene `insight`): the screen wired right after "Looks right", from both places a paper is
 *  confirmed — the Record's own Papers list, and onboarding. Every walk here is against the
 *  real backend (fixture adapters, no model call): the headline, the "Looked at" chips and the
 *  questions inside the card are the backend's own words, never a fixture of the web's own. */

test.beforeEach(async ({ page }) => {
  await fixClock(page);
});

/** A paper, still waiting for his yes, posted the same way `record-helpers.ts`'s own
 *  `confirmPhoto` posts one — except never confirmed here: the UI's own "Looks right" is what
 *  this suite means to exercise. */
async function postWaitingPaper(request: import("@playwright/test").APIRequestContext, token: string, profileId: string, label: string): Promise<void> {
  const posted = await request.post(`${API}/profiles/${profileId}/photos`, {
    ...auth(token),
    data: { data: placeholderPng(label).toString("base64"), content_type: "image/png", captured_at: "2026-09-14T08:00:00Z" },
  });
  expect(posted.status(), await posted.text()).toBe(201);
}

test("the Record flow: a lab paper with an out-of-range value, real stages, the headline, the card's own questions, Keep, and the question lands on the visit", async ({
  page,
  request,
}) => {
  const pa = await openOwn(request);
  const drTan = await addProvider(request, pa, "Dr Tan");
  const appointmentId = await book(request, pa, drTan, await daysFromNow(request, 7), "check-up");

  await postWaitingPaper(request, pa.token, pa.profileId, "lab-report-vitals-2026-09-10");

  await signInAs(page, pa, "Pa");
  await openRecord(page);
  await page.getByTestId("record-papers").click();
  await page.getByTestId("waiting-paper").click();
  await expect(page.getByTestId("review-card")).toContainText("Blood test");
  await page.getByTestId("looks-right").click();

  // The insight screen, a real screen of its own — the tab bar's own record.
  await expect(page.getByTestId("insight-screen")).toBeVisible();
  await expect(page.locator("h1")).toHaveText("What it means for you");

  // The orb stays beside the headline once the real stream has finished — never gone, the same
  // way a finished Ask turn keeps its own orb. `SoftText` keeps the whole line in a `.sr-only`
  // span beside its per-word animated spans; asserting on the element itself would read the
  // text twice (the two concatenate with no space between them).
  await expect(page.getByTestId("insight-turn")).toBeVisible();
  await expect(page.getByTestId("insight-orb")).toBeVisible();
  await expect(page.getByTestId("insight-headline").locator(".sr-only")).toHaveText("Here is what I would ask.");

  // Looked at: quiet chips, the stream's own real labels — never invented ones.
  await expect(page.getByTestId("insight-looked-at-label")).toHaveText("Looked at");
  const chips = page.getByTestId("insight-looked-at").locator(".glass-chip");
  expect(await chips.count()).toBeGreaterThan(0);

  // One card, titled for the real visit just booked, its questions as plain paragraphs inside
  // it — never a dose, never a verdict, never "should"/"stop"/"start"/"change".
  const card = page.getByTestId("insight-card");
  await expect(card).toBeVisible();
  await expect(card.locator("h3")).toHaveText(/^For Dr Tan on /);
  const questions = page.getByTestId("insight-question");
  const questionCount = await questions.count();
  expect(questionCount).toBeGreaterThan(0);
  const allQuestionsText = (await questions.allInnerTexts()).join(" ").toLowerCase();
  for (const word of ["dose", "should", "stop", "start", "change"]) expect(allQuestionsText).not.toContain(word);
  // Every question really is a question, first person, never a statement left standing alone.
  for (const text of await questions.allInnerTexts()) expect(text.trim().endsWith("?")).toBe(true);

  // The safety line, once: "Questions to ask, never answers." then the boundary sentence.
  await expect(page.getByTestId("insight-safety")).toHaveText("Questions to ask, never answers. This is not a doctor's advice.");
  await expect(page.locator('[data-testid="insight-safety"]')).toHaveCount(1);

  // No checkboxes, no "What stands out" block — this screen is about what to ask, the report
  // table already showed what stands out.
  await expect(page.getByTestId("insight-question-checkbox")).toHaveCount(0);
  await expect(page.getByTestId("insight-standout-rows")).toHaveCount(0);

  // Keep: the three states, then where it went — full width, its own row under the button.
  const keep = page.getByTestId("insight-keep");
  await expect(keep).toHaveText("Keep these for my visit");
  await keep.click();
  await expect(keep).toHaveAttribute("data-state", "done");
  await expect(keep).toHaveText("Kept");
  await expect(page.getByTestId("insight-kept-where")).toHaveText("Kept for your next visit.");

  // "Not now": back to the papers list, the same note it always gave.
  const leave = page.getByTestId("insight-leave");
  await expect(leave).toHaveText("Not now");
  await leave.click();
  await expect(page.getByTestId("record-note")).toHaveText("Nura wrote it down.");

  // On the visit itself, through the API: the question is really there, cited to the paper —
  // and really readable: the visit's own card (`patient_card`) verifies every line again on
  // the way out, in its own default profile (one idea, at most fifteen words), so a 200 here
  // is itself proof each kept question really is one whole, single-idea sentence.
  const listed = (await (
    await request.get(`${API}/profiles/${pa.profileId}/appointments/${appointmentId}/questions`, auth(pa.token))
  ).json()) as { questions: { text: string; source_kind: string | null; source_ids: string[] }[] };
  const fromThePaper = listed.questions.filter((q) => q.source_kind === "paper_insight");
  expect(fromThePaper.length).toBe(questionCount);
  expect(fromThePaper.some((q) => q.text.toLowerCase().startsWith("why is my"))).toBe(true);
});

test("no visit booked: the card falls back to the generic title, never a guessed doctor", async ({ page, request }) => {
  const pa = await openOwn(request);
  await postWaitingPaper(request, pa.token, pa.profileId, "lab-report-vitals-2026-09-10");

  await signInAs(page, pa, "Pa");
  await openRecord(page);
  await page.getByTestId("record-papers").click();
  await page.getByTestId("waiting-paper").click();
  await expect(page.getByTestId("review-card")).toContainText("Blood test");
  await page.getByTestId("looks-right").click();

  await expect(page.getByTestId("insight-headline")).toBeVisible();
  await expect(page.getByTestId("insight-card").locator("h3")).toHaveText("For your next visit");

  // Keep, with no visit booked: the honest fallback (#303 review, B3) — nothing is kept, the
  // button never claims "Kept", and the screen says plainly why.
  const keep = page.getByTestId("insight-keep");
  await keep.click();
  await expect(page.getByTestId("insight-keep-no-visit")).toHaveText(
    "There is no visit booked yet, so Nura has not kept these. Book a visit, then open this paper again.",
  );
  await expect(keep).toHaveAttribute("data-state", "idle");
  await expect(keep).toHaveText("Keep these for my visit");
});

test("nothing to ask: a paper with no printed range says so plainly, with a way on — never an empty screen", async ({ page, request }) => {
  const pa = await openOwn(request);
  await postWaitingPaper(request, pa.token, pa.profileId, "lipid-panel-2023-09-07");

  await signInAs(page, pa, "Pa");
  await openRecord(page);
  await page.getByTestId("record-papers").click();
  await page.getByTestId("waiting-paper").click();
  await page.getByTestId("looks-right").click();

  await expect(page.getByTestId("insight-headline").locator(".sr-only")).toHaveText("Nothing on this paper looks worth a question right now.");
  await expect(page.getByTestId("insight-card")).toHaveCount(0);
  await expect(page.getByTestId("insight-question")).toHaveCount(0);
  await expect(page.getByTestId("insight-keep")).toHaveCount(0);
  // The safety line still says its piece even with nothing to ask.
  await expect(page.getByTestId("insight-safety")).toHaveText("Questions to ask, never answers. This is not a doctor's advice.");
  // A calm state, never a dead end: the one way on is still there.
  const leave = page.getByTestId("insight-leave");
  await expect(leave).toBeVisible();
  await expect(leave).toBeInViewport();
  await leave.click();
  await expect(page.getByTestId("record-note")).toHaveText("Nura wrote it down.");
});

test("onboarding: 'Looks right' opens the insight screen first, and its own 'Not now' returns to the step that would have come next", async ({
  page,
  request,
}) => {
  const phone = freshPhone("+659889");
  await signInThroughTheApp(page, phone, "Pa");
  await page.getByTestId("door-for-me").click();
  await page.getByTestId("who-continue").click();
  await page.getByTestId("agree").click();
  await page.getByLabel("The name Nura uses").fill("Pa");
  await page.getByTestId("about-next").click();
  await page.getByTestId("about-lang-en").click();
  await page.getByTestId("decade-1950").click();
  await page.getByLabel("The doctor's name").fill("Dr Tan");
  await page.getByTestId("about-next").click();
  await page.getByTestId("breakfast-07:30").click();
  for (const item of ["large_text", "high_contrast", "voice_on", "big_targets", "one_thing_per_screen", "read_back", "repeat_prompts"]) await page.getByTestId(`${item}-no`).click();
  await page.getByTestId("density-simple").click();
  await page.getByTestId("cloud-done").click();

  const main = page.locator("main.onboarding");
  await expect(main).toHaveAttribute("data-stage", "records");
  await page.getByTestId("photo-input").setInputFiles({ name: "paper.png", mimeType: "image/png", buffer: placeholderPng("lipid-panel-2023-09-07") });
  await expect(page.getByTestId("reading-result")).toBeVisible();
  await page.getByTestId("see-report").click();
  await page.getByTestId("looks-right").click();

  // The insight screen, inside the sitting — no tab bar, no Shell, the sitting's own bare
  // chrome, one h1, the blueprint's own "Not now" (never "Continue"/"Next" invented here).
  await expect(main).toHaveAttribute("data-stage", "insight");
  await expect(page.locator("nav.tabbar")).toHaveCount(0);
  await expect(page.locator("h1")).toHaveText("What it means for you");
  const leave = page.getByTestId("insight-leave");
  await expect(leave).toHaveText("Not now");
  await expect(page.getByTestId("insight-headline").or(page.getByTestId("notice"))).toBeVisible();
  await leave.click();

  // Back to records — the sitting takes the paper in and says so — never a step skipped.
  await expect(main).toHaveAttribute("data-stage", "records");
  await expect(page.getByTestId("saved")).toHaveText("Nura wrote it down.");
});

test("a caregiver (Mei): the insight screen speaks of Pa's paper by name, never to him or as her own — headline and Keep button exactly", async ({
  page,
  request,
}) => {
  const pa = await openOwn(request);
  const mei = await letIn(request, pa, "Mei", "chief", EVERY_PART);
  await postWaitingPaper(request, pa.token, pa.profileId, "lab-report-vitals-2026-09-10");

  await signInAs(page, mei, "Mei", true);
  await openRecord(page);
  await page.getByTestId("record-papers").click();
  await page.getByTestId("waiting-paper").click();
  await expect(page.getByTestId("review-card")).toContainText("Blood test");
  await page.getByTestId("looks-right").click();

  await expect(page.locator("h1")).toHaveText("What it means for Pa");
  // The headline itself, exactly — never the self-voiced "Here is what I would ask." a
  // caregiver run used to read when `build_insight` had no `reader` of its own (#303
  // review, S4ii). A bare `toContain("pa")` here would have passed against "paper" too
  // (S4iii) — this checks the real, whole sentence instead.
  await expect(page.getByTestId("insight-headline").locator(".sr-only")).toHaveText(
    "Here is what I would ask about Pa's paper.",
  );
  // The Keep button's own caregiver twin, exactly (S4i) — never the self-voiced "Keep these
  // for my visit" a caregiver would otherwise see.
  await expect(page.getByTestId("insight-keep")).toHaveText("Keep these for Pa's visit");

  // "your"/"you"/"I"/"my" about his record is what #210's own sweep catches; this screen's
  // own words never carry them in caregiver voice — the headline, the looked-at chips, the
  // card's own questions AND the Keep button (S4iii: included in this sweep, not carved out)
  // are all rendered about him, by name, never in the first or second person.
  const turn = await page.getByTestId("insight-turn").innerText();
  const lookedAt = await page.getByTestId("insight-looked-at").innerText();
  const card = await page.getByTestId("insight-card").innerText();
  const safety = await page.getByTestId("insight-safety").innerText();
  const keepButton = await page.getByTestId("insight-keep").innerText();
  const spoken = [turn, lookedAt, card, safety, keepButton].join("\n").toLowerCase();
  expect(spoken).not.toMatch(/\byour\b|\byou\b|\bmy\b|\bi take\b|\bfor me\b/);
  expect(spoken).toMatch(/\bpa\b/); // the patient by name, a whole word — never "paper"'s own "pa"
});

for (const viewport of [
  { width: 390, height: 844, name: "phone" },
  { width: 1280, height: 900, name: "desktop" },
] as const) {
  test(`geometry at ${viewport.name} (${viewport.width}x${viewport.height}): nothing under the tab bar, the primary button fully visible, no horizontal scroll`, async ({
    page,
    request,
  }) => {
    await page.setViewportSize({ width: viewport.width, height: viewport.height });
    const pa = await openOwn(request);
    await postWaitingPaper(request, pa.token, pa.profileId, "lab-report-vitals-2026-09-10");

    await signInAs(page, pa, "Pa");
    await openRecord(page);
    await page.getByTestId("record-papers").click();
    await page.getByTestId("waiting-paper").click();
    await page.getByTestId("looks-right").click();
    await expect(page.getByTestId("insight-headline")).toBeVisible();

    expect(await page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth)).toBeLessThanOrEqual(0);
    const leave = page.getByTestId("insight-leave");
    await leave.scrollIntoViewIfNeeded();
    await expect(leave).toBeInViewport();
    const box = (await leave.boundingBox())!;
    const tabBar = page.locator("nav.tabbar");
    if (await tabBar.count()) {
      const barBox = (await tabBar.boundingBox())!;
      expect(box.y + box.height).toBeLessThanOrEqual(barBox.y + 1);
    }
  });
}
