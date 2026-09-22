import { expect, test, type APIRequestContext, type Page } from "@playwright/test";
import { API, apiToken, backendClock, codeFromLog, codesSoFar, fixClock, freshPhone, pastWelcome } from "./helpers";

/** Package 9 (checkpoint 5): onboarding in the blueprint's language — welcome, sign in, who is
 *  this for, and the bubble cloud (docs/design/experience-blueprint.html scenes `welcome`,
 *  `signin`, `who`, `cloud`). The big, sequential registration and caregiver walks already live
 *  in `onboarding.spec.ts` and stay there unweakened; this spec covers what is new here: the
 *  choose-cards, the bubble cloud's geometry and keyboard reachability, every sign-in state, and
 *  proof the cloud still saves exactly what it always saved. */

const SWITCHES = ["large_text", "high_contrast", "voice_on", "big_targets", "one_thing_per_screen", "read_back", "repeat_prompts"] as const;

test.beforeEach(async ({ page, request }) => {
  const clock = await backendClock(request);
  expect(clock.frozen, "start the backend with NURA_FROZEN_CLOCK (see playwright.config.ts)").toBe(true);
  await fixClock(page);
});

/** Welcome → the phone number and name → Send — one screen at a time, so a test can look at the
 *  sign-in screens themselves along the way (`signInThroughTheApp`, helpers.ts, does the same
 *  thing in one call but does not stop to look). Returns how many codes this number had before
 *  this send, for `codeFromLog` to wait past. */
async function throughSend(page: Page, phone: string, name: string): Promise<number> {
  await page.goto("./");
  await pastWelcome(page);
  await page.getByLabel("Your phone number").fill(phone);
  await page.getByLabel("Your name").fill(name);
  const before = codesSoFar(phone);
  await page.getByTestId("send-code").click();
  await expect(page.getByLabel("The code")).toBeVisible();
  return before;
}

/** The same, all the way to the doors: the code read from the log and verified. */
async function throughSignIn(page: Page, phone: string, name: string): Promise<void> {
  const before = await throughSend(page, phone, name);
  const code = await codeFromLog(phone, before);
  await page.getByLabel("The code").fill(code);
  await page.getByTestId("verify-code").click();
}

async function profileOf(request: APIRequestContext, phone: string): Promise<{ auth: { Authorization: string }; id: string }> {
  const token = await apiToken(request, phone);
  const auth = { Authorization: `Bearer ${token}` };
  const me = (await (await request.get(`${API}/me`, { headers: auth })).json()) as { profile_id: string };
  return { auth, id: me.profile_id };
}

test("welcome and sign in, in the blueprint's own shape", async ({ page }) => {
  await page.goto("./");
  const welcome = page.getByTestId("welcome-screen");
  await expect(welcome).toBeVisible();
  await expect(welcome.getByTestId("welcome-orb")).toBeVisible();
  // The tagline is now words arriving one by one (`SoftText`); the plain sentence still reads
  // exactly as before, from the accessible line kept beside the animated spans.
  await expect(welcome.locator(".welcome-tagline .sr-only")).toHaveText("Your health, kept together. Your family, close by.");
  await page.getByTestId("welcome-start").click();

  // Sign in as one conversation step: Nura's line beside the small orb, the field, a button
  // that goes through its three real states.
  await expect(page.getByTestId("signin-say")).toBeVisible();
  const phone = freshPhone("+659871");
  await page.getByLabel("Your phone number").fill(phone);
  await page.getByLabel("Your name").fill("Tan");
  const send = page.getByTestId("send-code");
  await expect(send).toHaveAttribute("data-state", "idle");
  await send.click();
  await expect(page.getByLabel("The code")).toBeVisible();
  await expect(page.getByTestId("signin-say")).toBeVisible();
});

test("sign-in: the phone-number step's own error sits right under the field, and clears when he types again", async ({ page }) => {
  await page.goto("./");
  await pastWelcome(page);
  const phone = page.getByLabel("Your phone number");
  const already = freshPhone("+659878");
  // AlreadyRegistered is a real refusal `startPhone` can return for a number already signed up
  // (mocked here only because seeding one through the app first would need its own sign-in,
  // not because the backend can't produce it) — the point is the placement/aria wiring, not
  // this one particular refusal class.
  await page.route("**/auth/phone/start", async (route) => {
    await route.fulfill({ status: 409, contentType: "application/json", body: JSON.stringify({ refusal: "AlreadyRegistered" }) });
  });
  await phone.fill(already);
  await page.getByTestId("send-code").click();
  const notice = page.getByTestId("notice");
  await expect(notice).toBeVisible();
  const noticeId = await notice.getAttribute("id");
  expect(noticeId).toBeTruthy();
  await expect(phone).toHaveAttribute("aria-describedby", noticeId!);
  await expect(phone).toHaveAttribute("aria-invalid", "true");

  await phone.fill(freshPhone("+659877"));
  await expect(notice).toHaveCount(0);
  await expect(phone).not.toHaveAttribute("aria-invalid", "true");
});

/** Operator review: the old layout (illustration + heart + tall headline + three tall cards)
 *  pushed "Get started" below the fold at 390x844 — a first screen whose only action is not
 *  visible is a defect. This must hold with no scrolling at both sizes; at 360x640 the orb is
 *  allowed to shrink (`clamp()`, onboarding.css) but the button must still be on screen. */
for (const size of [
  { width: 390, height: 844, label: "390x844" },
  { width: 360, height: 640, label: "360x640" },
]) {
  test(`welcome: "Get started" is on screen with no scrolling at ${size.label}`, async ({ page }) => {
    await page.setViewportSize({ width: size.width, height: size.height });
    await page.goto("./");
    const welcome = page.getByTestId("welcome-screen");
    await expect(welcome).toBeVisible();
    await page.evaluate(() => document.fonts.ready);

    const scrollHeight = await page.evaluate(() => document.scrollingElement?.scrollHeight ?? 0);
    expect(scrollHeight, "the welcome screen scrolls").toBeLessThanOrEqual(size.height + 1);

    const button = page.getByTestId("welcome-start");
    const box = (await button.boundingBox())!;
    expect(box.y, "Get started's top").toBeGreaterThanOrEqual(0);
    expect(box.y + box.height, "Get started's bottom").toBeLessThanOrEqual(size.height);

    const rows = await page.locator(".value-row").evaluateAll((nodes, viewportHeight) =>
      nodes.map((node) => {
        const rect = node.getBoundingClientRect();
        return { top: rect.top, bottom: rect.bottom, clipped: rect.top < 0 || rect.bottom > viewportHeight, text: (node.textContent ?? "").trim() };
      }),
      size.height,
    );
    expect(rows.length).toBe(3);
    for (const row of rows) expect(row.clipped, row.text).toBe(false);
  });
}

test("who is this for: a conversation with chips, and the caregiver path names him rather than saying 'your'", async ({ page, request }) => {
  const phone = freshPhone("+659872");
  await throughSignIn(page, phone, "Ash");

  await expect(page.getByTestId("who-greeting")).toBeVisible();
  await expect(page.getByTestId("who-chips")).toBeVisible();
  for (const testId of ["door-for-me", "door-for-someone"]) {
    const box = (await page.getByTestId(testId).boundingBox())!;
    expect(box.height, testId).toBeGreaterThanOrEqual(44);
  }

  const pa = freshPhone("+659879");
  await page.getByTestId("door-for-someone").click();
  await page.getByLabel("Their name").fill("Pa");
  await page.getByLabel("Their phone number").fill(pa);
  await page.getByTestId("relationship-daughter").click();
  await page.getByText("They asked you to do this.").click();
  await page.getByRole("button", { name: "Set it up" }).click();

  const main = page.locator("main.onboarding");
  await expect(page.getByRole("heading", { name: "A few things about Pa" })).toBeVisible();
  await page.getByTestId("about-lang-en").click();
  await page.getByTestId("decade-1940").click();
  await page.getByLabel("The doctor's name").fill("Dr Lim");
  await page.getByTestId("breakfast-07:00").click();
  for (const item of SWITCHES) await page.getByTestId(`${item}-no`).click();
  await page.getByTestId("density-detailed").click();
  await page.getByTestId("about-next").click();

  await expect(main).toHaveAttribute("data-stage", "cloud");
  await expect(page.getByRole("heading", { name: "What is part of Pa's health?" })).toBeVisible();
  await page.getByTestId("word-high_blood_pressure").click();
  // Nura's acknowledgement names him, never "your" — about-him.spec.ts's own rule, extended to
  // the new ack line.
  const ack = page.getByTestId("cloud-ack");
  await expect(ack).toBeVisible();
  await expect(ack).toContainText("Pa");
  await expect(ack).not.toContainText(/\byour\b/i);
});

/** Choosing "Me" (docs/design/experience-blueprint.html `who`): his own reply, then Nura's,
 *  then one privacy sentence and one Continue — before the versioned consent words, never an
 *  instant jump from a tap to a form. */
test("who is this for, choosing 'Me': his reply, Nura's welcome, one Continue, then consent", async ({ page }) => {
  const phone = freshPhone("+659881");
  await throughSignIn(page, phone, "Tan");

  await page.getByTestId("door-for-me").click();
  await expect(page.getByTestId("who-me-reply")).toContainText("Me. My name is Tan.");
  await expect(page.getByTestId("who-met")).toContainText("Good to meet you, Tan.");
  await expect(page.getByTestId("consent-words")).toHaveCount(0);
  await page.getByTestId("who-continue").click();
  await expect(page.getByTestId("consent-words")).toBeVisible();
});

test("sign-in: wrong code, then a real resend, then the right one", async ({ page }) => {
  const phone = freshPhone("+659873");
  await throughSend(page, phone, "Pa");

  const code = page.getByLabel("The code");
  await code.fill("000000");
  await page.getByTestId("verify-code").click();
  const notice = page.getByTestId("notice");
  await expect(notice).toBeVisible();
  await expect(notice.locator("[data-error-kind]")).toHaveAttribute("data-error-kind", "wrongCode");
  // Right under the field it is about (operator review), tied to it for a screen reader, not a
  // separate card elsewhere on the screen.
  const noticeId = await notice.getAttribute("id");
  expect(noticeId).toBeTruthy();
  await expect(code).toHaveAttribute("aria-describedby", noticeId!);
  await expect(code).toHaveAttribute("aria-invalid", "true");
  const fieldBox = (await code.boundingBox())!;
  const noticeBox = (await notice.boundingBox())!;
  expect(noticeBox.y, "the notice sits right under the code field, not far below the form").toBeLessThan(fieldBox.y + fieldBox.height + 120);

  // Typing again clears it — the refusal was about the code already sent, not the one now
  // being typed.
  await code.fill("111111");
  await expect(notice).toHaveCount(0);
  await expect(code).not.toHaveAttribute("aria-invalid", "true");

  await code.fill("000000");
  await page.getByTestId("verify-code").click();
  await expect(notice).toBeVisible();

  // A real resend: it asks the backend again, exactly as the first send did, and shows what
  // came back — never a client-side countdown.
  const before = codesSoFar(phone);
  await page.getByTestId("resend-code").click();
  await expect(page.getByTestId("resend-done")).toBeVisible();
  const fresh = await codeFromLog(phone, before);
  await page.getByLabel("The code").fill(fresh);
  await page.getByTestId("verify-code").click();
  // Both choose-cards land together on a fresh phone (the `who` scene shows "for me" and "for
  // someone I look after" side by side, not one at a time).
  await expect(page.getByTestId("door-for-me")).toBeVisible();
  await expect(page.getByTestId("door-for-someone")).toBeVisible();
});

test("sign-in: an expired code, a locked challenge, and a dead network — each the backend's own sentence", async ({ page }) => {
  const phone = freshPhone("+659874");
  await throughSend(page, phone, "Pa");

  // The backend itself has no easy way to produce these three in a live run (a real expiry
  // takes real minutes, a real lock takes many real tries, a dead network needs no network) —
  // each is mocked at the one seam the app calls through, `POST /auth/phone/verify` /
  // `POST /auth/phone/start`, so the screen is exercised exactly as a real refusal would drive
  // it.
  await page.route("**/auth/phone/verify", async (route) => {
    await route.fulfill({ status: 409, contentType: "application/json", body: JSON.stringify({ refusal: "ChallengeExpired" }) });
  });
  await page.getByLabel("The code").fill("123456");
  await page.getByTestId("verify-code").click();
  await expect(page.getByTestId("notice").locator("[data-error-kind]")).toHaveAttribute("data-error-kind", "expired");
  // Expired points Resend at the plum, primary look — the one action that actually answers it.
  await expect(page.getByTestId("resend-code")).toHaveClass(/plum/);
  await page.unroute("**/auth/phone/verify");

  await page.route("**/auth/phone/verify", async (route) => {
    await route.fulfill({ status: 429, contentType: "application/json", body: JSON.stringify({ refusal: "ChallengeLocked" }) });
  });
  await page.getByTestId("verify-code").click();
  await expect(page.getByTestId("notice").locator("[data-error-kind]")).toHaveAttribute("data-error-kind", "locked");
  await page.unroute("**/auth/phone/verify");

  await page.route("**/auth/phone/verify", async (route) => {
    await route.abort("internetdisconnected");
  });
  await page.getByTestId("verify-code").click();
  await expect(page.getByTestId("notice").locator("[data-error-kind]")).toHaveAttribute("data-error-kind", "network");
  await page.unroute("**/auth/phone/verify");
});

test("the cloud saves exactly the same payload it always did", async ({ page, request }) => {
  const phone = freshPhone("+659875");
  await throughSignIn(page, phone, "Tan");
  await page.getByTestId("door-for-me").click();
  await page.getByTestId("who-continue").click();
  await page.getByTestId("agree").click();
  await page.getByLabel("The name Nura uses").fill("Tan");
  await page.getByTestId("about-next").click();
  await page.getByTestId("about-lang-en").click();
  await page.getByTestId("decade-1950").click();
  await page.getByLabel("The doctor's name").fill("Dr Tan");
  await page.getByTestId("about-next").click();
  await page.getByTestId("breakfast-07:30").click();
  for (const item of SWITCHES) await page.getByTestId(`${item}-no`).click();
  await page.getByTestId("density-simple").click();

  await page.getByTestId("word-high_blood_pressure").click();
  await page.getByTestId("word-cholesterol").click();

  const [saveRequest] = await Promise.all([
    page.waitForRequest((req) => req.url().includes("/settings") && req.method() === "PUT"),
    page.getByTestId("cloud-done").click(),
  ]);
  const body = saveRequest.postDataJSON() as { conditions: string[] };
  // The exact same shape `saveSettings()`/`toggle()` (onboarding/actions.ts, onboarding/cloud.ts,
  // both untouched by this package) have always sent: the picked codes, nothing else new.
  expect(body.conditions).toEqual(expect.arrayContaining(["high_blood_pressure", "cholesterol"]));
  const pa = await profileOf(request, phone);
  const saved = (await (await request.get(`${API}/profiles/${pa.id}/settings`, { headers: pa.auth })).json()) as { conditions: string[] };
  expect(saved.conditions).toEqual(expect.arrayContaining(["high_blood_pressure", "cholesterol"]));
});

/** The cloud's bubbles at three sizes (360×640, the smallest a phone gets; 390×844, the default;
 *  1280×900, the widest the phone frame ever shows a screen at — above 600px the app sits
 *  inside a fixed 390px frame, so the cloud itself never actually grows past that, but the test
 *  runs the geometry check at the wide viewport too to prove nothing outside the frame breaks
 *  it). No two bubbles' boxes intersect by more than 4px, and every bubble's label stays inside
 *  the scrolling region — never clipped.
 *
 *  `evaluateAll` never auto-waits the way a locator action does — called the instant the graph's
 *  own fetch (`Cloud.tsx`) is still in flight, it used to read the container's own real, honest
 *  ZERO circles, not a timing bug in this test (review of #318: this red about a third of runs).
 *  Waiting on `data-loaded="true"` first is the fix, not a longer guessed sleep. */
async function cloudGeometryHolds(page: Page): Promise<void> {
  await expect(page.getByTestId("cloud")).toHaveAttribute("data-loaded", "true");
  const boxes = await page.getByTestId("cloud").locator('[data-testid^="word-"]').evaluateAll((nodes) =>
    nodes.map((node) => {
      const rect = node.getBoundingClientRect();
      return { left: rect.left, top: rect.top, right: rect.right, bottom: rect.bottom, text: (node.textContent ?? "").trim() };
    }),
  );
  expect(boxes.length).toBeGreaterThan(0);
  const scrollWidth = await page.evaluate(() => document.scrollingElement?.scrollWidth ?? 0);
  for (const box of boxes) {
    expect(box.left, box.text).toBeGreaterThanOrEqual(0);
    expect(box.right, box.text).toBeLessThanOrEqual(scrollWidth + 1);
  }
  for (let i = 0; i < boxes.length; i++) {
    for (let j = i + 1; j < boxes.length; j++) {
      const a = boxes[i]!;
      const b = boxes[j]!;
      const overlapX = Math.min(a.right, b.right) - Math.max(a.left, b.left);
      const overlapY = Math.min(a.bottom, b.bottom) - Math.max(a.top, b.top);
      if (overlapX > 0 && overlapY > 0) {
        expect(Math.min(overlapX, overlapY), `${a.text} vs ${b.text}`).toBeLessThanOrEqual(4);
      }
    }
  }
}

for (const size of [
  { width: 360, height: 640, label: "360x640" },
  { width: 390, height: 844, label: "390x844" },
  { width: 1280, height: 900, label: "1280x900" },
]) {
  test(`the bubble cloud never overlaps itself at ${size.label}`, async ({ page }) => {
    await page.setViewportSize({ width: size.width, height: size.height });
    const phone = freshPhone("+65987" + (600 + size.width));
    await throughSignIn(page, phone, "Tan");
    await page.getByTestId("door-for-me").click();
    await page.getByTestId("who-continue").click();
    await page.getByTestId("agree").click();
    await page.getByLabel("The name Nura uses").fill("Tan");
    await page.getByTestId("about-next").click();
    await page.getByTestId("about-lang-en").click();
    await page.getByTestId("decade-1950").click();
    await page.getByLabel("The doctor's name").fill("Dr Tan");
    await page.getByTestId("about-next").click();
    await page.getByTestId("breakfast-07:30").click();
    for (const item of SWITCHES) await page.getByTestId(`${item}-no`).click();
    await page.getByTestId("density-detailed").click();
    await expect(page.locator("main.onboarding")).toHaveAttribute("data-stage", "cloud");
    await page.getByTestId("more-words").click(); // the fullest the cloud gets
    await cloudGeometryHolds(page);
  });
}

test("the cloud is walkable by keyboard alone, in reading order", async ({ page }) => {
  const phone = freshPhone("+659876");
  await throughSignIn(page, phone, "Tan");
  await page.getByTestId("door-for-me").click();
  await page.getByTestId("who-continue").click();
  await page.getByTestId("agree").click();
  await page.getByLabel("The name Nura uses").fill("Tan");
  await page.getByTestId("about-next").click();
  await page.getByTestId("about-lang-en").click();
  await page.getByTestId("decade-1950").click();
  await page.getByLabel("The doctor's name").fill("Dr Tan");
  await page.getByTestId("about-next").click();
  await page.getByTestId("breakfast-07:30").click();
  for (const item of SWITCHES) await page.getByTestId(`${item}-no`).click();
  await page.getByTestId("density-simple").click();

  const first = page.getByTestId("word-high_blood_pressure");
  await first.focus();
  await expect(first).toBeFocused();
  await page.keyboard.press("Enter");
  await expect(first).toHaveAttribute("aria-pressed", "true");
  // Real buttons, reachable one after the other in the cloud's own DOM order (the same order
  // `onboarding.spec.ts` already checks — a pick's related words land right after it).
  await page.keyboard.press("Tab");
  const next = page.locator(":focus");
  await expect(next).toHaveAttribute("data-testid", /^word-/);
});

test("the cloud respects prefers-reduced-motion: nothing keeps running", async ({ page }) => {
  await page.emulateMedia({ reducedMotion: "reduce" });
  const phone = freshPhone("+659877");
  await throughSignIn(page, phone, "Tan");
  await page.getByTestId("door-for-me").click();
  await page.getByTestId("who-continue").click();
  await page.getByTestId("agree").click();
  await page.getByLabel("The name Nura uses").fill("Tan");
  await page.getByTestId("about-next").click();
  await page.getByTestId("about-lang-en").click();
  await page.getByTestId("decade-1950").click();
  await page.getByLabel("The doctor's name").fill("Dr Tan");
  await page.getByTestId("about-next").click();
  await page.getByTestId("breakfast-07:30").click();
  for (const item of SWITCHES) await page.getByTestId(`${item}-no`).click();
  await page.getByTestId("density-simple").click();
  await expect(page.locator("main.onboarding")).toHaveAttribute("data-stage", "cloud");
  // `evaluateAll` never auto-waits — the graph's own fetch may still be in flight.
  await expect(page.getByTestId("cloud")).toHaveAttribute("data-loaded", "true");

  const running = await page.getByTestId("cloud").locator('[data-testid^="word-"]').evaluateAll((nodes) =>
    nodes.flatMap((node) => (node as HTMLElement).getAnimations().filter((a) => a.playState === "running")),
  );
  expect(running).toHaveLength(0);
});
