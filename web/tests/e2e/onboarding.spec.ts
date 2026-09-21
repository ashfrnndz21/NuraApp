import { mkdirSync } from "node:fs";
import { join } from "node:path";
import { expect, test, type APIRequestContext, type Locator, type Page } from "@playwright/test";
import { en } from "../../src/strings/en";
import { API, apiToken, backendClock, captureSpeech, fixClock, freshPhone, nothingDrawnOverLines, seedVisit, signInThroughTheApp } from "./helpers";

/** Checkpoint 11 on a phone-sized screen: onboarding end to end against the real backend —
 *  E01's sitting, settings, word cloud and first week (#117), E02's photos, imports and review
 *  cards, E05's visit list and E12's sharing — with nothing mocked. Both clocks stand at 10 in
 *  the morning in Singapore on Monday 14 September: the phone's by `fixClock`, the backend's
 *  by NURA_FROZEN_CLOCK (playwright.config.ts), so "tomorrow at breakfast" is always Tuesday.
 *  Every line checked is the backend's or the app's own string table. */

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
const photo = (label: string) => ({ name: `${label}.png`, mimeType: "image/png", buffer: placeholder(label) });

const SWITCHES = ["large_text", "high_contrast", "voice_on", "big_targets", "one_thing_per_screen", "read_back", "repeat_prompts"] as const;
const p = en.onboarding.plan;

test.beforeEach(async ({ page, request }) => {
  const clock = await backendClock(request);
  expect(clock.frozen, "start the backend with NURA_FROZEN_CLOCK (see playwright.config.ts)").toBe(true);
  await fixClock(page);
});

/** About you, answered quickly, in his own papers' patient density: one question a screen. */
async function throughAbout(page: Page, { breakfast = true } = {}): Promise<void> {
  await page.getByLabel("The name Nura uses").fill("Pa");
  await page.getByTestId("about-next").click();
  await page.getByTestId("about-lang-en").click();
  await page.getByTestId("decade-1950").click();
  await page.getByLabel("The doctor's name").fill("Dr Tan");
  await page.getByTestId("about-next").click();
  await page.getByTestId(breakfast ? "breakfast-07:30" : "breakfast-not-now").click();
  for (const item of SWITCHES) await page.getByTestId(`${item}-no`).click();
  await page.getByTestId("density-simple").click();
}

async function signedInToOnboarding(page: Page, prefix: string, options: { breakfast?: boolean } = {}): Promise<string> {
  const phone = freshPhone(prefix);
  await captureSpeech(page);
  await signInThroughTheApp(page, phone, "Pa");
  await page.getByTestId("door-for-me").click();
  await page.getByTestId("agree").click();
  await throughAbout(page, options);
  return phone;
}

interface Api {
  auth: { Authorization: string };
  id: string;
  token: string;
}
async function profileOf(request: APIRequestContext, phone: string): Promise<Api> {
  const token = await apiToken(request, phone);
  const auth = { Authorization: `Bearer ${token}` };
  const me = (await (await request.get(`${API}/me`, { headers: auth })).json()) as { profile_id: string };
  return { auth, id: me.profile_id, token };
}

interface Sitting {
  step: string;
  more: string | null;
  questions: { question_id: string; line: string; kept: boolean | null; state_id: string | null; source: string | null; handed_over_to: string | null }[];
}
const sitting = async (request: APIRequestContext, who: Api): Promise<Sitting> =>
  (await (await request.get(`${API}/profiles/${who.id}/biography?language=en`, { headers: who.auth })).json()) as Sitting;

interface Week {
  prompts: { prompt: string; status: string; headline: string | null; line: string | null; capture: string }[];
}
const week = async (request: APIRequestContext, who: Api): Promise<Week> =>
  (await (await request.get(`${API}/profiles/${who.id}/plan?language=en`, { headers: who.auth })).json()) as Week;

/** What a visit's list holds (E05), in the words each question was kept in. */
async function visitList(request: APIRequestContext, who: Api): Promise<{ appointment: string; questions: { text: string; added_by_person_id: string | null }[] }> {
  const visits = (await (await request.get(`${API}/profiles/${who.id}/appointments`, { headers: who.auth })).json()) as { appointment_id: string }[];
  expect(visits.length).toBeGreaterThan(0);
  const appointment = visits[0]!.appointment_id;
  const listed = (await (await request.get(`${API}/profiles/${who.id}/appointments/${appointment}/questions`, { headers: who.auth })).json()) as {
    questions: { text: string; added_by_person_id: string | null }[];
  };
  return { appointment, questions: listed.questions };
}

/** Later on each card until the one wanted is up (each Later waits for the next card: a
 *  second Later on the same gap would retire it). */
async function laterUntil(gap: Locator, wanted: string): Promise<void> {
  for (let n = 0; n < 8; n++) {
    const current = await gap.getAttribute("data-gap");
    if (current === wanted) return;
    await gap.getByTestId("later").click();
    await expect(gap).not.toHaveAttribute("data-gap", current!);
  }
  await expect(gap).toHaveAttribute("data-gap", wanted);
}

const spoken = (page: Page) => page.evaluate(() => (window as unknown as { __spoken: string[] }).__spoken.splice(0));

test("the patient's own onboarding: about you, the cloud, a paper, the read-back, questions, the first week", async ({ page, request }) => {
  test.setTimeout(180_000);
  const phone = freshPhone("+659888");
  await captureSpeech(page);
  await signInThroughTheApp(page, phone, "Pa");
  await page.getByTestId("door-for-me").click();
  await page.getByTestId("agree").click();

  // About you: the sitting's own words lead; one question per screen, patient density, 56px.
  const main = page.locator("main.onboarding");
  await expect(main).toHaveAttribute("data-item", "name");
  await expect(page.locator("html")).toHaveAttribute("data-density", "patient");
  await expect(page.getByRole("heading", { name: "A few things about you" })).toBeVisible();
  await expect(page.getByTestId("about-lead").first()).toHaveText("Tell us which language you like best.");
  await expect(page.getByRole("heading", { name: "What should Nura call you?" })).toBeVisible();
  expect(await nothingDrawnOverLines(main, { minTarget: 56 })).toEqual([]);
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
  await expect(page.getByRole("heading", { name: "Would bigger writing help you?" })).toBeVisible();
  expect(await nothingDrawnOverLines(main, { minTarget: 56 })).toEqual([]);
  for (const item of SWITCHES) await page.getByTestId(`${item}-${item === "read_back" ? "yes" : "no"}`).click();
  await page.getByTestId("density-simple").click();

  // The word cloud (#117's graph): the common words big and on the first screen, no scrolling.
  await expect(main).toHaveAttribute("data-stage", "cloud");
  await expect(page.getByRole("heading", { name: "What is part of your health?" })).toBeVisible();
  const viewport = page.viewportSize()!;
  for (const code of ["high_blood_pressure", "cholesterol", "diabetes", "heart"]) {
    const word = page.getByTestId(`word-${code}`);
    await expect(word).toHaveAttribute("data-size", "3");
    const box = (await word.boundingBox())!;
    expect(box.y + box.height, code).toBeLessThanOrEqual(viewport.height);
    expect(box.height).toBeGreaterThanOrEqual(56);
  }
  expect(await page.evaluate(() => window.scrollY)).toBe(0);
  await expect(page.getByTestId("word-cataract")).toHaveCount(0);

  // A tap picks the plain word and speaks it — only now; what goes with it comes in right
  // after it, and a word two picks point at grows.
  expect(await spoken(page)).toEqual([]);
  await page.getByTestId("word-high_blood_pressure").click();
  await expect(page.getByTestId("word-high_blood_pressure")).toHaveAttribute("aria-pressed", "true");
  expect(await spoken(page)).toEqual(["High blood pressure"]);
  await expect(page.getByTestId("cloud-status")).toHaveText("Nura wrote that down.");
  const order = await page.getByTestId("cloud").locator("button").evaluateAll((all) => all.map((each) => each.getAttribute("data-testid")));
  expect(order.indexOf("word-bp_tablets")).toBe(order.indexOf("word-high_blood_pressure") + 1);
  await expect(page.getByTestId("word-heart_doctor")).toHaveAttribute("data-size", "2");
  await page.getByTestId("word-cholesterol").click();
  await expect(page.getByTestId("word-heart_doctor")).toHaveAttribute("data-size", "3");
  await page.getByTestId("word-bp_tablets").click();
  await spoken(page);

  // "Or just tell me": free text, tagged into the cloud's own words by the backend's tagger —
  // never a new word, never echoed back, only the codes it tagged.
  await page.getByTestId("tell-me-open").click();
  await page.getByRole("textbox", { name: "In your own words" }).fill("my sugar is a bit high");
  await page.getByTestId("tell-me-send").click();
  await expect(page.getByTestId("word-diabetes")).toHaveAttribute("aria-pressed", "true");

  await page.evaluate(() => window.scrollTo(0, 0));
  await page.screenshot({ path: shot("word-cloud") });
  expect(await nothingDrawnOverLines(main, { minTarget: 56 })).toEqual([]);
  await page.getByTestId("cloud-done").click();

  // "Blood pressure tablets" carries a follow-up ("For how long?"): it comes before the
  // papers, one question on its own screen for the patient, his tap the whole answer.
  await expect(main).toHaveAttribute("data-stage", "asks");
  await expect(page.getByTestId("ask-bp_tablets")).toContainText("For how long?");
  await page.getByTestId("option-one_to_five_years").click();

  // The papers step: the sitting's words; the settings and the words saved in one PUT.
  await expect(main).toHaveAttribute("data-stage", "records");
  await expect(page.getByRole("heading", { name: "Now, your papers" })).toBeVisible();
  await expect(page.getByTestId("prompt")).toContainText("Take a photo of each paper you have.");
  await expect(page.getByTestId("photo-input")).toHaveAttribute("capture", "environment");
  const pa = await profileOf(request, phone);
  const saved = (await (await request.get(`${API}/profiles/${pa.id}/settings`, { headers: pa.auth })).json()) as Record<string, unknown>;
  expect(saved.conditions).toEqual(expect.arrayContaining(["high_blood_pressure", "cholesterol", "bp_tablets", "diabetes"]));
  expect(saved).toMatchObject({ preferred_name: "Pa", doctor_name: "Dr Tan", breakfast_time: "07:30", birth_decade: 1950, read_back: true, large_text: false });
  expect(saved.answers).toMatchObject({ bp_tablets: "one_to_five_years" });

  // A photo of the lipid report: the reading screen first — his paper as a bubble, the orb and
  // one status line, then what Nura found — before the full report table (E02, checkpoint 2).
  await page.getByTestId("photo-input").setInputFiles(photo("lipid-panel-2023-09-07"));
  await expect(page.getByTestId("paper-bubble")).toContainText("lipid-panel-2023-09-07.png");
  await expect(page.getByTestId("reading-result")).toBeVisible();
  await page.screenshot({ path: shot("reading-result"), fullPage: true });
  await page.getByTestId("see-report").click();

  const card = page.getByTestId("review-card");
  await expect(card).toContainText("This is a blood test.");
  await expect(card).toContainText(/The paper is dated Thursday,? 7 September 2023\./);
  await expect(page.getByTestId("field-total_cholesterol")).not.toHaveAttribute("data-needs-confirm", "true");
  await expect(page.getByTestId("field-triglycerides")).toHaveAttribute("data-needs-confirm", "true");
  await expect(page.getByTestId("field-triglycerides")).toContainText("The blood fats");
  await expect(page.getByTestId("field-triglycerides").getByTestId("check-this-one")).toBeVisible();
  await page.screenshot({ path: shot("review-card"), fullPage: true });
  expect(await nothingDrawnOverLines(page.locator("main.onboarding"), { minTarget: 56 })).toEqual([]);
  // Every line of this lab report has its own words — never the generic fallback — and a
  // readable value: no line is titled "Another line on the paper" and no line is blank
  // (E02 defect #1 and defect #2).
  const fieldTiles = page.locator('[data-testid^="field-"]');
  const fieldCount = await fieldTiles.count();
  expect(fieldCount).toBeGreaterThan(0);
  for (let at = 0; at < fieldCount; at++) {
    const tile = fieldTiles.nth(at);
    await expect(tile).not.toContainText("Another line on the paper");
    const value = (await tile.locator(".report-value-num").textContent()) ?? "";
    expect(value.trim().length).toBeGreaterThan(0);
  }
  // In the patient density every line has its spoken twin.
  await page.getByTestId("field-triglycerides").getByTestId("hear").click();
  expect(await spoken(page)).toEqual(["The blood fats", "64 mg/dL", "Please check this one."]);

  // Correct the misread blood fats to what the paper says, from the correction sheet; a word
  // is caught first.
  await page.getByTestId("field-triglycerides").getByTestId("check-this-one").click();
  const sheet = page.getByTestId("check-sheet");
  const fats = sheet.locator("input");
  await expect(fats).toHaveValue("64");
  await fats.fill("fifty-four");
  await page.getByTestId("action-sheet-cta").click();
  await expect(sheet.getByTestId("sheet-not-a-number")).toHaveText("Please type the number from the paper.");
  await fats.fill("54");
  await page.getByTestId("action-sheet-cta").click();
  await expect(sheet).toHaveCount(0);
  await page.getByTestId("field-vldl").getByTestId("row-value").click();
  await page.getByTestId("leave-out").click();
  await page.getByTestId("action-sheet-not-now").click();
  await expect(page.getByTestId("field-vldl")).toContainText("Nura will leave this one out.");
  await page.getByTestId("looks-right").click();
  await expect(main).toHaveAttribute("data-stage", "records");
  await expect(page.getByTestId("saved")).toHaveText("Nura wrote it down.");

  // On the record: the correction as typed, the line left out absent, provenance kept.
  const facts = (await (await request.get(`${API}/profiles/${pa.id}/facts?subject=lipid_panel`, { headers: pa.auth })).json()) as {
    attribute: string;
    value: unknown;
    artifact_id: string | null;
  }[];
  const byName = new Map(facts.map((fact) => [fact.attribute, fact]));
  expect(byName.get("triglycerides")?.value).toBe(54);
  expect(byName.get("total_cholesterol")?.value).toBe(230);
  expect(byName.has("vldl")).toBe(false);
  for (const fact of facts) expect(fact.artifact_id).toBeTruthy();

  // "That is all my papers": the read-back, one backend line per screen, Yes / No on paper.
  await page.getByTestId("all-done").click();
  await expect(main).toHaveAttribute("data-stage", "readBack");
  await expect(page.getByRole("heading", { name: "Here is what Nura understood" })).toBeVisible();
  const line = page.getByTestId("readback-line");
  await expect(line).toHaveCount(1);
  await expect(line).toContainText("You told us: High blood pressure.");
  await expect(line).toContainText(/This is 1 of \d+\./);
  const total = Number(/This is 1 of (\d+)\./.exec((await line.textContent()) ?? "")![1]);
  expect(await nothingDrawnOverLines(main, { minTarget: 56 })).toEqual([]);
  await line.getByTestId("readback-yes").click();
  await expect(line).toContainText("You told us: High cholesterol.");
  await line.getByTestId("readback-no").click();
  await expect(page.getByTestId("readback-ack")).toHaveText(/\S/);
  const read: string[] = [];
  for (let n = 3; n <= total; n++) {
    await expect(line).toContainText(`This is ${n} of ${total}.`);
    read.push((await line.textContent()) ?? "");
    await line.getByTestId("readback-yes").click();
  }
  expect(read.join("\n")).toContain("Your doctor is Dr Tan.");
  expect(read.join("\n")).toContain("Your cholesterol was 230 on");

  // The questions the papers raised: one per screen, each with its State and its source line.
  await expect(main).toHaveAttribute("data-stage", "questions");
  await expect(page.getByRole("heading", { name: "A few questions about your papers" })).toBeVisible();
  const asked = await sitting(request, pa);
  expect(asked.questions.length).toBeGreaterThan(1);
  const question = page.getByTestId("question");
  await expect(question).toHaveCount(1);
  await expect(question).toContainText(asked.questions[0]!.line);
  await expect(question).toHaveAttribute("data-state-id", asked.questions[0]!.state_id!);
  await expect(question.getByTestId("source")).toHaveText(asked.questions[0]!.source!);
  if (asked.more) await expect(page.getByTestId("questions-more")).toHaveText(asked.more);
  expect(await nothingDrawnOverLines(main, { minTarget: 56 })).toEqual([]);
  await question.getByTestId("keep").click();
  await expect(page.getByTestId("question-ack")).toHaveText("Nura will keep this one for the visit.");
  await expect(question).toContainText(asked.questions[1]!.line);
  await question.getByTestId("not-this").click();
  const count = asked.questions.length;
  for (let n = 3; n <= count; n++) {
    await expect(question).toContainText(`This is ${n} of ${count}.`);
    await question.getByTestId("keep").click();
  }
  // No visit is booked: the kept question waits on the sitting.
  const kept = (await sitting(request, pa)).questions[0]!;
  expect(kept).toMatchObject({ kept: true, handed_over_to: null });

  // The first week: the sitting's close, then one card for the patient, and how many follow.
  await expect(main).toHaveAttribute("data-stage", "plan");
  await expect(page.getByRole("heading", { name: "Your app is ready" })).toBeVisible();
  await expect(page.getByTestId("done-prompt")).toContainText("Your Today page comes from what you told us.");
  await expect(page.getByTestId("summary")).toContainText("Nura saved one of your papers.");
  await expect(page.getByTestId("summary")).toContainText("You said one line was not right.");
  const plan = await week(request, pa);
  const pendingCodes = plan.prompts.filter((each) => each.status === "pending").map((each) => each.prompt);
  expect(pendingCodes).toContain("medicines");
  const first = plan.prompts.find((each) => each.prompt === pendingCodes[0])!;
  const gap = page.getByTestId("gap-card");
  await expect(gap).toHaveCount(1);
  await expect(gap).toHaveAttribute("data-gap", first.prompt);
  await expect(gap).toContainText(first.headline!);
  await expect(gap).toContainText(first.line!);
  await expect(gap).toContainText(/Nura will ask for this on Tuesday/);
  await expect(page.getByTestId("more-after")).toHaveText(/There (is 1 more|are \d+ more) after that\./);
  await page.screenshot({ path: shot("first-week"), fullPage: true });
  expect(await nothingDrawnOverLines(main, { minTarget: 56 })).toEqual([]);
  // Later sends it to the back of the week; the next one comes.
  await gap.getByTestId("later").click();
  await expect(page.getByTestId("plan-status")).toHaveText(p.laterSaid);
  await expect(gap).not.toHaveAttribute("data-gap", first.prompt);
  // Do it now on the tablets: the camera, the card, the yes, and back here with that gap closed.
  await laterUntil(gap, "medicines");
  await gap.getByTestId("photo-input").setInputFiles(photo("warfarin-label-2024-03-12"));
  await expect(page.getByTestId("review-card")).toContainText("This is a medicine label.");
  // A structured line (the dose) still needs him, but cannot be retyped: the sheet offers only
  // what Nura read and "Leave this one out".
  await page.getByTestId("field-dose").getByTestId("check-this-one").click();
  await expect(page.getByTestId("check-sheet").locator("input")).toHaveCount(0);
  await expect(page.getByTestId("check-sheet")).toContainText(en.onboarding.records.leaveOut);
  await page.getByTestId("action-sheet-not-now").click();
  await page.getByTestId("looks-right").click();
  await expect(main).toHaveAttribute("data-stage", "plan");
  await expect(gap).not.toHaveAttribute("data-gap", "medicines");
  expect((await week(request, pa)).prompts.find((each) => each.prompt === "medicines")?.status).toBe("done");

  // A visit booked now: the question he kept moves onto its list (E05), in his words.
  await seedVisit(request, pa.token, pa.id);
  const list = await visitList(request, pa);
  expect(list.questions.map((each) => each.text)).toContain(kept.line);
  // The sitting names the visit it went to while that gap is still open (the label may have
  // closed it: the tablets were the first question).
  const still = (await sitting(request, pa)).questions.find((each) => each.question_id === kept.question_id);
  if (still) expect(still.handed_over_to).toBe(list.appointment);

  // Nothing sideways, anywhere on the way.
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= document.documentElement.clientWidth)).toBe(true);

  // Today, and nothing of onboarding kept on the phone.
  await page.getByTestId("open-nura").click();
  await expect(page.locator("nav.tabbar")).toBeVisible();
  const stored = await page.evaluate(async () => {
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
  expect(stored.local).toBe(0);
  expect(stored.session).toBe(0);
  // Today's own copies, not onboarding's: `emergency.` is the emergency card Today keeps for
  // offline, `queue.` the taps held while offline (E00-08), `nfw.` the not-feeling-well cards
  // for no network (ADR 0012) — each bound to the key that read it and deleted with the Today
  // page on a refusal, a switch of papers and sign-out.
  for (const key of stored.keys) expect(key).toMatch(/^(session\.|device\.|today\.|proud\.|takenDays\.|feed\.|emergency\.|queue\.|nfw\.)/);
});

test("the caregiver density, for a chief setting up her father", async ({ page }) => {
  test.setTimeout(120_000);
  const phone = freshPhone("+659889");
  await captureSpeech(page);
  await signInThroughTheApp(page, phone, "Ash");
  await page.getByTestId("door-for-someone").click();
  await page.getByLabel("Their name").fill("Pa");
  await page.getByLabel("Their phone number").fill(freshPhone("+659887"));
  // Who she is to him is a choice, never typed (E01-01).
  await page.getByTestId("relationship-daughter").click();
  await page.getByText("They asked you to do this.").click();
  await page.getByRole("button", { name: "Set it up" }).click();

  // Caregiver density: every question on one page, in his name; her phone keeps her language.
  const main = page.locator("main.onboarding");
  await expect(page.locator("html")).toHaveAttribute("data-density", "caregiver");
  await expect(page.getByRole("heading", { name: "A few things about Pa" })).toBeVisible();
  await expect(page.getByTestId("about-name")).toBeVisible();
  await expect(page.getByTestId("about-large_text")).toContainText("Would bigger writing help Pa?");
  await page.getByTestId("about-lang-ms").click();
  await expect(page.locator("html")).toHaveAttribute("lang", "en");
  await expect(page.getByTestId("about-lang-ms")).toHaveAttribute("aria-pressed", "true");
  await page.getByTestId("decade-1940").click();
  await page.getByLabel("The doctor's name").fill("Dr Lim");
  await page.getByTestId("breakfast-07:00").click();
  await page.getByTestId("large_text-yes").click();
  expect(await nothingDrawnOverLines(main)).toEqual([]);
  await page.getByTestId("about-next").click();

  await expect(page.getByRole("heading", { name: "What is part of Pa's health?" })).toBeVisible();
  await page.getByTestId("word-high_blood_pressure").click();
  await page.getByTestId("word-bp_at_home").click();
  await page.screenshot({ path: shot("word-cloud-caregiver") });
  await page.getByTestId("cloud-done").click();

  // The caregiver density shows every follow-up on one page; she moves on without answering.
  await expect(main).toHaveAttribute("data-stage", "asks");
  await page.getByTestId("asks-next").click();
  await expect(page.getByRole("heading", { name: "Now, Pa's papers" })).toBeVisible();

  // A paper in the caregiver density: the card's header speaks, its lines do not each.
  await page.getByTestId("photo-input").setInputFiles(photo("lipid-panel-2023-09-07"));
  await expect(page.getByTestId("reading-result")).toBeVisible();
  await page.getByTestId("see-report").click();
  await expect(page.getByTestId("review-card").getByTestId("hear")).toHaveCount(1);
  await expect(page.getByTestId("field-triglycerides").getByTestId("hear")).toHaveCount(0);
  expect(await nothingDrawnOverLines(main)).toEqual([]);
  await page.getByTestId("looks-right").click();
  await expect(page.getByTestId("saved")).toBeVisible();

  // The read-back as a list, each line with its own Yes and No — in her language, not his.
  await page.getByTestId("all-done").click();
  const lines = page.getByTestId("readback-line");
  await expect(lines.first()).toContainText("You told us: High blood pressure.");
  expect(await lines.count()).toBeGreaterThan(2);
  await lines.nth(1).getByTestId("readback-no").click();
  await expect(lines.nth(1).getByTestId("readback-no")).toHaveAttribute("aria-pressed", "true");
  await expect(lines.first()).toContainText("You told us: High blood pressure.");
  for (let n = 0; n < (await lines.count()); n++) {
    if (n === 1) continue;
    await lines.nth(n).getByTestId("readback-yes").click();
    await expect(lines.nth(n).getByTestId("readback-yes")).toHaveAttribute("aria-pressed", "true");
  }
  await page.getByTestId("readback-next").click();

  // The questions as a list, then the whole first week, then Today.
  await expect(page.getByRole("heading", { name: "Pa's papers raised a few questions" })).toBeVisible();
  await expect(page.getByTestId("question").first()).toContainText("?");
  await page.getByTestId("questions-next").click();
  await expect(page.getByRole("heading", { name: p.title })).toBeVisible();
  const gaps = page.getByTestId("gap-card");
  await expect(gaps.first()).toContainText(/With (it|them), Nura/);
  expect(await gaps.count()).toBeGreaterThan(1);
  await expect(page.getByTestId("more-after")).toHaveCount(0);
  expect(await nothingDrawnOverLines(main)).toEqual([]);
  await page.getByTestId("open-nura").click();
  await expect(page.locator("nav.tabbar")).toBeVisible();
  await expect(page.locator("html")).toHaveAttribute("data-density", "caregiver");
});

test("his language takes effect the moment he picks it", async ({ page }) => {
  const phone = freshPhone("+659886");
  await signInThroughTheApp(page, phone, "Pa");
  await page.getByTestId("door-for-me").click();
  await page.getByTestId("agree").click();
  await page.getByTestId("about-next").click();
  await page.getByTestId("about-lang-ms").click();
  await expect(page.locator("html")).toHaveAttribute("lang", "ms");
  await expect(page.getByRole("heading", { name: "Bila anda dilahirkan?" })).toBeVisible();
});

test("papers of every kind: a hospital letter as a PDF, a page that is not a health paper, a line Nura could not read", async ({ page, request }) => {
  const phone = await signedInToOnboarding(page, "+659885");
  await page.getByTestId("word-hospital_last_year").click();
  await page.getByTestId("cloud-done").click();
  const main = page.locator("main.onboarding");
  await expect(main).toHaveAttribute("data-stage", "records");

  // A PDF that is not a health paper: the backend reads it and says so; nothing to say yes to.
  await page.getByTestId("file-input").setInputFiles({ name: "receipt.pdf", mimeType: "application/pdf", buffer: placeholderPdf("receipt-2026-09-01") });
  await expect(page.getByTestId("review-unreadable")).toBeVisible();
  await expect(page.getByTestId("looks-right")).toHaveCount(0);
  await page.getByRole("button", { name: "Go back" }).click();

  // The hospital letter as a PDF goes to /imports and comes back as a card like any photo.
  await page.getByTestId("file-input").setInputFiles({ name: "letter.pdf", mimeType: "application/pdf", buffer: placeholderPdf("discharge-letter-2026-08-20") });
  await expect(page.getByTestId("reading-result")).toBeVisible();
  await page.getByTestId("see-report").click();
  await expect(page.getByTestId("review-card")).toContainText("This is a hospital letter.");
  await expect(page.getByTestId("field-reason")).toContainText("Why you were in hospital");
  await spoken(page); // what the cloud's tap said earlier
  await page.getByTestId("field-reason").getByTestId("hear").click();
  expect((await spoken(page)).slice(0, 2)).toEqual(["Why you were in hospital", "heart failure"]);
  await page.getByTestId("looks-right").click();
  await expect(page.getByTestId("saved")).toHaveText("Nura wrote it down.");

  // A clinic slip with a line Nura could not read: never confirmed as read; he types it, from
  // the correction sheet "Check this one" opens.
  await page.getByTestId("photo-input").setInputFiles(photo("clinic-slip-2026-09-10"));
  await page.getByTestId("see-report").click();
  const frequency = page.getByTestId("field-frequency");
  await expect(frequency.getByTestId("check-this-one")).toBeVisible();
  expect(await nothingDrawnOverLines(main, { minTarget: 56 })).toEqual([]);
  await frequency.getByTestId("check-this-one").click();
  const sheet = page.getByTestId("check-sheet");
  await expect(sheet).toContainText("Nura could not read this one.");
  await expect(sheet.locator("input")).toHaveValue("");
  await page.getByTestId("action-sheet-cta").click();
  await expect(sheet.getByTestId("sheet-not-a-number")).toHaveText("Please type what the paper says.");
  await sheet.locator("input").fill("twice a day");
  await page.getByTestId("action-sheet-cta").click();
  await expect(sheet).toHaveCount(0);
  await page.getByTestId("looks-right").click();
  await expect(main).toHaveAttribute("data-stage", "records");

  // On the record: the letter's reason, and the frequency exactly as he typed it; both papers
  // are the sitting's.
  const pa = await profileOf(request, phone);
  const facts = (await (await request.get(`${API}/profiles/${pa.id}/facts`, { headers: pa.auth })).json()) as { subject: string; attribute: string; value: unknown }[];
  expect(facts.find((fact) => fact.subject === "discharge" && fact.attribute === "reason")?.value).toBe("heart failure");
  expect(facts.find((fact) => fact.attribute === "frequency")?.value).toBe("twice a day");
  const papers = (await (await request.get(`${API}/profiles/${pa.id}/biography?language=en`, { headers: pa.auth })).json()) as { papers: unknown[]; open_cards: number };
  expect(papers.papers).toHaveLength(2);
  expect(papers.open_cards).toBe(0);
});

test("the Ready screen's other actions: breakfast from its card, and one person let in", async ({ page, request }) => {
  test.setTimeout(120_000);
  const phone = await signedInToOnboarding(page, "+659884", { breakfast: false });
  await page.getByTestId("word-allergies").click();
  await page.getByTestId("word-medicine_allergy").click();
  await page.getByTestId("cloud-done").click();
  const main = page.locator("main.onboarding");
  // "Allergic to a medicine" carries a follow-up ("Which one?"); his tap is the whole answer.
  await expect(main).toHaveAttribute("data-stage", "asks");
  await page.getByTestId("option-not_sure").click();
  // No papers today: the sitting closes straight away, and says so.
  await page.getByTestId("all-done").click();
  await expect(main).toHaveAttribute("data-stage", "plan");
  await expect(page.getByTestId("summary")).toContainText("No papers were added this time.");

  // Which medicine he is allergic to has no way in yet: Later only, never a dead button.
  const gap = page.getByTestId("gap-card");
  await laterUntil(gap, "allergy_which");
  await expect(gap.getByTestId("do-it-now")).toHaveCount(0);
  // His breakfast time: the one question, then back here with that gap closed.
  await laterUntil(gap, "meal_times");
  await expect(gap.getByTestId("do-it-now")).toHaveText("Today, tap the time you have breakfast.");
  await gap.getByTestId("do-it-now").click();
  await expect(main).toHaveAttribute("data-stage", "about");
  await page.getByTestId("breakfast-08:00").click();
  await expect(main).toHaveAttribute("data-stage", "plan");
  await expect(gap).not.toHaveAttribute("data-gap", "meal_times");
  const pa = await profileOf(request, phone);
  expect((await week(request, pa)).prompts.find((each) => each.prompt === "meal_times")?.status).toBe("done");

  // Someone to see his papers: E12's flow, the backend's words, his one yes.
  await laterUntil(gap, "someone_to_see");
  await gap.getByTestId("do-it-now").click();
  const mei = freshPhone("+659883");
  await page.getByLabel("Their name").fill("Mei");
  await page.getByLabel("Their phone number").fill(mei);
  await page.getByTestId("invite-relationship-daughter").click();
  await page.getByTestId("invite-next").click();
  await page.getByTestId("part-medicines").click();
  await page.getByTestId("part-visits").click();
  await page.getByTestId("invite-see-words").click();
  const words = page.getByTestId("invite-words");
  await expect(words).toContainText("- your medicines");
  await expect(words).toContainText("- your visits to the doctor");
  await expect(words).not.toContainText("blood pressure book");
  // The backend's words name the person by the name he typed.
  await expect(words).toContainText("Mei");
  expect(await nothingDrawnOverLines(main, { minTarget: 56 })).toEqual([]);
  const previewed = await words.locator(".lines p").allTextContents();
  await page.getByTestId("invite-agree").click();
  await expect(main).toHaveAttribute("data-stage", "plan");
  await expect(page.getByTestId("plan-status")).toHaveText("They can see those parts now.");
  await expect(gap.first()).not.toHaveAttribute("data-gap", "someone_to_see");

  // On the record: his consent in exactly the words he read, and a caregiver key no wider.
  const consents = (await (await request.get(`${API}/profiles/${pa.id}/consents`, { headers: pa.auth })).json()) as { purpose: string; wording_text: string }[];
  const sharing = consents.find((each) => each.purpose === "share_with_family");
  expect(sharing?.wording_text.split("\n")).toEqual(previewed);
  const keys = (await (await request.get(`${API}/profiles/${pa.id}/keys`, { headers: pa.auth })).json()) as { role: string; scopes: string[]; revoked_at: string | null }[];
  const key = keys.find((each) => each.role === "caregiver" && each.revoked_at === null);
  expect(key?.scopes).toEqual(expect.arrayContaining(["medicines", "visits"]));
  expect(key?.scopes).not.toContain("readings");
  expect(key?.scopes).not.toContain("records");
});

test("a question kept with a visit booked goes on that visit's list at once (E05)", async ({ page, request }) => {
  test.setTimeout(120_000);
  const phone = await signedInToOnboarding(page, "+659882");
  await page.getByTestId("word-hospital_last_year").click();
  await page.getByTestId("cloud-done").click();
  const main = page.locator("main.onboarding");
  await expect(main).toHaveAttribute("data-stage", "records");

  // A visit is booked the way the family would: the doctor, then the visit, each with its yes.
  const pa = await profileOf(request, phone);
  await seedVisit(request, pa.token, pa.id);

  // One paper, the read-back, then he keeps the first question the sitting raised.
  await page.getByTestId("photo-input").setInputFiles(photo("lipid-panel-2023-09-07"));
  await page.getByTestId("see-report").click();
  await page.getByTestId("looks-right").click();
  await expect(page.getByTestId("saved")).toBeVisible();
  await page.getByTestId("all-done").click();
  const line = page.getByTestId("readback-line");
  await expect(line).toContainText(/This is 1 of \d+\./);
  const total = Number(/This is 1 of (\d+)\./.exec((await line.textContent()) ?? "")![1]);
  for (let n = 1; n <= total; n++) {
    await expect(line).toContainText(`This is ${n} of ${total}.`);
    await line.getByTestId("readback-yes").click();
  }
  await expect(main).toHaveAttribute("data-stage", "questions");
  const asked = await sitting(request, pa);
  const question = page.getByTestId("question");
  await expect(question).toContainText(asked.questions[0]!.line);
  await question.getByTestId("keep").click();
  await expect(page.getByTestId("question-ack")).toHaveText("Nura will keep this one for the visit.");

  // On the visit's list, in exactly the words he kept, added by him — never composed here.
  const list = await visitList(request, pa);
  const kept = list.questions.find((each) => each.text === asked.questions[0]!.line);
  expect(kept, JSON.stringify(list.questions)).toBeTruthy();
  expect(kept!.added_by_person_id).toBeTruthy();
  expect((await sitting(request, pa)).questions[0]!.handed_over_to).toBe(list.appointment);
});

/** The owner's report: he signed in on a fresh number and landed on Home, with nothing on
 *  it — his account had no name at all. A bare profile (no name typed anywhere: not at sign
 *  in, not on the "for me" door) must go to onboarding first, and stay there through a
 *  relaunch, until it is finished (E01-01's gate). Once he has a name, he lands on Home,
 *  never back in onboarding. */
test("a bare profile always opens onboarding, never Home, and stays that way through a relaunch (E01-01)", async ({ page }) => {
  const phone = freshPhone("+659883");
  await captureSpeech(page);
  // No name at sign in, and none on the "for me" door either: nothing types his name anywhere.
  await signInThroughTheApp(page, phone, "");
  await page.getByTestId("door-for-me").click();
  await page.getByTestId("agree").click();

  const main = page.locator("main.onboarding");
  await expect(main).toHaveAttribute("data-stage", "about");
  await expect(page.locator("nav.tabbar")).toHaveCount(0);

  // A relaunch — closing the app mid-way and opening it again — restores the session and must
  // land him back in onboarding, not on Home with nothing on it: the bug as the owner saw it.
  await page.reload();
  await expect(main).toHaveAttribute("data-stage", "about");
  await expect(page.locator("nav.tabbar")).toHaveCount(0);

  // He gives his name; onboarding still has more to ask (About you has more of its own
  // questions before the cloud), so he stays in it, not Home.
  await page.getByLabel("The name Nura uses").fill("Pa");
  await page.getByTestId("about-next").click();
  await expect(main).not.toHaveAttribute("data-item", "name");
  await expect(page.locator("nav.tabbar")).toHaveCount(0);
});
