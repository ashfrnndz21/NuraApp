import { readFileSync } from "node:fs";
import { expect, test, type Browser, type Page } from "@playwright/test";
import { BASE_URL, FROZEN_CLOCK } from "../../playwright.config";
import { API, apiToken, backendClock, fixClock, freshPhone, seedFeed, seedVisit, signInThroughTheApp } from "./helpers";
import { auth, caregiverScreenOk, ICS, openFamilyPart, patientScreenOk, runTriggersAt, seedFamily, seedProposals, type Family, type Person } from "./familySeed";

/** Checkpoint 26's web half: Family, against `make dev` serving the build, both clocks at 10 in
 *  the morning in Singapore on Monday 14 September. Pa reads it in the patient density on a
 *  phone; Mei, Kit and Siti in the caregiver density at 360 by 640 (E15-03). Every line about
 *  his record on these screens is the backend's; the refusals are its too. */

test.beforeAll(async ({ request }) => {
  const backend = await backendClock(request);
  if (!backend.frozen || Date.parse(backend.now) !== Date.parse(FROZEN_CLOCK)) {
    throw new Error(`the backend's clock is not frozen at ${FROZEN_CLOCK} (it says ${JSON.stringify(backend)})`);
  }
});

test.beforeEach(async ({ page }) => {
  await fixClock(page);
});

async function signIn(page: Page, who: Person, owner: boolean): Promise<void> {
  await signInThroughTheApp(page, who.phone, who.name);
  if (!owner) await page.getByTestId("door-key").click();
  await expect(page.getByTestId("tab-family")).toBeVisible();
}

/** Someone else, on a browser of their own, at 360 by 640. */
async function secondPhone(browser: Browser): Promise<Page> {
  const context = await browser.newContext({ baseURL: BASE_URL, viewport: { width: 360, height: 640 }, timezoneId: "Asia/Singapore", serviceWorkers: "allow" });
  const page = await context.newPage();
  await fixClock(page);
  return page;
}

const back = (page: Page) => page.getByRole("button", { name: "Go back" }).click();

test("the nav: Today, Papers (the Record, W5), Family, Me", async ({ page, request }) => {
  const family = await seedFamily(request);
  await signIn(page, family.pa, true);
  await expect(page.locator("nav.tabbar button")).toHaveText(["Today", "Papers", "Family", "Me"]);
});

test("Pa's Family, one thing a screen: his circle, his trail, a part kept to himself, and Mei refused on his trail", async ({ page, request }) => {
  const family = await seedFamily(request);
  await signIn(page, family.pa, true);
  await page.getByTestId("tab-family").click();
  await expect(page.locator("html")).toHaveAttribute("data-density", "patient");
  const circle = page.getByTestId("circle");
  await expect(circle).toContainText("Who can see your papers");
  await expect(circle.getByTestId("grant-lines").filter({ hasText: "Mei" })).toBeVisible();
  await expect(circle.getByTestId("grant-lines").filter({ hasText: "Kit" })).toBeVisible();
  // Adding and granting access is his own selection, in his own density (#177) — the rest
  // of the chief's arrangements (the roster, messages, the week's numbers) stay hers.
  await expect(page.getByTestId("open-keys")).toBeVisible();
  await expect(page.getByTestId("open-roster")).toHaveCount(0);
  expect(await patientScreenOk(page)).toEqual([]);

  // Mei reads his notes as his chief, before he keeps them to himself.
  expect((await request.get(`${API}/profiles/${family.profileId}/notes`, { headers: auth(family.mei.token) })).status()).toBe(200);

  await page.getByTestId("open-onlyMe").click();
  await page.getByTestId("only-me-notes").click();
  await expect(page.getByTestId("only-me-confirm")).toContainText("Private notes");
  expect(await patientScreenOk(page)).toEqual([]);
  await page.getByTestId("only-me-yes").click();
  await expect(page.getByTestId("only-me-notes")).toHaveAttribute("aria-pressed", "true");
  await expect(page.getByTestId("only-me-notes")).toContainText("Only you");
  expect(await patientScreenOk(page)).toEqual([]);

  // Mei's next read is refused at once, and it is on his trail in his words.
  const hers = await request.get(`${API}/profiles/${family.profileId}/notes`, { headers: auth(family.mei.token) });
  expect(hers.status()).toBe(403);
  expect(((await hers.json()) as { refusal: string }).refusal).toBe("OutOfScope");
  await back(page);
  await page.getByTestId("open-trail").click();
  const trail = page.getByTestId("family-trail");
  await expect(trail.getByTestId("trail-day").first()).toContainText("Monday 14 September");
  await expect(trail).toContainText("Mei asked to see your private notes on Monday 14 September.");
  await expect(trail).not.toContainText(/OutOfScope|notes_|[0-9a-f]{8}-[0-9a-f]{4}/);
  expect(await patientScreenOk(page)).toEqual([]);
});

test("Pa adds Priya himself on the Family Keys screen, and she can ask against his record at once", async ({ page, request, browser }) => {
  // The exact bug this proves fixed: the Family "Give someone a key" screen used to cut a
  // key straight away, for a phone number nobody had ever let in — refused every time, for
  // anybody new (`ConsentWithheld`). Now the owner reads the backend's own words for exactly
  // the parts and the role, agrees, and only then is the key cut.
  const pa = await seedFeed(request);
  await signInThroughTheApp(page, pa.phone, "Pa");
  await expect(page.getByTestId("proud")).toBeVisible();

  const priyaPhone = freshPhone("+659777");
  await page.getByTestId("tab-family").click();
  const rolePresets = page.waitForResponse((res) => res.url().includes("/family/roles") && res.ok());
  await page.getByTestId("open-keys").click();
  await rolePresets; // the role's own preset parts and window, before a role is chosen
  await page.getByLabel("Their name").fill("Priya");
  await page.getByLabel("Their phone number").fill(priyaPhone);
  await page.getByTestId("role-caregiver").click();
  await expect(page.getByTestId("role-lines")).toContainText("Priya");
  await expect(page.getByTestId("new-part-medicines")).toHaveAttribute("aria-pressed", "true");
  // Owner only: the sharing agreement is his own yes, so he reads the words first.
  await page.getByTestId("see-words").click();
  const words = page.getByTestId("new-words");
  await expect(words).toContainText("Priya");
  await expect(words).toContainText("your questions to Nura");
  expect(await patientScreenOk(page)).toEqual([]);
  await page.getByTestId("agree-key").click();
  const grant = page.getByTestId("grant").filter({ hasText: "Priya" });
  await expect(grant).toBeVisible();

  // Priya, on a browser of her own, registers only now — nothing about her existed before Pa
  // named her number — and her very first look at the doors already lists Pa: no reload, no
  // second sign-in, no job to wait for.
  const priyaPage = await secondPhone(browser);
  await signIn(priyaPage, { phone: priyaPhone, token: "", personId: "", name: "Priya" }, false);

  // She asks against Pa's own record and reads back a cited answer, over her own key.
  await priyaPage.getByTestId("open-feed").click();
  await expect(priyaPage.getByTestId("pager")).toBeVisible();
  const reading = priyaPage.locator("article.feed-card[data-type=reading]").first();
  await reading.scrollIntoViewIfNeeded();
  await reading.getByTestId("action-ask").click();
  const asking = priyaPage.getByTestId("ask-screen");
  await asking.getByLabel("Your question").fill("What was my blood pressure?");
  const [asked] = await Promise.all([
    priyaPage.waitForRequest((req) => req.method() === "POST" && req.url().endsWith(`/profiles/${pa.profileId}/ask`)),
    asking.getByTestId("ask-send").click(),
  ]);
  expect(asked.postDataJSON()).toMatchObject({ question: "What was my blood pressure?" });
  await expect(asking.getByTestId("answer")).toContainText("138");
  await priyaPage.context().close();
});

test("changing what a key would open while the words for it are still on the wire never leaves a stale preview on screen", async ({ page, request }) => {
  // The name, phone, parts and window are disabled the moment the request is sent — so this
  // walks the one thing that is still reachable while it is in flight: the role pills, which
  // reset the parts and the window underneath it (`choose()`). A caregiver's words landing
  // late, after he has already moved to viewer, must never be shown as if they were viewer's.
  const pa = await seedFeed(request);
  await signInThroughTheApp(page, pa.phone, "Pa");
  await page.getByTestId("tab-family").click();
  const rolePresets = page.waitForResponse((res) => res.url().includes("/family/roles") && res.ok());
  await page.getByTestId("open-keys").click();
  await rolePresets;
  await page.getByLabel("Their name").fill("Priya");
  await page.getByLabel("Their phone number").fill(freshPhone("+659777"));
  await page.getByTestId("role-caregiver").click();
  await expect(page.getByTestId("new-part-medicines")).toHaveAttribute("aria-pressed", "true");
  await expect(page.getByTestId("new-part-ask")).toHaveAttribute("aria-pressed", "true");

  // The preview request is held on the wire until the test releases it.
  let release: (() => void) | null = null;
  const held = new Promise<void>((resolve) => (release = resolve));
  const previewUrl = /\/consents\/sharing\/preview$/;
  let seen = 0;
  await page.route(previewUrl, async (route) => {
    seen += 1;
    if (seen === 1) await held;
    await route.continue();
  });
  const asCaregiver = page.waitForRequest((req) => req.method() === "POST" && previewUrl.test(req.url()));
  await page.getByTestId("see-words").click();
  expect((await asCaregiver).postDataJSON()).toMatchObject({ scopes: expect.arrayContaining(["ask"]) });

  // While the caregiver's words are in flight: the four fields are locked, but the role is
  // not, and taking it to viewer — narrower, and no `ask` — is exactly what invalidates them.
  await expect(page.getByLabel("Their name")).toBeDisabled();
  await expect(page.getByLabel("Their phone number")).toBeDisabled();
  await expect(page.getByTestId("new-part-medicines")).toBeDisabled();
  await expect(page.getByTestId("new-window-always")).toBeDisabled();
  await expect(page.getByTestId("see-words")).toBeDisabled();
  await page.getByTestId("role-viewer").click();
  await expect(page.getByTestId("new-part-ask")).toHaveAttribute("aria-pressed", "false");

  release!();
  // The stale answer, rendered for the caregiver's parts, never reaches the screen.
  await page.waitForResponse((res) => previewUrl.test(res.url()) && res.ok());
  await expect(page.getByTestId("new-words")).toHaveCount(0);
  await expect(page.getByTestId("see-words")).toBeEnabled();

  // Asking again, for viewer, is his — and it is viewer's words, not the caregiver's.
  const asViewer = page.waitForRequest((req) => req.method() === "POST" && previewUrl.test(req.url()));
  await page.getByTestId("see-words").click();
  expect((await asViewer).postDataJSON()).toMatchObject({ scopes: expect.not.arrayContaining(["ask"]) });
  await expect(page.getByTestId("new-words")).toBeVisible();
  await expect(page.getByTestId("new-words")).not.toContainText("your questions to Nura");
});

test("Pa stops letting Kit in after reading what it will do, Kit is out at once, and the record is his to print", async ({ page, request }) => {
  const family = await seedFamily(request);
  expect((await request.get(`${API}/profiles/${family.profileId}/medicines`, { headers: auth(family.kit.token) })).status()).toBe(200);
  await signIn(page, family.pa, true);
  await page.getByTestId("tab-family").click();
  await page.getByTestId("open-consents").click();
  // Keeping his papers is stopped by closing his account (#143): the backend says what closing
  // means and when his papers go; he does not say yes here.
  const keeping = page.getByTestId("consent").filter({ hasText: "Nura keeps your papers" });
  await keeping.getByTestId("close-account").click();
  await expect(page.getByTestId("stop-lines")).toContainText("Nura will stop keeping your papers.");
  await expect(page.getByTestId("stop-lines")).toContainText("Until then, you can change your mind.");
  await expect(page.getByTestId("close-yes")).toHaveText("Yes, close my account");
  await page.getByTestId("stop-cancel").click();
  const kits = page.getByTestId("consent").filter({ hasText: "Kit" });
  await expect(kits.getByTestId("consent-words")).toContainText("Kit can see these parts:");
  expect(await patientScreenOk(page)).toEqual([]);
  await kits.getByTestId("stop").click();
  await expect(page.getByTestId("stop-lines")).toContainText("If you stop this, Kit cannot see your papers.");
  await expect(page.getByTestId("consent")).toHaveCount(0); // one thing on the screen: the yes
  expect(await patientScreenOk(page)).toEqual([]);
  await page.getByTestId("stop-yes").click();
  await expect(page.getByTestId("stopped")).toContainText("Kit cannot see your papers now.");
  await expect(page.getByTestId("consent").filter({ hasText: "Kit" })).toHaveCount(0);

  const refused = await request.get(`${API}/profiles/${family.profileId}/medicines`, { headers: auth(family.kit.token) });
  expect(refused.status()).toBe(403);
  expect(((await refused.json()) as { refusal: string }).refusal).toBe("NoKey");

  await page.getByTestId("open-record").click();
  await expect(page.frameLocator('[data-testid="record-page"]').locator("h1")).toHaveText("What you said yes to");
  const saving = page.waitForEvent("download");
  await page.getByTestId("save-record").click();
  const saved = readFileSync((await (await saving).path())!, "utf8");
  expect(saved).toContain("What you said yes to");
  expect(saved).toContain("You stopped this one on Monday 14 September 2026.");
  expect(saved).not.toContain("<script");
  expect(await patientScreenOk(page)).toEqual([]);
});

test("Pa's calendar one proposal at a time: his yes books the visit, a no books nothing; the family's messages", async ({ page, request }) => {
  const family = await seedFamily(request);
  await seedProposals(request, family);
  await signIn(page, family.pa, true);
  await page.getByTestId("tab-family").click();
  await page.getByTestId("open-calendar").click();
  await expect(page.getByTestId("proposal")).toHaveCount(1);
  const first = await page.getByTestId("proposal-lines").innerText();
  expect(first.trim()).not.toBe("");
  expect(await patientScreenOk(page)).toEqual([]);
  await page.getByTestId("proposal-yes").click();
  await expect(page.getByTestId("proposal-lines")).not.toHaveText(first);
  await page.getByTestId("proposal-no").click();
  await expect(page.getByTestId("proposal")).toHaveCount(0);
  await expect(page.getByTestId("choose-ics")).toBeVisible();
  const visits = (await (await request.get(`${API}/profiles/${family.profileId}/appointments`, { headers: auth(family.pa.token) })).json()) as { status: string }[];
  expect(visits.map((visit) => visit.status)).toEqual(["planned"]);

  await back(page);
  await page.getByTestId("open-thread").click();
  const digest = page.getByTestId("digest");
  await expect(digest).toContainText("Pa on Monday 14 September.");
  await page.locator('textarea[name="family-message"]').fill("I slept well.");
  await page.getByTestId("send-message").click();
  await expect(digest.getByTestId("digest-entry").filter({ hasText: "I slept well." })).toContainText("Pa wrote on Monday 14 September:");
  expect(await patientScreenOk(page)).toEqual([]);
});

test.describe("the caregiver density at 360 by 640", () => {
  test.use({ viewport: { width: 360, height: 640 } });

  test("Mei's keys: a helper's key by role, parts and window; made smaller; wider refused in the backend's words; closed", async ({ page, request }) => {
    const family = await seedFamily(request);
    await signIn(page, family.mei, false);
    await expect(page.locator("html")).toHaveAttribute("data-density", "caregiver");
    await page.getByTestId("tab-family").click();
    // The circle is read after the page opens: check the layout once its lines are in.
    await expect(page.getByTestId("grant-lines")).toHaveCount(2);
    expect(await caregiverScreenOk(page)).toEqual([]);
    await page.getByTestId("open-keys").click();
    await expect(page.getByTestId("grant")).toHaveCount(2);

    await page.getByLabel("Their name").fill("Siti");
    await page.getByLabel("Their phone number").fill(family.siti.phone);
    await page.getByTestId("role-helper").click();
    await expect(page.getByTestId("role-lines")).toContainText("Siti");
    await expect(page.getByTestId("new-part-medicines")).toHaveAttribute("aria-pressed", "true");
    await expect(page.getByTestId("new-part-notes")).toHaveAttribute("aria-pressed", "false");
    await page.getByTestId("new-window-thirty_days").click();
    // Mei is a chief, not the owner: letting someone in at all is Pa's own yes (`may_invite`),
    // so her key rests on the sharing agreement `seedFamily` already gave Pa's — no words step
    // of her own, straight to the key.
    await expect(page.getByTestId("see-words")).toHaveCount(0);
    expect(await caregiverScreenOk(page)).toEqual([]);
    await page.getByTestId("make-key").click();
    const siti = page.getByTestId("grant").filter({ hasText: "Siti" });
    await expect(siti).toContainText("your emergency card");

    await siti.getByTestId("narrow").click();
    await siti.getByTestId("narrow-part-emergency").click();
    await siti.getByTestId("narrow-part-send").click();
    expect(await caregiverScreenOk(page)).toEqual([]);
    await siti.getByTestId("narrow-yes").click();
    await expect(siti).not.toContainText("your emergency card");
    await expect(siti).toContainText("your medicines");

    // Wider is not a change in place: the backend says no, in its words.
    await siti.getByTestId("narrow").click();
    await siti.getByTestId("narrow-part-readings").click();
    await siti.getByTestId("narrow-yes").click();
    await expect(siti.getByTestId("notice")).toContainText("Nura cannot make this wider.");
    await expect(siti.getByTestId("notice")).toContainText("The owner must agree to more first.");
    await siti.getByTestId("narrow-cancel").click();

    await siti.getByTestId("close-key").click();
    await siti.getByTestId("close-yes").click();
    await expect(page.getByTestId("grant").filter({ hasText: "Siti" })).toHaveCount(0);
    expect((await request.get(`${API}/profiles/${family.profileId}`, { headers: auth(family.siti.token) })).status()).toBe(403);
    expect(await caregiverScreenOk(page)).toEqual([]);
  });

  test("Mei's roster and tasks: Mei weekdays, Kit weekends; a task only Siti can mark done; the visit one tap away", async ({ page, request }) => {
    const family = await seedFamily(request, { sitiKey: true });
    await seedVisit(request, family.pa.token, family.profileId);
    await signIn(page, family.mei, false);
    const roster = await openFamilyPart(page, "roster");
    await expect(roster.getByTestId("roster-row")).toHaveCount(1);
    await page.getByTestId("slot-who-Mei").click();
    for (const day of [1, 2, 3, 4]) await page.getByTestId(`slot-day-${day}`).click();
    await page.getByTestId("add-slot").click();
    await expect(roster.getByTestId("roster-row")).toHaveCount(2);
    await page.getByTestId("slot-who-Kit").click();
    for (const day of [5, 6]) await page.getByTestId(`slot-day-${day}`).click();
    await page.getByTestId("add-slot").click();
    await expect(roster.getByTestId("roster-row")).toHaveCount(3);
    await expect(roster.getByTestId("roster-row").filter({ hasText: "Kit" })).toContainText("07:00");
    await expect(page.getByTestId("on-duty")).toContainText("Mei");

    await page.getByLabel("What to do").fill("Buy the water pill");
    await page.getByTestId("task-who-Siti").click();
    await page.getByTestId("add-task").click();
    const task = page.getByTestId("task").filter({ hasText: "Buy the water pill" });
    await expect(task).toContainText("Siti");
    await task.getByTestId("task-done-button").click();
    await expect(task.getByTestId("notice")).toContainText("Only the person it is for can say it is done.");
    expect(await caregiverScreenOk(page)).toEqual([]);

    // Siti taps it done herself, with her own key.
    const hers = auth(family.siti.token);
    const mine = (await (await request.get(`${API}/profiles/${family.profileId}/tasks?mine=true`, { headers: hers })).json()) as { task_id: string }[];
    const yes = await request.post(`${API}/profiles/${family.profileId}/confirmations`, { headers: hers, data: { subject: "task_done", task_id: mine[0]!.task_id } });
    const done = await request.post(`${API}/profiles/${family.profileId}/tasks/${mine[0]!.task_id}/done`, {
      headers: hers,
      data: { confirmation_id: ((await yes.json()) as { confirmation_id: string }).confirmation_id },
    });
    expect(done.status()).toBe(200);
    await openFamilyPart(page, "roster");
    await expect(page.getByTestId("task").filter({ hasText: "Buy the water pill" }).getByTestId("task-done")).toHaveText("Done");

    await page.getByTestId("next-visit").click();
    await expect(page.getByTestId("visit-screen")).toBeVisible();
  });

  test("the family thread: Mei writes on her phone, Kit reads the digest on his", async ({ page, request, browser }) => {
    const family = await seedFamily(request);
    await signIn(page, family.mei, false);
    await openFamilyPart(page, "thread");
    await page.locator('textarea[name="family-message"]').fill("Pa slept well. I will come by at 6.");
    await page.getByTestId("send-message").click();
    await expect(page.getByTestId("digest-entry").filter({ hasText: "Pa slept well." })).toContainText("Mei wrote on Monday 14 September:");
    expect(await caregiverScreenOk(page)).toEqual([]);

    const kit = await secondPhone(browser);
    await signIn(kit, family.kit, false);
    await openFamilyPart(kit, "thread");
    const digest = kit.getByTestId("digest");
    await expect(digest).toContainText("Pa on Monday 14 September.");
    await expect(digest.getByTestId("digest-entry").filter({ hasText: "Pa slept well. I will come by at 6." })).toContainText("Mei wrote on Monday 14 September:");
    await expect(kit.getByTestId("digest-closing")).toContainText("Mei is on duty today.");
    expect(await caregiverScreenOk(kit)).toEqual([]);
    // What went out, and to whom, is the owner's and his chief's: Kit is told so in the
    // backend's words, never shown a disabled button.
    await openFamilyPart(kit, "deliveries");
    await expect(kit.getByTestId("notice")).toContainText("Only the owner can see this.");
    await kit.context().close();
  });

  test("a message to Pa, previewed in Malay, scheduled, then sent by the delivery engine; the delivery log says what went", async ({ page, request }) => {
    const family = await seedFamily(request);
    await signIn(page, family.mei, false);
    await openFamilyPart(page, "messages");
    await page.getByLabel("When").fill("pukul 9");
    await page.getByTestId("message-lang-ms").click();
    await page.getByTestId("preview-message").click();
    await expect(page.getByTestId("preview-lines").locator("p")).toHaveText(["Mei akan ambil anda pada pukul 9.", "Bawa buku tekanan darah anda."]);
    expect(await caregiverScreenOk(page)).toEqual([]);
    await page.getByTestId("schedule-message").click();
    const scheduled = page.getByTestId("scheduled-message");
    await expect(scheduled.getByTestId("message-state")).toHaveAttribute("data-state", "scheduled");
    await expect(scheduled.getByTestId("message-state")).toContainText("Waiting to send");

    await runTriggersAt(request, family, "2026-09-14T11:20:00+08:00");
    await openFamilyPart(page, "messages");
    await expect(page.getByTestId("message-state")).toHaveAttribute("data-state", "sent");
    await expect(page.getByTestId("message-state")).toContainText("Sent");

    await openFamilyPart(page, "deliveries");
    const sent = page.getByTestId("delivery").filter({ hasText: "family_message_due" });
    await expect(sent).toContainText("Family message");
    await expect(sent).toContainText("Pa");
    await expect(sent).toContainText("WhatsApp");
    expect(await caregiverScreenOk(page)).toEqual([]);
  });

  test("the week in numbers, when and how Nura sends, the papers behind the family list; what is the owner's alone is refused in the backend's words", async ({ page, request }) => {
    const family = await seedFamily(request);
    await signIn(page, family.mei, false);

    await openFamilyPart(page, "metrics");
    await expect(page.getByTestId("metrics-week").first()).toContainText("Taps");
    expect(await caregiverScreenOk(page)).toEqual([]);

    await openFamilyPart(page, "settings");
    await page.getByLabel("Quiet from").fill("21:30");
    await page.getByTestId("save-settings").click();
    await openFamilyPart(page, "settings");
    await expect(page.getByLabel("Quiet from")).toHaveValue("21:30");
    await expect(page.getByTestId("kind-flag")).toContainText("Never held");
    // No setting chooses how a red flag goes (#162): the row says so and offers no channel.
    await expect(page.getByTestId("every-way-flag")).toHaveText("Nura always tells your family about this, every way it can.");
    await expect(page.getByTestId("kind-flag").getByTestId(/^channel-flag-/)).toHaveCount(0);
    expect(await caregiverScreenOk(page)).toEqual([]);

    await openFamilyPart(page, "documents");
    await page.getByTestId("tag-lpa").click();
    await page.getByTestId("choose-document").locator("input").setInputFiles({ name: "lpa.pdf", mimeType: "application/pdf", buffer: Buffer.from("%PDF-1.4 placeholder lpa") });
    await expect(page.getByTestId("document").filter({ hasText: "Lasting power of attorney" })).toBeVisible();
    expect(await caregiverScreenOk(page)).toEqual([]);

    await openFamilyPart(page, "consents");
    await page.getByTestId("consent").filter({ hasText: "Kit" }).getByTestId("stop").click();
    await expect(page.getByTestId("notice")).toContainText("Only the owner can stop this.");
    expect(await caregiverScreenOk(page)).toEqual([]);

    await openFamilyPart(page, "onlyMe");
    await page.getByTestId("only-me-money").click();
    await page.getByTestId("only-me-yes").click();
    await expect(page.getByTestId("notice")).toBeVisible();
    await expect(page.getByTestId("notice")).not.toContainText("Nura could not do that right now.");

    await openFamilyPart(page, "trail");
    await expect(page.getByTestId("trail-day").first()).toBeVisible();
    expect(await caregiverScreenOk(page)).toEqual([]);
  });

  test("a calendar file on Mei's phone: two proposals, the lunch kept nowhere, one put aside", async ({ page, request }) => {
    const family = await seedFamily(request);
    // Pa agrees to the calendar first; Mei cannot agree for him.
    const words = (await (await request.get(`${API}/consent/wording?purpose=calendar&language=en`)).json()) as { version: string };
    const agreed = await request.post(`${API}/profiles/${family.profileId}/connectors/calendar`, {
      headers: auth(family.pa.token),
      data: { consent: { wording_version: words.version, language: "en", captured_via: "app" } },
    });
    expect(agreed.status()).toBe(201);
    await signIn(page, family.mei, false);
    await openFamilyPart(page, "calendar");
    await page.getByTestId("choose-ics").locator("input").setInputFiles({ name: "three-events.ics", mimeType: "text/calendar", buffer: ICS });
    await expect(page.getByTestId("proposal")).toHaveCount(2);
    await expect(page.locator("main")).not.toContainText("Ah Kow");
    expect(await caregiverScreenOk(page)).toEqual([]);
    await page.getByTestId("proposal").nth(1).getByTestId("proposal-no").click();
    await expect(page.getByTestId("proposal")).toHaveCount(1);
  });

  test("a red flag reached Mei: she says she is on it, and the ladder asks nobody else", async ({ page, request }) => {
    const family = await seedFamily(request);
    const said = await request.post(`${API}/profiles/${family.profileId}/not-feeling-well`, { headers: auth(family.pa.token), data: { words: "chest pain" } });
    expect(said.status()).toBe(201);
    await signIn(page, family.mei, false);
    await page.getByTestId("tab-family").click();
    const ladder = page.getByTestId("ladder");
    await expect(ladder.getByTestId("ladder-lines")).toContainText("Nura asked you to check on Pa on Monday 14 September at 10 in the morning.");
    expect(await caregiverScreenOk(page)).toEqual([]);
    await ladder.getByTestId("on-it").click();
    await expect(page.getByTestId("ladder-answered")).toContainText("Nura asks nobody else now.");
    await expect(page.getByTestId("ladder")).toHaveCount(0);
  });
});

test("the for-someone door: who you are to them is a choice, and the number can come from the phone's contacts", async ({ page, request }) => {
  const his = freshPhone("+659885");
  await page.addInitScript((tel: string) => {
    Object.defineProperty(navigator, "contacts", { value: { select: async () => [{ name: ["Pa"], tel: [tel] }] }, configurable: true });
  }, `+65 ${his.slice(3, 7)} ${his.slice(7)}`);
  await signInThroughTheApp(page, freshPhone("+659884"), "Ash");
  await page.getByTestId("door-for-someone").click();
  await expect(page.locator('input[name="relationship"]')).toHaveCount(0);
  await page.getByTestId("pick-contact").click();
  await expect(page.getByLabel("Their phone number")).toHaveValue(his);
  await expect(page.getByLabel("Their name")).toHaveValue("Pa");
  await page.getByTestId("relationship-daughter").click();
  await expect(page.getByTestId("relationship-daughter")).toHaveAttribute("aria-pressed", "true");
  await page.getByText("They asked you to do this.").click();
  await page.getByRole("button", { name: "Set it up" }).click();
  await expect(page.locator("main.onboarding")).toBeVisible();

  const token = await apiToken(request, his);
  // A code on the wire; the words are the backend's, in the reader's language.
  const offers = (await (await request.get(`${API}/profiles/mine/claimable?language=en`, { headers: auth(token) })).json()) as { relationship: string | null; relationship_words: string | null }[];
  expect(offers.map((offer) => [offer.relationship, offer.relationship_words])).toEqual([["daughter", "your daughter"]]);
  const malay = (await (await request.get(`${API}/profiles/mine/claimable?language=ms`, { headers: auth(token) })).json()) as { relationship_words: string | null }[];
  expect(malay.map((offer) => offer.relationship_words)).toEqual(["anak perempuan anda"]);
});

export type { Family };
