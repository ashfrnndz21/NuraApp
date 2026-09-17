import { readFileSync } from "node:fs";
import { expect, test } from "@playwright/test";

/** The owner's comparison (docs/design/nura-concept-board.html): each built screen beside the
 *  board's matching phone, one picture each, into `tests/visual/warm/`. Not a gate. Run after
 *  `warm.spec.ts`, which takes the built screens. */

const WARM = new URL("./warm/", import.meta.url).pathname;
const BOARD = new URL("../../../docs/design/nura-concept-board.html", import.meta.url).pathname;

const PAIRS = [
  { board: 0, built: "welcome-patient-390x844.png", name: "beside-board-welcome" },
  { board: 1, built: "home-patient-390x844.png", name: "beside-board-home" },
  { board: 1, built: "home-caregiver-390x844.png", name: "beside-board-home-caregiver" },
] as const;

test("each built screen beside the board's", async ({ browser }) => {
  const page = await browser.newPage({ viewport: { width: 1600, height: 1000 }, deviceScaleFactor: 2 });
  await page.goto(`file://${BOARD}`);
  await expect(page.locator(".phone").first()).toBeVisible();
  const phones: Buffer[] = [];
  for (let at = 0; at < 2; at++) phones.push(await page.locator(".phone").nth(at).screenshot());
  for (const pair of PAIRS) {
    const built = readFileSync(`${WARM}${pair.built}`).toString("base64");
    const board = phones[pair.board]!.toString("base64");
    await page.setContent(`<body style="margin:0;background:#efe6e0;font:600 15px system-ui;color:#2c2733">
      <div style="display:inline-flex;gap:32px;padding:24px;align-items:flex-start">
        <figure style="margin:0"><img src="data:image/png;base64,${board}" style="width:300px;display:block;border-radius:34px"><figcaption style="text-align:center;padding-top:8px">The approved board</figcaption></figure>
        <figure style="margin:0"><img src="data:image/png;base64,${built}" style="width:320px;display:block;border-radius:24px"><figcaption style="text-align:center;padding-top:8px">Built, with real data (390 × 844)</figcaption></figure>
      </div></body>`);
    await page.locator("div").first().screenshot({ path: `${WARM}${pair.name}.png` });
  }
});
