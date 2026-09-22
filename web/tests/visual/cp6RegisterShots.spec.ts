import { mkdirSync } from "node:fs";
import { expect, test, type Page } from "@playwright/test";
import { codeFromLog, codesSoFar, freshPhone, pastWelcome, paperPhoto } from "../e2e/helpers";

/** The register path, one continuous blueprint experience (docs/design/experience-blueprint.html
 *  scenes `welcome`, `signin`, `who`, `cloud`, `firstpaper`, `reading`, `report`): a brand new
 *  phone number, signed in for real through the Welcome screen (never "Try it as Pa/Mei", which
 *  already has a finished profile and skips every one of these screens), the rule-based/fixture
 *  stack only, no faked delay inside the app itself.
 *
 *  Every scene along this walk gets its own shot, at a phone width (390x844, full-bleed) and a
 *  wide desktop width (1280x900, clipped to the phone frame) — the two sizes the rest of this
 *  suite's design captures already use. It also holds the whole walk to zero `pageerror`s and
 *  zero `console.error`s: the blank-screen defect the owner hit in Safari would show up here as
 *  a walk that throws or logs, in whichever browser project runs it
 *  (`--project=chromium`/`--project=webkit`).
 *
 *  Not a gate — `npx playwright test -c playwright.visual.config.ts
 *  tests/visual/cp6RegisterShots.spec.ts --project=<chromium|webkit>` writes pictures for a
 *  person to look at, into `NURA_CP6_SHOTS` (default: this checkpoint's own scratchpad folder).
 *  Every shot waits for real content first — never a fixed sleep. */

const OUT = process.env.NURA_CP6_SHOTS ?? "/private/tmp/claude-501/-Users-ashleyfernandez-SingleIDContext/e8f60261-760e-4178-a18b-74e3888c414c/scratchpad/shots/cp6-register";
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

/** Every cloud bubble's OWN word must stay inside its own circle — a screenshot once caught
 *  "Kidney number checked by a doctor" and "Stroke in the family" painting text above and below
 *  the circle's own edge (`onboarding/cloud.ts` `minDiameterFor`/`estimateLabelBox`, sized for
 *  the whole wrapped label, not just its longest single word). Reads each bubble's own text
 *  node with a DOM `Range` (never `element.getBoundingClientRect()` alone — that would measure
 *  the button's own box, which is what this is checking the text stays inside, not the text
 *  itself) and compares it against the button's real, rendered box — the same real layout a
 *  screenshot shows, not `packCloud`'s own estimate of it. A tiny tolerance absorbs sub-pixel
 *  rounding, nothing more. */
async function assertNoBubbleTextOverflow(page: Page, where: string): Promise<void> {
  const overflowing = await page.evaluate(() => {
    const TOLERANCE = 1;
    const misfits: string[] = [];
    for (const button of Array.from(document.querySelectorAll('[data-testid^="word-"]'))) {
      let left = Infinity;
      let top = Infinity;
      let right = -Infinity;
      let bottom = -Infinity;
      let hasText = false;
      for (const node of Array.from(button.childNodes)) {
        if (node.nodeType !== Node.TEXT_NODE || !node.textContent?.trim()) continue;
        const range = document.createRange();
        range.selectNodeContents(node);
        for (const rect of Array.from(range.getClientRects())) {
          if (rect.width === 0 && rect.height === 0) continue;
          hasText = true;
          left = Math.min(left, rect.left);
          top = Math.min(top, rect.top);
          right = Math.max(right, rect.right);
          bottom = Math.max(bottom, rect.bottom);
        }
      }
      if (!hasText) continue;
      const box = button.getBoundingClientRect();
      const over = Math.max(box.left - left, box.top - top, right - box.right, bottom - box.bottom);
      if (over > TOLERANCE) {
        misfits.push(`${button.getAttribute("data-testid")} "${button.textContent?.trim()}" overflows its circle by ${Math.round(over * 10) / 10}px`);
      }
    }
    return misfits;
  });
  expect(overflowing, `${where}: every bubble's text must stay inside its own circle`).toEqual([]);
}

/** One scene at a time, every `pageerror` and `console.error` collected along the way — the
 *  webkit walk this is really for (task: find the blank screen the owner hit in Safari). */
async function run(page: Page, prefix: string, wide: boolean, errors: string[]): Promise<void> {
  page.on("pageerror", (err) => errors.push(`${prefix} pageerror: ${err.message}`));
  page.on("console", (msg) => {
    if (msg.type() === "error") errors.push(`${prefix} console.error: ${msg.text()}`);
  });

  // 1. Welcome.
  await page.goto("./");
  await expect(page.getByTestId("welcome-screen")).toBeVisible();
  await shoot(page, `${OUT}/${prefix}-01-welcome.png`, wide);

  // 2. Sign in.
  await pastWelcome(page);
  await expect(page.getByLabel("Your phone number")).toBeVisible();
  const phone = freshPhone(`+65989${wide ? 1 : 2}`);
  await page.getByLabel("Your phone number").fill(phone);
  await page.getByLabel("Your name").fill("Tan");
  await shoot(page, `${OUT}/${prefix}-02-signin.png`, wide);

  const before = codesSoFar(phone);
  await page.getByTestId("send-code").click();
  const code = await codeFromLog(phone, before);
  await page.getByLabel("The code").fill(code);
  await shoot(page, `${OUT}/${prefix}-03-signin-code.png`, wide);
  await page.getByTestId("verify-code").click();

  // 3. Who is this for: the chips.
  await expect(page.getByTestId("who-chips")).toBeVisible();
  await shoot(page, `${OUT}/${prefix}-04-who.png`, wide);

  // 4. His reply, Nura's welcome, one Continue.
  await page.getByTestId("door-for-me").click();
  await expect(page.getByTestId("who-continue")).toBeVisible();
  await shoot(page, `${OUT}/${prefix}-05-who-reply.png`, wide);
  await page.getByTestId("who-continue").click();

  // 5. Before we start: the versioned words, as Nura's own turn.
  await expect(page.getByTestId("consent-words")).toBeVisible();
  await shoot(page, `${OUT}/${prefix}-06-consent.png`, wide);
  await page.getByTestId("agree").click();

  // 6. About you: the conversation transcript, one question live at a time.
  await expect(page.getByRole("heading", { name: "What should Nura call you?" })).toBeVisible();
  await shoot(page, `${OUT}/${prefix}-07-about-name.png`, wide);
  await page.getByLabel("The name Nura uses").fill("Tan");
  await page.getByTestId("about-next").click();
  await expect(page.getByTestId("about-lang-en")).toBeVisible();
  await page.getByTestId("about-lang-en").click();
  await page.getByTestId("decade-1950").click();
  await page.getByLabel("The doctor's name").fill("Dr Tan");
  await page.getByTestId("about-next").click();
  await page.getByTestId("breakfast-07:30").click();
  for (const item of ["large_text", "high_contrast", "voice_on", "big_targets", "one_thing_per_screen", "read_back", "repeat_prompts"]) {
    await page.getByTestId(`${item}-no`).click();
  }
  // Every earlier turn still on screen, answered, above the live one.
  await expect(page.getByTestId("about-answered-name")).toBeVisible();
  await shoot(page, `${OUT}/${prefix}-08-about-transcript.png`, wide);
  await page.getByTestId("density-simple").click();

  // 7. The cloud: empty, a floating scatter of different-sized circles.
  await expect(page.locator("main.onboarding")).toHaveAttribute("data-stage", "cloud");
  await expect(page.getByTestId("cloud").locator('[data-testid^="word-"]').first()).toBeVisible();
  await assertNoBubbleTextOverflow(page, `${prefix}-09-cloud-empty`);
  await shoot(page, `${OUT}/${prefix}-09-cloud-empty.png`, wide);

  // 8. Picked: the tapped word, the words it bloomed in under it, and Nura's one line under
  // the cloud naming exactly what that tap did (docs/design/onboarding-mock.html `pick()`).
  await page.getByTestId("word-high_blood_pressure").click();
  await expect(page.getByTestId("cloud-ack")).toBeVisible();
  await page.getByTestId("word-high_blood_pressure").scrollIntoViewIfNeeded();
  await page.mouse.wheel(0, -80); // a little air above the tapped word, its bloom below it
  await assertNoBubbleTextOverflow(page, `${prefix}-10-cloud-picked`);
  await shoot(page, `${OUT}/${prefix}-10-cloud-picked.png`, wide);

  // 9. A word with a follow-up: its question opens right under the cloud, before he answers it.
  await page.getByTestId("word-bp_tablets").click();
  await expect(page.getByTestId("ask-bp_tablets")).toBeVisible();
  await page.getByTestId("ask-bp_tablets").scrollIntoViewIfNeeded();
  await assertNoBubbleTextOverflow(page, `${prefix}-11-cloud-ask`);
  await shoot(page, `${OUT}/${prefix}-11-cloud-ask.png`, wide);

  // 10. The same question, answered — his tap is the whole answer.
  await page.getByTestId("option-one_to_five_years").click();
  await expect(page.getByTestId("option-one_to_five_years")).toHaveAttribute("aria-pressed", "true");
  await assertNoBubbleTextOverflow(page, `${prefix}-11b-cloud-ask-answered`);
  await shoot(page, `${OUT}/${prefix}-11b-cloud-ask-answered.png`, wide);
  await page.getByTestId("cloud-done").click();

  // 9. Add a paper: three rows, icon + title + hint, never a stack of plain pills.
  await expect(page.locator("main.onboarding")).toHaveAttribute("data-stage", "records");
  await expect(page.getByTestId("take-photo")).toBeVisible();
  await shoot(page, `${OUT}/${prefix}-12-firstpaper.png`, wide);

  // 10. Nura reads it: his paper as a bubble, the orb and one status line.
  await page.getByTestId("photo-input").setInputFiles(paperPhoto("lipid-panel-2023-09-07"));
  await expect(page.getByTestId("paper-bubble")).toBeVisible();
  await shoot(page, `${OUT}/${prefix}-13-reading.png`, wide);
  await expect(page.getByTestId("reading-result")).toBeVisible();
  await shoot(page, `${OUT}/${prefix}-14-reading-result.png`, wide);

  // 11. The full report table.
  await page.getByTestId("see-report").click();
  await expect(page.getByTestId("review-card")).toBeVisible();
  await shoot(page, `${OUT}/${prefix}-15-report.png`, wide);
}

test.describe("cp6 register path at 390x844", () => {
  test.use({ viewport: { width: 390, height: 844 }, deviceScaleFactor: 1, isMobile: true, hasTouch: true });
  test("390x844, full-bleed, no console or page error along the way", async ({ page }) => {
    const errors: string[] = [];
    await run(page, "phone", false, errors);
    expect(errors, errors.join("\n")).toEqual([]);
  });
});

test.describe("cp6 register path at 1280x900", () => {
  test.use({ viewport: { width: 1280, height: 900 }, deviceScaleFactor: 2 });
  test("1280x900, clipped to the phone frame, no console or page error along the way", async ({ page }) => {
    const errors: string[] = [];
    await run(page, "wide", true, errors);
    expect(errors, errors.join("\n")).toEqual([]);
  });
});
