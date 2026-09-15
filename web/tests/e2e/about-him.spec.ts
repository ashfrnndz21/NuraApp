import { expect, test, type Page } from "@playwright/test";
import { signInThroughTheApp, todayReady } from "./helpers";
import { seedHome } from "./homeSeed";

/** A line that speaks to him about his own papers ("your tablets", "You have 5 left", "I am not
 *  feeling well"). "For you today" and "See more for you" speak to her, and are hers. */
const TO_HIM = /\b(your|yours|you have|you took|you see|you saw|you told|you kept|you wrote|you can|you are|when you|I am)\b/i;

async function linesOn(page: Page): Promise<string[]> {
  const text = await page.getByTestId("shell-scroll").innerText();
  return text.split("\n").map((line) => line.trim()).filter(Boolean);
}

/** D1: her screens say his papers about him by name — the backend's twins and the catalogue's —
 *  never to him; the pill is "Pa is not feeling well", the same button flow. */
test("her Home and her Medicines say his papers about him by name, never to him", async ({ page, request }) => {
  const family = await seedHome(request);
  await signInThroughTheApp(page, family.meiPhone, "Mei");
  await page.getByTestId("door-key").click();
  await todayReady(page);
  await expect(page.locator("html")).toHaveAttribute("data-density", "caregiver");
  await expect(page.getByTestId("not-well")).toHaveText(/Pa is not feeling well/);
  await expect(page.getByTestId("home-hero")).toBeVisible();
  const home = await linesOn(page);
  expect(home.filter((line) => TO_HIM.test(line))).toEqual([]);

  await page.getByTestId("tab-medicines").click();
  await expect(page.getByTestId("tab-medicines")).toHaveAttribute("aria-current", "page");
  await page.waitForLoadState("networkidle");
  const medicines = await linesOn(page);
  expect(medicines.length).toBeGreaterThan(0);
  expect(medicines.filter((line) => TO_HIM.test(line))).toEqual([]);
});
