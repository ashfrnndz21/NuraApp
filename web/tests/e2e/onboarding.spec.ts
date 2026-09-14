import { mkdirSync } from "node:fs";
import { join } from "node:path";
import { expect, test, type APIRequestContext, type Page } from "@playwright/test";
import { en } from "../../src/strings/en";
import { API, apiToken, captureSpeech, freshPhone, signInThroughTheApp } from "./helpers";

/** Checkpoint 11 on a phone-sized screen: onboarding end to end. The E01 routes (settings,
 *  the condition graph, the biography, the plan) are answered by `src/api/mock/` when the
 *  app runs under VITE_API_MOCK=1 (`make web-mock`), or by the backend once E01 merges; the
 *  photo, the review card, the yes and the facts are the live E02 API either way. */

const SHOTS = process.env.W3_SHOTS ?? join(process.cwd(), "test-results", "w3-shots");
const stamp = Date.now();
function shot(name: string): string {
  mkdirSync(SHOTS, { recursive: true });
  return join(SHOTS, `w3-${name}-${stamp}.png`);
}

/** The bytes the fixture extractor knows a redacted paper by (backend/tests/paper.py). */
const PNG = Buffer.from([0x89, 0x50, 0x4e, 0x47, 0x0d, 0x0a, 0x1a, 0x0a]);
const placeholder = (label: string) => Buffer.concat([PNG, Buffer.from(`nura-paper-placeholder:${label}\n`, "ascii")]);
const placeholderPdf = (label: string) => Buffer.from(`%PDF-1.4\nnura-paper-placeholder:${label}\n`, "ascii");
const SKIP = "needs E01's routes: run the app with VITE_API_MOCK=1 (make web-mock) until E01 merges";

/** About you, answered quickly, in his own papers' patient density. */
async function throughAbout(page: Page): Promise<void> {
  await page.getByLabel("The name Nura uses").fill("Pa");
  await page.getByTestId("about-next").click();
  await page.getByTestId("about-lang-en").click();
  await page.getByTestId("decade-1950").click();
  await page.getByLabel("The doctor's name").fill("Dr Tan");
  await page.getByTestId("about-next").click();
  await page.getByTestId("breakfast-07:30").click();
  for (const item of ["sight", "hearing", "hands", "memory"]) await page.getByTestId(`${item}-no`).click();
}

async function signedInToOnboarding(page: Page, request: APIRequestContext, prefix: string): Promise<string> {
  const phone = freshPhone(prefix);
  await captureSpeech(page);
  await signInThroughTheApp(page, phone, "Pa");
  test.skip(!(await e01Answers(page, request)), SKIP);
  await page.getByTestId("door-for-me").click();
  await page.getByTestId("agree").click();
  await throughAbout(page);
  return phone;
}

async function profileOf(request: APIRequestContext, phone: string): Promise<{ auth: { Authorization: string }; id: string }> {
  const token = await apiToken(request, phone);
  const auth = { Authorization: `Bearer ${token}` };
  const me = (await (await request.get(`${API}/me`, { headers: auth })).json()) as { profile_id: string };
  return { auth, id: me.profile_id };
}

async function e01Answers(page: Page, request: APIRequestContext): Promise<boolean> {
  const mocked = await page.evaluate(() => Boolean((window as unknown as { __NURA_API_MOCK__?: boolean }).__NURA_API_MOCK__));
  if (mocked) return true;
  return (await request.get(`${API}/onboarding/conditions?language=en`)).status() !== 404;
}

const spoken = (page: Page) => page.evaluate(() => (window as unknown as { __spoken: string[] }).__spoken.splice(0));

test("the patient's own onboarding: about you, the cloud, read-back, a paper, questions, gaps", async ({ page, request }) => {
  const phone = freshPhone("+659888");
  await captureSpeech(page);
  await signInThroughTheApp(page, phone, "Pa");
  test.skip(!(await e01Answers(page, request)), "needs E01's routes: run the app with VITE_API_MOCK=1 (make web-mock) until E01 merges");
  await page.getByTestId("door-for-me").click();
  await page.getByTestId("agree").click();

  // About you: one question per screen, patient density, 56px targets.
  const main = page.locator("main.onboarding");
  await expect(main).toHaveAttribute("data-item", "name");
  await expect(page.locator("html")).toHaveAttribute("data-density", "patient");
  await expect(page.getByRole("heading", { name: "What should Nura call you?" })).toBeVisible();
  await page.getByLabel("The name Nura uses").fill("Pa");
  await page.getByTestId("about-next").click();
  await expect(main).toHaveAttribute("data-item", "language");
  expect((await page.getByTestId("about-lang-en").boundingBox())!.height).toBeGreaterThanOrEqual(56);
  await page.getByTestId("about-lang-en").click();
  await page.getByTestId("decade-1950").click();
  await page.getByLabel("The doctor's name").fill("Dr Tan");
  await page.getByTestId("about-next").click();
  await expect(page.getByTestId("about-breakfast")).toContainText("Nura ties morning tablets to breakfast.");
  await page.getByTestId("breakfast-07:30").click();
  await page.getByTestId("sight-yes").click();
  await page.getByTestId("hearing-no").click();
  await page.getByTestId("hands-no").click();
  await page.getByTestId("memory-no").click();

  // The word cloud: the common words big and on the first screen, no scrolling.
  await expect(main).toHaveAttribute("data-stage", "cloud");
  await expect(page.getByRole("heading", { name: "What is part of your health?" })).toBeVisible();
  const viewport = page.viewportSize()!;
  for (const id of ["bp", "chol", "sugar", "heart"]) {
    const word = page.getByTestId(`word-${id}`);
    await expect(word).toHaveAttribute("data-size", "3");
    const box = (await word.boundingBox())!;
    expect(box.y + box.height, id).toBeLessThanOrEqual(viewport.height);
    expect(box.height).toBeGreaterThanOrEqual(56);
  }
  expect(await page.evaluate(() => window.scrollY)).toBe(0);
  await expect(page.getByTestId("word-thyroid")).toHaveCount(0);

  // A tap picks the plain word, shows the clinic's term in brackets, and speaks — only now.
  expect(await spoken(page)).toEqual([]);
  await page.getByTestId("word-bp").click();
  await expect(page.getByTestId("word-bp")).toHaveAttribute("aria-pressed", "true");
  await expect(page.getByTestId("word-bp").getByTestId("term")).toHaveText(" (hypertension)");
  expect(await spoken(page)).toEqual(["High blood pressure", "Doctors call it hypertension."]);
  await expect(page.getByTestId("cloud-status")).toHaveText("Nura noted that.");
  // What goes with it comes in right after it; a word two picks point at grows.
  const order = await page.getByTestId("cloud").locator("button").evaluateAll((all) => all.map((each) => each.getAttribute("data-testid")));
  expect(order.indexOf("word-bp_meds")).toBe(order.indexOf("word-bp") + 1);
  await expect(page.getByTestId("word-heart_doc")).toHaveAttribute("data-size", "2");
  await page.getByTestId("word-chol").click();
  await expect(page.getByTestId("word-heart_doc")).toHaveAttribute("data-size", "3");
  await page.getByTestId("word-bp_meds").click();
  await page.getByTestId("word-statin").click();
  await spoken(page);
  await page.evaluate(() => window.scrollTo(0, 0));
  await page.screenshot({ path: shot("word-cloud") });
  await page.getByTestId("cloud-done").click();

  // The follow-up questions, one per screen, the backend's words and options.
  await expect(page.getByTestId("ask-bp_meds")).toContainText("How long have you taken them?");
  await page.getByTestId("option-1to5").click();
  await expect(page.getByTestId("ask-statin")).toContainText("Does the tablet trouble you?");
  await page.getByTestId("option-none").click();

  // Read-back: one backend line per screen, Yes / No on paper, its source and its State.
  const line = page.getByTestId("readback-line");
  await expect(line).toHaveCount(1);
  await expect(line).toContainText("You have high blood pressure.");
  await expect(line).toContainText("This is 1 of 6.");
  await expect(line.getByTestId("source")).toContainText("From what you told Nura on");
  await expect(line).toHaveAttribute("data-state-id", /.+/);
  await line.getByTestId("hear").click();
  expect(await spoken(page)).toEqual(["You have high blood pressure."]);
  await line.getByTestId("readback-yes").click();
  await expect(line).toContainText("Your cholesterol is high.");
  await line.getByTestId("readback-no").click();
  await expect(page.getByTestId("readback-ack")).toHaveText("Nura will not build on that one.");
  for (let n = 3; n <= 6; n++) {
    await expect(line).toContainText(`This is ${n} of 6.`);
    await line.getByTestId("readback-yes").click();
  }

  // The records step: the server's prompt, shown and spoken on Hear.
  await expect(main).toHaveAttribute("data-stage", "records");
  const prompt = page.getByTestId("prompt");
  await expect(prompt).toContainText("Next, Nura would like to see your papers.");
  await expect(prompt).toHaveAttribute("data-state-id", /.+/);
  await prompt.getByTestId("hear").click();
  expect((await spoken(page))[0]).toBe("Thank you for telling Nura.");
  await expect(page.getByTestId("photo-input")).toHaveAttribute("accept", "image/*,application/pdf");
  await expect(page.getByTestId("photo-input")).toHaveAttribute("capture", "environment");

  // A photo of the lipid report: the live E02 review card.
  await page.getByTestId("photo-input").setInputFiles({ name: "lipids.png", mimeType: "image/png", buffer: placeholder("lipid-panel-2023-09-07") });
  const card = page.getByTestId("review-card");
  await expect(card).toContainText("This is a blood test.");
  await expect(card).toContainText(/The paper is dated Thursday,? 7 September 2023\./);
  await expect(card.getByTestId("source")).toContainText("From the photo you added on");
  await expect(page.getByTestId("field-total_cholesterol").getByTestId("confidence")).toHaveText("Nura is sure of this one.");
  await expect(page.getByTestId("field-triglycerides").getByTestId("confidence")).toHaveText("Please check this one.");
  await expect(page.getByTestId("field-triglycerides")).toHaveAttribute("data-needs-confirm", "true");
  await expect(page.getByTestId("field-triglycerides")).toContainText("The blood fats");
  await expect(page.getByTestId("field-triglycerides").locator("input")).toHaveValue("64");
  await page.screenshot({ path: shot("review-card"), fullPage: true });
  // In the patient density every line has its spoken twin.
  await page.getByTestId("field-triglycerides").getByTestId("hear").click();
  expect(await spoken(page)).toEqual(["The blood fats", "64 mg/dL", "Please check this one."]);

  // Correct the misread blood fats to what the paper says; a word is caught first.
  const fats = page.getByTestId("field-triglycerides").locator("input");
  await fats.fill("fifty-four");
  await page.getByTestId("looks-right").click();
  await expect(page.getByTestId("not-a-number")).toHaveText("Please type the number from the paper.");
  await fats.fill("54");
  await page.getByTestId("field-vldl").getByTestId("leave-out").click();
  await expect(page.getByTestId("field-vldl")).toContainText("Nura will leave this one out.");
  await page.getByTestId("looks-right").click();

  // What Nura learned, and the next prompt.
  await expect(page.getByTestId("learned")).toContainText("Your blood test is in your papers now.");
  await expect(page.getByTestId("prompt")).toContainText("Do you have another paper to hand?");

  // On the record: the correction as typed, the line left out absent, provenance kept.
  const token = await apiToken(request, phone);
  const auth = { Authorization: `Bearer ${token}` };
  const me = (await (await request.get(`${API}/me`, { headers: auth })).json()) as { profile_id: string };
  const facts = (await (await request.get(`${API}/profiles/${me.profile_id}/facts?subject=lipid_panel`, { headers: auth })).json()) as {
    attribute: string;
    value: unknown;
    artifact_id: string | null;
  }[];
  const byName = new Map(facts.map((fact) => [fact.attribute, fact]));
  expect(byName.get("triglycerides")?.value).toBe(54);
  expect(byName.get("total_cholesterol")?.value).toBe(230);
  expect(byName.has("vldl")).toBe(false);
  for (const fact of facts) expect(fact.artifact_id).toBeTruthy();

  // "That is all for today" closes; the questions the paper raised, one per screen.
  await page.getByTestId("all-done").click();
  const question = page.getByTestId("question");
  await expect(question).toHaveCount(1);
  await expect(question).toContainText("Ask Dr Tan for a newer one.");
  await expect(question).toHaveAttribute("data-state-id", /.+/);
  await question.getByTestId("hear").click();
  expect(await spoken(page)).toEqual(["Your blood test is from a while ago.", "Ask Dr Tan for a newer one."]);
  await question.getByTestId("keep").click();
  await expect(page.getByTestId("question-ack")).toHaveText("Nura will keep this one for the visit.");
  await expect(question).toContainText("Ask Dr Tan if the tablet is working.");
  await question.getByTestId("not-this").click();
  await expect(question).toContainText("Ask Dr Tan if you should.");
  await question.getByTestId("keep").click();

  // Gaps and unlocks: one card for the patient, with how many follow.
  await expect(main).toHaveAttribute("data-stage", "plan");
  await expect(page.getByTestId("done-prompt")).toContainText("That is all for now.");
  const gap = page.getByTestId("gap-card");
  await expect(gap).toHaveCount(1);
  await expect(gap).toHaveAttribute("data-gap", "meds");
  await expect(gap).toContainText("Which tablets you take, and how much");
  await expect(gap).toContainText("With it Nura can check each new medicine against the rest.");
  await expect(gap).toContainText(/Nura will ask for this on \w+day/);
  await expect(gap).toHaveAttribute("data-state-id", /.+/);
  await expect(page.getByTestId("more-after")).toHaveText(/There (is 1 more|are \d+ more) after that\./);
  // Later sends it back; the next one comes.
  await gap.getByTestId("later").click();
  await expect(page.getByTestId("plan-status")).toHaveText("Nura will ask once more in a few days.");
  await expect(gap).not.toHaveAttribute("data-gap", "meds");
  const next = await gap.getAttribute("data-gap");
  // Do it now: the camera, the card, the yes, and back here with that gap closed.
  await gap.getByTestId("photo-input").setInputFiles({ name: "label.png", mimeType: "image/png", buffer: placeholder("warfarin-label-2024-03-12") });
  await expect(page.getByTestId("review-card")).toContainText("This is a medicine label.");
  await expect(page.getByTestId("field-dose")).toContainText("If this one is wrong, leave it out.");
  await page.getByTestId("looks-right").click();
  await expect(main).toHaveAttribute("data-stage", "plan");
  await expect(gap).toHaveCount(1);
  expect(await gap.getAttribute("data-gap")).toBe(next);

  // Nothing sideways, anywhere on the way.
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= document.documentElement.clientWidth)).toBe(true);

  // Today, and nothing of onboarding kept on the phone.
  await page.getByTestId("open-nura").click();
  await expect(page.locator("nav.tabbar")).toBeVisible();
  const kept = await page.evaluate(async () => {
    const keys = await new Promise<string[]>((resolve) => {
      const open = indexedDB.open("nura");
      open.onsuccess = () => {
        const db = open.result;
        if (!db.objectStoreNames.contains("kv")) return resolve([]);
        const all = db.transaction("kv").objectStore("kv").getAllKeys();
        all.onsuccess = () => resolve(all.result.map(String));
      };
      open.onerror = () => resolve([]);
    });
    return { keys, local: localStorage.length, session: sessionStorage.length };
  });
  expect(kept.local).toBe(0);
  expect(kept.session).toBe(0);
  for (const key of kept.keys) expect(key).toMatch(/^(session\.|device\.|today\.|proud\.|takenDays\.)/);
});

test("the caregiver density, for a chief setting up her father", async ({ page, request }) => {
  const phone = freshPhone("+659889");
  await captureSpeech(page);
  await signInThroughTheApp(page, phone, "Ash");
  test.skip(!(await e01Answers(page, request)), "needs E01's routes: run the app with VITE_API_MOCK=1 (make web-mock) until E01 merges");
  await page.getByTestId("door-for-someone").click();
  await page.getByLabel("Their name").fill("Pa");
  await page.getByLabel("Their phone number").fill(freshPhone("+659887"));
  await page.getByLabel("Who they are to you").fill("Father");
  await page.getByText("They asked you to do this.").click();
  await page.getByRole("button", { name: "Set it up" }).click();

  // Caregiver density: every question on one page, in his name; her phone keeps her language.
  await expect(page.locator("html")).toHaveAttribute("data-density", "caregiver");
  await expect(page.getByRole("heading", { name: "A few things about Pa" })).toBeVisible();
  await expect(page.getByTestId("about-name")).toBeVisible();
  await expect(page.getByTestId("about-memory")).toContainText("Does Pa forget things more than before?");
  await page.getByTestId("about-lang-ms").click();
  await expect(page.locator("html")).toHaveAttribute("lang", "en");
  await expect(page.getByTestId("about-lang-ms")).toHaveAttribute("aria-pressed", "true");
  await page.getByTestId("decade-1940").click();
  await page.getByLabel("The doctor's name").fill("Dr Lim");
  await page.getByTestId("breakfast-07:00").click();
  await page.getByTestId("sight-yes").click();
  await page.getByTestId("about-next").click();

  await expect(page.getByRole("heading", { name: "What is part of Pa's health?" })).toBeVisible();
  await page.getByTestId("word-bp").click();
  await page.getByTestId("word-bp_home").click();
  await page.screenshot({ path: shot("word-cloud-caregiver") });
  await page.getByTestId("cloud-done").click();
  await expect(page.getByTestId("ask-bp_home")).toBeVisible();
  await page.getByTestId("option-130to150").click();
  await page.getByTestId("asks-next").click();

  // The read-back as a list, each line with its own Yes and No.
  const lines = page.getByTestId("readback-line");
  await expect(lines).toHaveCount(3);
  await lines.nth(1).getByTestId("readback-no").click();
  await expect(lines.nth(1)).toContainText("Nura will not build on that one.");
  await expect(lines.nth(1).getByTestId("readback-no")).toHaveAttribute("aria-pressed", "true");
  await page.getByTestId("readback-next").click();

  // A paper in the caregiver density: the card's header speaks, its lines do not each.
  await page.getByTestId("photo-input").setInputFiles({ name: "lipids.png", mimeType: "image/png", buffer: placeholder("lipid-panel-2023-09-07") });
  await expect(page.getByTestId("review-card").getByTestId("hear")).toHaveCount(1);
  await expect(page.getByTestId("field-triglycerides").getByTestId("hear")).toHaveCount(0);
  await page.getByTestId("looks-right").click();
  await expect(page.getByTestId("learned")).toBeVisible();

  // The questions and the whole gap list, then Today.
  await page.getByTestId("all-done").click();
  await expect(page.getByTestId("question").first()).toContainText("Ask Dr Lim");
  await page.getByTestId("questions-next").click();
  const gaps = page.getByTestId("gap-card");
  await expect(gaps.first()).toBeVisible();
  expect(await gaps.count()).toBeGreaterThan(1);
  await expect(page.getByTestId("more-after")).toHaveCount(0);
  await page.getByTestId("open-nura").click();
  await expect(page.locator("nav.tabbar")).toBeVisible();
  await expect(page.locator("html")).toHaveAttribute("data-density", "caregiver");
});

test("his language takes effect the moment he picks it", async ({ page, request }) => {
  const phone = freshPhone("+659886");
  await signInThroughTheApp(page, phone, "Pa");
  test.skip(!(await e01Answers(page, request)), "needs E01's routes: run the app with VITE_API_MOCK=1 (make web-mock) until E01 merges");
  await page.getByTestId("door-for-me").click();
  await page.getByTestId("agree").click();
  await page.getByTestId("about-next").click();
  await page.getByTestId("about-lang-ms").click();
  await expect(page.locator("html")).toHaveAttribute("lang", "ms");
  await expect(page.getByRole("heading", { name: "Bila anda dilahirkan?" })).toBeVisible();
});

test("papers of every kind: a hospital letter as a PDF, a page that is not a health paper, a line Nura could not read", async ({ page, request }) => {
  const phone = await signedInToOnboarding(page, request, "+659885");
  await page.getByTestId("word-hosp").click();
  await page.getByTestId("cloud-done").click();
  await page.getByTestId("readback-line").getByTestId("readback-yes").click();
  const main = page.locator("main.onboarding");
  await expect(main).toHaveAttribute("data-stage", "records");

  // A PDF that is not a health paper: the backend reads it and says so; nothing to say yes to.
  await page.getByTestId("file-input").setInputFiles({ name: "receipt.pdf", mimeType: "application/pdf", buffer: placeholderPdf("receipt-2026-09-01") });
  await expect(page.getByTestId("review-unreadable")).toBeVisible();
  await expect(page.getByTestId("looks-right")).toHaveCount(0);
  await page.getByRole("button", { name: "Go back" }).click();

  // The hospital letter as a PDF goes to /imports and comes back as a card like any photo.
  await page.getByTestId("file-input").setInputFiles({ name: "letter.pdf", mimeType: "application/pdf", buffer: placeholderPdf("discharge-letter-2026-08-20") });
  await expect(page.getByTestId("review-card")).toContainText("This is a hospital letter.");
  await expect(page.getByTestId("field-reason")).toContainText("Why you were in hospital");
  await spoken(page); // what the cloud's tap said earlier
  await page.getByTestId("field-reason").getByTestId("hear").click();
  const reason = await spoken(page);
  expect(reason.slice(0, 2)).toEqual(["Why you were in hospital", "heart failure"]);
  await page.getByTestId("looks-right").click();
  await expect(page.getByTestId("learned")).toContainText("Your hospital letter is in your papers now.");

  // A clinic slip with a line Nura could not read: never confirmed as read; he types it.
  await page.getByTestId("photo-input").setInputFiles({ name: "slip.png", mimeType: "image/png", buffer: placeholder("clinic-slip-2026-09-10") });
  const frequency = page.getByTestId("field-frequency");
  await expect(frequency.getByTestId("confidence")).toHaveText("Nura could not read this one.");
  await expect(frequency.locator("input")).toHaveValue("");
  await page.getByTestId("looks-right").click();
  await expect(frequency.getByTestId("not-a-number")).toHaveText("Please type what the paper says.");
  await frequency.locator("input").fill("twice a day");
  await page.getByTestId("looks-right").click();
  await expect(page.getByTestId("learned")).toContainText("The appointment card is in your papers now.");

  // On the record: the letter's reason, and the frequency exactly as he typed it.
  const { auth, id } = await profileOf(request, phone);
  const facts = (await (await request.get(`${API}/profiles/${id}/facts`, { headers: auth })).json()) as { subject: string; attribute: string; value: unknown }[];
  expect(facts.find((fact) => fact.subject === "discharge" && fact.attribute === "reason")?.value).toBe("heart failure");
  expect(facts.find((fact) => fact.attribute === "frequency")?.value).toBe("twice a day");
});

test("the Ready screen's other actions: a follow-up reopened, and one person let in", async ({ page, request }) => {
  const phone = await signedInToOnboarding(page, request, "+659884");
  await page.getByTestId("word-allergy").click();
  await page.getByTestId("word-drug_all").click();
  await page.getByTestId("cloud-done").click();
  await page.getByTestId("ask-not-now").click();
  const line = page.getByTestId("readback-line");
  await line.getByTestId("readback-yes").click();
  await line.getByTestId("readback-yes").click();
  await page.getByTestId("all-done").click();
  await page.getByTestId("question").getByTestId("keep").click();

  // A tap gap reopens its follow-up question, and the answer closes it.
  const main = page.locator("main.onboarding");
  const gap = page.getByTestId("gap-card");
  await expect(main).toHaveAttribute("data-stage", "plan");
  await expect(gap).toHaveAttribute("data-gap", "all");
  await gap.getByTestId("do-it-now").click();
  await expect(page.getByTestId("ask-drug_all")).toContainText("Which medicine is it?");
  await page.getByTestId("option-aspirin").click();
  await expect(main).toHaveAttribute("data-stage", "plan");
  await expect(gap).not.toHaveAttribute("data-gap", "all");

  // Later, until the invite gap comes up; then E12's flow.
  // Each Later waits for the next card: a second Later on the same gap would retire it.
  for (let n = 0; n < 4; n++) {
    const current = await gap.getAttribute("data-gap");
    if (current === "fam") break;
    await gap.getByTestId("later").click();
    await expect(gap).not.toHaveAttribute("data-gap", current!);
  }
  await expect(gap).toHaveAttribute("data-gap", "fam");
  await expect(gap.getByTestId("do-it-now")).toBeEnabled();
  await gap.getByTestId("do-it-now").click();
  const mei = freshPhone("+659883");
  await page.getByLabel("Their name").fill("Mei");
  await page.getByLabel("Their phone number").fill(mei);
  await page.getByLabel("Who they are to you").fill("daughter");
  await page.getByTestId("invite-next").click();
  await page.getByTestId("part-medicines").click();
  await page.getByTestId("part-visits").click();
  await page.getByTestId("invite-see-words").click();
  const words = page.getByTestId("invite-words");
  await expect(words).toContainText("- your medicines");
  await expect(words).toContainText("- your visits to the doctor");
  await expect(words).not.toContainText("blood pressure book");
  // The backend's words name the person by the name he typed; how they put it is theirs.
  await expect(words).toContainText("Mei");
  const previewed = await words.locator(".lines p").allTextContents();
  await page.getByTestId("invite-agree").click();
  await expect(main).toHaveAttribute("data-stage", "plan");
  await expect(page.getByTestId("plan-status")).toHaveText("They can see those parts now.");
  await expect(gap.first()).not.toHaveAttribute("data-gap", "fam");

  // On the record: his consent in words naming the parts, and a caregiver key no wider.
  const { auth, id } = await profileOf(request, phone);
  const consents = (await (await request.get(`${API}/profiles/${id}/consents`, { headers: auth })).json()) as { purpose: string; wording_text: string }[];
  const sharing = consents.find((each) => each.purpose === "share_with_family");
  // What he read before agreeing is exactly what was kept.
  expect(sharing?.wording_text.split("\n")).toEqual(previewed);
  const keys = (await (await request.get(`${API}/profiles/${id}/keys`, { headers: auth })).json()) as { role: string; scopes: string[]; revoked_at: string | null }[];
  const key = keys.find((each) => each.role === "caregiver" && each.revoked_at === null);
  expect(key?.scopes).toEqual(expect.arrayContaining(["medicines", "visits"]));
  expect(key?.scopes).not.toContain("readings");
  expect(key?.scopes).not.toContain("records");
});
