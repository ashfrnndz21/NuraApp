import { mkdirSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import { expect, test, type Page } from "@playwright/test";

const HERE = dirname(fileURLToPath(import.meta.url));

/** Board conformance pass (docs/design/nura-concept-board.html): one screenshot per board
 *  screen, per persona, at 390 by 844 (the board's own phone size), against the real demo
 *  seed — "Try it as Pa" and "Try it as Mei" on the Welcome screen (docs/deploy-demo.md),
 *  never a synthetic fixture family. Not a gate: `npm run shots -- board-conformance` writes
 *  the pictures the conformance table (docs/design/conformance.md) points to, committed under
 *  docs/design/screens/. */

const OUT = resolve(HERE, "../../../docs/design/screens");
mkdirSync(OUT, { recursive: true });

test.use({ viewport: { width: 390, height: 844 }, deviceScaleFactor: 1 });

async function shot(page: Page, name: string): Promise<void> {
  await page.evaluate(() => document.fonts.ready);
  await page.screenshot({ path: `${OUT}/${name}.png`, animations: "disabled" });
}

async function tryAs(page: Page, who: "pa" | "mei"): Promise<void> {
  await page.goto("./");
  await expect(page.getByTestId("welcome-screen")).toBeVisible();
  await shot(page, `welcome-${who}`);
  const button = page.getByTestId(who === "pa" ? "welcome-try-pa" : "welcome-try-mei");
  await expect(button).toBeVisible({ timeout: 15_000 });
  await button.click();
  await expect(page.getByTestId("welcome-screen")).toHaveCount(0, { timeout: 15_000 });
  // Mei is a chief with no papers of her own: she lands on the doors and picks Pa's key
  // (`Doors.tsx`'s "door-key"), the same tap `docs/deploy-demo.md`'s "Try it as Mei" leaves
  // for a person to make. Pa owns his own papers, so `afterSignIn` opens them at once.
  const doorKey = page.getByTestId("door-key");
  if (await doorKey.first().isVisible({ timeout: 5_000 }).catch(() => false)) await doorKey.first().click();
}

async function tab(page: Page, testId: string): Promise<void> {
  await page.getByTestId(testId).click();
  await page.waitForLoadState("networkidle", { timeout: 5_000 }).catch(() => undefined);
  await page
    .locator("main[aria-busy=true]")
    .waitFor({ state: "detached", timeout: 10_000 })
    .catch(() => undefined);
}

for (const who of ["pa", "mei"] as const) {
  test(`board screens as ${who}`, async ({ page }) => {
    await tryAs(page, who);

    await page.waitForLoadState("networkidle", { timeout: 5_000 }).catch(() => undefined);
    await shot(page, `home-${who}`);

    await tab(page, "tab-health");
    await shot(page, `health-${who}`);

    await tab(page, "tab-connect");
    await shot(page, `connect-${who}`);

    await tab(page, "tab-services");
    await shot(page, `services-${who}`);

    await tab(page, "tab-profile");
    await shot(page, `profile-${who}`);

    // Ask Nura, with the thinking trace: reached from Home's own search bar, not a tab.
    await tab(page, "tab-home");
    const ask = page.getByTestId("ask-input");
    await ask.fill("When did my blood pressure tablet change?");
    await page.getByTestId("ask-go").click();
    await expect(page.getByTestId("answer").or(page.getByTestId("ask-trace"))).toBeVisible({ timeout: 20_000 });
    await page.waitForTimeout(300);
    await shot(page, `ask-${who}`);
  });
}
