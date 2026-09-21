import { expect, test } from "@playwright/test";
import { API, fixClock, freshPhone, seedMedicine, signInThroughTheApp } from "./helpers";
import { addProvider, auth, book, daysFromNow, EVERY_PART, letIn, openOwn, openRecord, placeholderPng, signInAs } from "./record-helpers";

/** Checkpoint 3, "What it means for you" (package 7, `docs/design/experience-blueprint.html`
 *  scene `insight`): the screen wired right after "Looks right", from both places a paper is
 *  confirmed — the Record's own Papers list, and onboarding. Every walk here is against the
 *  real backend (fixture adapters, no model call): the headline, the standout rows and the
 *  questions are the backend's own words, never a fixture of the web's own. */

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

test("the Record flow: a lab paper with an out-of-range value, its medicine, real stages, the headline, the questions, Keep, and the question lands on the visit", async ({ page, request }) => {
  const pa = await openOwn(request);
  // A statin on the record beside the paper's own out-of-range LDL — the same pairing
  // `test_paper_insight.py`'s own happy path uses, so a real question is really offered.
  await seedMedicine(request, pa.token, pa.profileId, { generic: "atorvastatin", strength: "20 mg", dose_text: "1 tab OD", quantity: 30 });

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

  // The headline: the backend's own words, once the real stream has finished — never a fixed
  // line, never before the report has actually landed. `SoftText` keeps the whole line in a
  // `.sr-only` span beside its per-word animated spans; asserting on the element itself would
  // read the text twice (the two concatenate with no space between them).
  await expect(page.getByTestId("insight-headline").locator(".sr-only")).toHaveText("Here is what is worth asking about this paper.");

  // What stands out: the paper's own out-of-range LDL, "Above" against the range printed on it
  // — the same words the report table itself would show for this row, reused, not a second one.
  await expect(page.getByTestId("insight-standout-rows")).toContainText("The bad cholesterol");
  await expect(page.getByTestId("insight-standout-rows")).toContainText("Above");

  // The question(s): real, cited, never a dose or a verdict — an out-of-range value beside its
  // medicine offers at least the value's own question (`test_paper_insight.py`'s own happy
  // path); the paper's own "this paper has a number outside its own printed range" may ride
  // beside it, so this checks every row offered rather than assuming exactly one.
  const questions = page.getByTestId("insight-question-row");
  const questionCount = await questions.count();
  expect(questionCount).toBeGreaterThan(0);
  const allQuestionsText = (await questions.allInnerTexts()).join(" ").toLowerCase();
  for (const word of ["dose", "should", "stop", "start", "change"]) expect(allQuestionsText).not.toContain(word);
  // Pre-selected, the blueprint's own card: every question offered is one worth asking.
  const checkboxes = page.getByTestId("insight-question-checkbox");
  for (let at = 0; at < questionCount; at++) await expect(checkboxes.nth(at)).toBeChecked();

  // The safety line, once.
  await expect(page.getByTestId("insight-safety")).toHaveText("Ranges are the ones printed on your paper. This is not a doctor's advice.");
  await expect(page.locator('[data-testid="insight-safety"]')).toHaveCount(1);

  // Keep: the three states, then where it went.
  const keep = page.getByTestId("insight-keep");
  await expect(keep).toHaveText("Keep these questions");
  await keep.click();
  await expect(keep).toHaveAttribute("data-state", "done");
  await expect(keep).toHaveText("Kept");
  await expect(page.getByTestId("insight-kept-where")).toHaveText("Kept for your next visit.");

  // Back to the papers list: the same note it always gave.
  await page.getByTestId("insight-leave").click();
  await expect(page.getByTestId("record-note")).toHaveText("Nura wrote it down.");
  await expect(page.getByTestId("checked-paper")).toHaveCount(1);

  // On the visit itself, through the API: the question is really there, cited to the paper.
  const listed = (await (
    await request.get(`${API}/profiles/${pa.profileId}/appointments/${appointmentId}/questions`, auth(pa.token))
  ).json()) as { questions: { text: string; source_kind: string | null; source_ids: string[] }[] };
  const fromThePaper = listed.questions.filter((q) => q.source_kind === "paper_insight");
  expect(fromThePaper.length).toBe(questionCount);
  expect(fromThePaper.some((q) => q.text.toLowerCase().includes("outside the range printed on it"))).toBe(true);
});

test("nothing stands out: a paper with no printed range says so plainly, with a way on — never an empty screen", async ({ page, request }) => {
  const pa = await openOwn(request);
  await postWaitingPaper(request, pa.token, pa.profileId, "lipid-panel-2023-09-07");

  await signInAs(page, pa, "Pa");
  await openRecord(page);
  await page.getByTestId("record-papers").click();
  await page.getByTestId("waiting-paper").click();
  await page.getByTestId("looks-right").click();

  await expect(page.getByTestId("insight-headline").locator(".sr-only")).toHaveText("Nothing on this paper looks worth a question right now.");
  await expect(page.getByTestId("insight-question-row")).toHaveCount(0);
  await expect(page.getByTestId("insight-keep")).toHaveCount(0);
  // A calm state, never a dead end: the one way on is still there.
  const leave = page.getByTestId("insight-leave");
  await expect(leave).toBeVisible();
  await expect(leave).toBeInViewport();
  await leave.click();
  await expect(page.getByTestId("record-note")).toHaveText("Nura wrote it down.");
});

test("onboarding: 'Looks right' opens the insight screen first, and its own 'Next' returns to the step that would have come next", async ({ page, request }) => {
  const phone = freshPhone("+659889");
  await signInThroughTheApp(page, phone, "Pa");
  await page.getByTestId("door-for-me").click();
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
  // chrome, one h1, the caller's own "Next" (never "Continue" invented here: the string is
  // `s.onboarding.next`, the same word every other onboarding step's own way on already uses).
  await expect(main).toHaveAttribute("data-stage", "insight");
  await expect(page.locator("nav.tabbar")).toHaveCount(0);
  await expect(page.locator("h1")).toHaveText("What it means for you");
  const next = page.getByTestId("insight-leave");
  await expect(next).toHaveText("Next");
  await expect(page.getByTestId("insight-headline").or(page.getByTestId("notice"))).toBeVisible();
  await next.click();

  // Back to records — the sitting takes the paper in and says so — never a step skipped.
  await expect(main).toHaveAttribute("data-stage", "records");
  await expect(page.getByTestId("saved")).toHaveText("Nura wrote it down.");
});

test("a caregiver (Mei): the insight screen says Pa's papers about him by name, never to him", async ({ page, request }) => {
  const pa = await openOwn(request);
  const mei = await letIn(request, pa, "Mei", "chief", EVERY_PART);
  await postWaitingPaper(request, pa.token, pa.profileId, "lab-report-vitals-2026-09-10");

  await signInAs(page, mei, "Mei", true);
  await openRecord(page);
  await page.getByTestId("record-papers").click();
  await page.getByTestId("waiting-paper").click();
  await page.getByTestId("looks-right").click();

  await expect(page.locator("h1")).toHaveText("What it means for Pa");
  await expect(page.getByTestId("insight-headline")).toBeVisible();
  const lines = await page.getByTestId("insight-screen").innerText();
  // "your"/"you"/"I"/"my" about his record is what #210's own sweep catches; this screen's own
  // words never carry them — only the neutral "Above"/"In range" flags and the questions
  // themselves, which are never phrased in the first or second person either way.
  expect(lines.toLowerCase()).not.toMatch(/\byour\b|\byou\b/);
});

for (const viewport of [
  { width: 390, height: 844, name: "phone" },
  { width: 1280, height: 900, name: "desktop" },
] as const) {
  test(`geometry at ${viewport.name} (${viewport.width}x${viewport.height}): nothing under the tab bar, the primary button fully visible, no horizontal scroll`, async ({ page, request }) => {
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
