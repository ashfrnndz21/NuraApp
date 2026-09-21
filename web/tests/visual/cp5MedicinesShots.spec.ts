import { mkdirSync } from "node:fs";
import { expect, test, type Page } from "@playwright/test";
import { fixClock, openMe, seedMedicine } from "../e2e/helpers";
import { letIn, openOwn, openRecord, placeholderPng, signInAs, type Papers } from "../e2e/record-helpers";

/** Package 11 ("Your tablets", and Add a medicine by photo, screenshot or typing): screen
 *  captures of the real app. Signed in through the app's own screens (`signInAs`) exactly as
 *  every end-to-end test does; the account itself is opened over the API first
 *  (`openOwn`/`letIn`, the same helper `record-medicines.spec.ts` already uses for every one
 *  of its walks) so each shot starts from a clean, known state rather than the demo Pa's own
 *  four medicines, which would make a fresh add read as a dose change. The fixture extractor
 *  is what the dev server runs in this build (`NURA_EXTRACTOR=fixture`, `make dev`'s own
 *  default), so a placeholder photo reads for real, exactly as an end-to-end test's does —
 *  nothing shown here is a mocked screenshot of invented data.
 *
 *  Not a gate — `npx playwright test -c playwright.visual.config.ts tests/visual/
 *  cp5MedicinesShots.spec.ts` writes pictures for a person to look at, into
 *  `NURA_MEDICINES_SHOTS` (default: this checkpoint's own folder under the scratchpad). */

const OUT = process.env.NURA_MEDICINES_SHOTS ?? "/private/tmp/claude-501/-Users-ashleyfernandez-SingleIDContext/e8f60261-760e-4178-a18b-74e3888c414c/scratchpad/shots/cp5-medicines";
mkdirSync(OUT, { recursive: true });

test.use({ actionTimeout: 20_000 });

test.beforeEach(async ({ page }) => {
  await fixClock(page);
});

async function openMedicines(page: Page): Promise<void> {
  await openRecord(page);
  await page.getByTestId("record-medicines").click();
  await expect(page.getByTestId("record-medicines")).toBeVisible();
  await page.waitForFunction(() => document.querySelector("main")?.getAttribute("aria-busy") !== "true");
}

async function shoot(page: Page, target: Page | ReturnType<Page["locator"]>, name: string): Promise<void> {
  await page.evaluate(() => document.fonts.ready);
  await target.screenshot({ path: `${OUT}/${name}.png`, animations: "disabled" });
}

interface Seeded {
  pa: Papers;
}

async function seed(request: import("@playwright/test").APIRequestContext): Promise<Seeded> {
  const pa = await openOwn(request);
  return { pa };
}

const VIEWPORTS: readonly { name: string; width: number; height: number; frame: boolean }[] = [
  { name: "phone", width: 390, height: 844, frame: false },
  { name: "wide", width: 1280, height: 900, frame: true },
];

for (const vp of VIEWPORTS) {
  test.describe(`cp5 Medicines at ${vp.width}x${vp.height}`, () => {
    test.use({ viewport: { width: vp.width, height: vp.height }, deviceScaleFactor: vp.frame ? 2 : 1, isMobile: !vp.frame, hasTouch: !vp.frame });
    const target = (page: Page) => (vp.frame ? page.locator("#phone-frame") : page);

    test("an empty registry, then three medicines, a row's sheet, and the add entry point", async ({ page, request }) => {
      const { pa } = await seed(request);
      await signInAs(page, pa, "Pa");
      await openMedicines(page);
      await expect(page.getByTestId("no-medicines")).toBeVisible();
      await shoot(page, target(page), `${vp.name}-registry-empty`);

      await page.getByTestId("add-medicine-empty").click();
      await expect(page.getByTestId("add-entry")).toBeVisible();
      await shoot(page, target(page), `${vp.name}-add-entry`);

      // A first medicine: warfarin's own dispensing-label fixture. Its printed strength
      // (5 mg) is not the one on file (3 mg — a high-risk generic, so a mismatch is never
      // silently taken); "Fix" corrects it, the same typed form prefilled with what was read.
      await page.getByTestId("photo-input").setInputFiles({ name: "warfarin.png", mimeType: "image/png", buffer: placeholderPng("warfarin-label-2024-03-12") });
      await expect(page.getByTestId("add-confirm")).toBeVisible();
      await shoot(page, target(page), `${vp.name}-confirmation-card`);
      await page.getByTestId("looks-right").click();
      await expect(page.getByTestId("notice")).toBeVisible();
      await page.getByTestId("add-fix").click();
      await page.getByLabel("How strong it is").fill("3 mg");
      await page.getByTestId("check-medicine").click();
      await expect(page.getByTestId("add-check")).toBeVisible();
      await page.getByTestId("add-it").click();
      await expect(page.getByTestId("add-done")).toBeVisible();
      await shoot(page, target(page), `${vp.name}-after-confirm-connection`);
      await page.getByTestId("see-in-registry").click();

      // A second, typed in: no photo at all.
      await page.getByTestId("add-medicine").click();
      await page.getByTestId("add-type-it").click();
      await expect(page.getByTestId("add-label")).toBeVisible();
      await shoot(page, target(page), `${vp.name}-typed-entry`);
      await page.getByLabel("The name on the label").fill("fish oil");
      await page.getByLabel("How strong it is").fill("1000 mg");
      await page.getByLabel("The form (tablet, capsule, inhaler…)").fill("capsule");
      await page.getByLabel("How to take it").fill("1 cap OD");
      await page.getByTestId("check-medicine").click();
      await expect(page.getByTestId("add-check")).toBeVisible();
      await page.getByTestId("add-it").click();
      await expect(page.getByTestId("add-done")).toBeVisible();
      await page.getByTestId("see-in-registry").click();

      // A third, a box naming only its family — the which-one question.
      await page.getByTestId("add-medicine").click();
      await page.getByTestId("photo-input").setInputFiles({ name: "statin.png", mimeType: "image/png", buffer: placeholderPng("statin-box-2026-09-19") });
      await expect(page.getByTestId("add-confirm")).toBeVisible();
      await page.getByTestId("looks-right").click();
      await expect(page.getByTestId("add-which")).toBeVisible();
      await shoot(page, target(page), `${vp.name}-which-statin`);
      await page.getByTestId("which-atorvastatin").click();
      await expect(page.getByTestId("add-check")).toBeVisible();
      await page.getByTestId("add-it").click();
      await expect(page.getByTestId("add-done")).toBeVisible();
      await page.getByTestId("see-in-registry").click();

      // Patient density shows one row a screen (`Paged`); switching to caregiver density
      // shows the whole list at once, for a shot with all three in frame together.
      await openMe(page);
      await page.getByTestId("density-caregiver").click();
      await page.keyboard.press("Escape");
      await expect(page.getByTestId("me-sheet")).toHaveCount(0);
      await expect(page.getByTestId("medicine-line")).toHaveCount(3);
      await shoot(page, target(page), `${vp.name}-registry-three`);

      await page.getByTestId("medicine-line-open").first().click();
      await expect(page.getByTestId("medicine-sheet")).toBeVisible();
      await shoot(page, target(page), `${vp.name}-medicine-sheet`);
    });

    test("Mei's view of the registry", async ({ page, request }) => {
      const { pa } = await seed(request);
      await seedMedicine(request, pa.token, pa.profileId, { generic: "amlodipine", strength: "5 mg", dose_text: "1 tab OD", quantity: 30 });
      const mei = await letIn(request, pa, "Mei", "chief", ["medicines"]);
      await signInAs(page, mei, "Mei", true);
      await openRecord(page);
      await page.getByTestId("record-medicines").click();
      await expect(page.getByTestId("medicine-line")).toBeVisible();
      await shoot(page, target(page), `${vp.name}-mei-view`);
    });
  });
}
