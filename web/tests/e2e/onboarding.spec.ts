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

  // A PDF: the live backend refuses it, and he reads that in one plain sentence.
  await page.getByTestId("file-input").setInputFiles({ name: "letter.pdf", mimeType: "application/pdf", buffer: Buffer.from("%PDF-1.4\n%nura\n") });
  const notAPhoto = en.refusals.NotAPhoto!;
  for (const sentence of typeof notAPhoto === "string" ? [notAPhoto] : notAPhoto) await expect(page.getByTestId("notice")).toContainText(sentence);
  await expect(page.getByTestId("notice")).not.toContainText("NotAPhoto");

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

  // No papers today: the questions and the whole gap list, then Today.
  await page.getByTestId("all-done").click();
  await expect(page.getByTestId("question")).toContainText("Ask Dr Lim for a copy of your last blood test.");
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
