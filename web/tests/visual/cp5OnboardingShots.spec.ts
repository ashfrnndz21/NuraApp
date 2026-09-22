import { mkdirSync } from "node:fs";
import { expect, test, type Page } from "@playwright/test";
import { codeFromLog, codesSoFar, freshPhone, pastWelcome } from "../e2e/helpers";

/** Package 9 (checkpoint 5, "onboarding in the blueprint's language"): screen captures of the
 *  real app — a fresh phone number, signed in through the Welcome screen for real (never "Try
 *  it as Pa/Mei", which already has a finished profile and skips onboarding entirely), the
 *  rule-based/fixture stack only, no faked delay inside the app itself.
 *
 *  Not a gate — `npx playwright test -c playwright.visual.config.ts
 *  tests/visual/cp5OnboardingShots.spec.ts` writes pictures for a person to look at, into
 *  `NURA_CP5_SHOTS` (default: this checkpoint's own scratchpad folder). Every shot waits for
 *  real content (a heading, a field, the cloud's own bubbles) before it fires — never a fixed
 *  sleep. */

const OUT = process.env.NURA_CP5_SHOTS ?? "/private/tmp/claude-501/-Users-ashleyfernandez-SingleIDContext/e8f60261-760e-4178-a18b-74e3888c414c/scratchpad/shots/cp5-onboarding";
mkdirSync(OUT, { recursive: true });

test.use({ actionTimeout: 20_000 });

async function ready(page: Page): Promise<void> {
  await page.evaluate(() => document.fonts.ready);
}

/** Shoots either the phone frame (wide, above 600px) or the full page (full-bleed, at or below
 *  600px) — the same choice every other visual spec in this suite makes. */
async function shoot(page: Page, path: string, wide: boolean): Promise<void> {
  await ready(page);
  if (wide) await page.locator("#phone-frame").screenshot({ path, animations: "disabled" });
  else await page.screenshot({ path, animations: "disabled" });
}

async function throughAbout(page: Page): Promise<void> {
  await page.getByTestId("about-next").click();
  await page.getByTestId("about-lang-en").click();
  await page.getByTestId("decade-1950").click();
  await page.getByLabel("The doctor's name").fill("Dr Tan");
  await page.getByTestId("about-next").click();
  await page.getByTestId("breakfast-07:30").click();
  for (const item of ["large_text", "high_contrast", "voice_on", "big_targets", "one_thing_per_screen", "read_back", "repeat_prompts"]) {
    await page.getByTestId(`${item}-no`).click();
  }
  await page.getByTestId("density-simple").click();
}

async function run(page: Page, prefix: string, wide: boolean): Promise<void> {
  // 1. Welcome.
  await page.goto("./");
  await expect(page.getByTestId("welcome-screen")).toBeVisible();
  await shoot(page, `${OUT}/${prefix}-welcome.png`, wide);

  // 2. Sign in, idle.
  await pastWelcome(page);
  await expect(page.getByLabel("Your phone number")).toBeVisible();
  const phone = freshPhone(`+65988${wide ? 1 : 2}`);
  await page.getByLabel("Your phone number").fill(phone);
  await page.getByLabel("Your name").fill("Tan");
  await shoot(page, `${OUT}/${prefix}-signin-idle.png`, wide);

  const before = codesSoFar(phone);
  await page.getByTestId("send-code").click();
  await expect(page.getByLabel("The code")).toBeVisible();

  // 3. Sign in, wrong code — the backend's own refusal sentence.
  await page.getByLabel("The code").fill("000000");
  await page.getByTestId("verify-code").click();
  await expect(page.getByTestId("notice")).toBeVisible();
  await shoot(page, `${OUT}/${prefix}-signin-wrong-code.png`, wide);

  const code = await codeFromLog(phone, before);
  await page.getByLabel("The code").fill(code);
  await page.getByTestId("verify-code").click();

  // 4. Who is this for.
  await expect(page.getByTestId("door-for-me")).toBeVisible();
  await shoot(page, `${OUT}/${prefix}-who.png`, wide);
  await page.getByTestId("door-for-me").click();
  await expect(page.getByTestId("who-continue")).toBeVisible();
  await page.getByTestId("who-continue").click();
  await page.getByTestId("agree").click();

  // 5. About, one step.
  await expect(page.getByRole("heading", { name: "What should Nura call you?" })).toBeVisible();
  await shoot(page, `${OUT}/${prefix}-about-step.png`, wide);
  await page.getByLabel("The name Nura uses").fill("Tan");
  await throughAbout(page);

  // 6. Cloud, empty — waits for the real bubbles themselves (`nura.conditions()`'s answer), not
  // only the (already-mounted, still content-less) container, so this is never a shot of a
  // blank loading gap.
  await expect(page.locator("main.onboarding")).toHaveAttribute("data-stage", "cloud");
  await expect(page.getByTestId("cloud").locator('[data-testid^="word-"]').first()).toBeVisible();
  await shoot(page, `${OUT}/${prefix}-cloud-empty.png`, wide);

  // 7. Cloud, 3 picked, with the acknowledgement.
  await page.getByTestId("word-high_blood_pressure").click();
  await page.getByTestId("word-cholesterol").click();
  await page.getByTestId("word-hospital_last_year").click();
  await expect(page.getByTestId("cloud-ack")).toBeVisible();
  await shoot(page, `${OUT}/${prefix}-cloud-picked.png`, wide);

  // 8. The hand-off into the first paper: the biography's own next prompt, Nura's line, the
  // camera/file/many-photos actions — `RecordsStep` (owned by another builder this package
  // does not touch) already renders exactly this moment on its first paint, before any file is
  // picked; this shot is that moment, not a new screen.
  await page.getByTestId("cloud-done").click();
  await expect(page.locator("main.onboarding")).toHaveAttribute("data-stage", "records");
  await expect(page.getByTestId("take-photo")).toBeVisible();
  await shoot(page, `${OUT}/${prefix}-handoff.png`, wide);
}

test.describe("cp5 onboarding at 390x844", () => {
  test.use({ viewport: { width: 390, height: 844 }, deviceScaleFactor: 1, isMobile: true, hasTouch: true });
  test("390x844, full-bleed", async ({ page }) => {
    await run(page, "phone", false);
  });
});

test.describe("cp5 onboarding at 1280x900", () => {
  test.use({ viewport: { width: 1280, height: 900 }, deviceScaleFactor: 2 });
  test("1280x900, clipped to the phone frame", async ({ page }) => {
    await run(page, "wide", true);
  });
});

test.describe("cp5 the bubble cloud at 360x640", () => {
  test.use({ viewport: { width: 360, height: 640 }, deviceScaleFactor: 1, isMobile: true, hasTouch: true });
  test("360x640, the smallest a phone gets", async ({ page }) => {
    const phone = freshPhone("+659883");
    await page.goto("./");
    await pastWelcome(page);
    await page.getByLabel("Your phone number").fill(phone);
    await page.getByLabel("Your name").fill("Tan");
    const before = codesSoFar(phone);
    await page.getByTestId("send-code").click();
    const code = await codeFromLog(phone, before);
    await page.getByLabel("The code").fill(code);
    await page.getByTestId("verify-code").click();
    await page.getByTestId("door-for-me").click();
    await page.getByTestId("who-continue").click();
    await page.getByTestId("agree").click();
    await page.getByLabel("The name Nura uses").fill("Tan");
    await throughAbout(page);
    // The cloud container is visible the instant the screen mounts now, loading or not
    // (`Cloud.tsx`: the orb and a loading line while its own graph fetch is still in flight,
    // never a childless box) — `data-loaded="true"` is what actually says the words themselves
    // have arrived.
    await expect(page.getByTestId("cloud")).toHaveAttribute("data-loaded", "true");
    await page.getByTestId("more-words").click();
    await shoot(page, `${OUT}/cloud-360x640.png`, false);
  });
});
