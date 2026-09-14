import { expect, test } from "@playwright/test";
import { API, apiToken, captureSpeech, freshPhone, seedMedicine, signInThroughTheApp } from "./helpers";

/** Checkpoint 9 on a phone-sized screen: sign in with a code from the log, open my own
 *  papers on today's words, see Today with the Now card, tap Taken, hear a card, sign out. */
test("sign in, agree, Today, Taken, Hear, sign out", async ({ page, request }) => {
  const phone = freshPhone();
  await captureSpeech(page);
  await signInThroughTheApp(page, phone, "Pa");

  // A fresh account: the doors, then the for-me door with today's words.
  await page.getByTestId("door-for-me").click();
  const words = page.getByTestId("consent-words");
  await expect(words).toContainText("Nura keeps your papers, your medicines and your blood pressure book.");
  await expect(words).toContainText("They never leave Singapore.");
  await page.getByTestId("agree").click();

  // Today, with no medicines yet: no spinner, one sentence, and the proud number at 0.
  await expect(page.getByTestId("no-medicines")).toContainText("Nura has no medicines for you yet.");
  await expect(page.getByTestId("proud-number")).toHaveText("0");
  await expect(page.locator("html")).toHaveAttribute("data-density", "patient");
  await expect(page.locator("html")).toHaveAttribute("data-posture", "stable");

  // Seed one medicine the way checkpoint 6 does, with a second session on the same number.
  const token = await apiToken(request, phone);
  const me = (await (await request.get(`${API}/me`, { headers: { Authorization: `Bearer ${token}` } })).json()) as { profile_id: string };
  await seedMedicine(request, token, me.profile_id, { generic: "amlodipine", strength: "5 mg", dose_text: "1 tab OM", quantity: 30 });

  // Reopen: the Now card is one drug, one big line, one paper button.
  await page.reload();
  const now = page.getByTestId("now-card");
  await expect(now).toContainText("Your blood pressure tablet");
  await expect(now).toContainText("Take 1 tablet of your blood pressure tablet with breakfast.");
  await expect(now).not.toContainText("amlodipine");
  const taken = page.getByTestId("taken");
  await expect(taken).toHaveText("Taken");
  const box = await taken.boundingBox();
  expect(box!.height).toBeGreaterThanOrEqual(56);

  // Every card has its spoken twin, and nothing was spoken before a tap.
  expect(await page.evaluate(() => (window as unknown as { __spoken: string[] }).__spoken)).toEqual([]);
  await now.getByTestId("hear").click();
  const spoken = await page.evaluate(() => (window as unknown as { __spoken: string[] }).__spoken);
  expect(spoken).toEqual(["Your blood pressure tablet", "Take 1 tablet of your blood pressure tablet with breakfast."]);

  // Taken: the tap is the yes; the card settles and the proud number goes to 1.
  await taken.click();
  await expect(page.getByTestId("all-taken")).toContainText("You have taken every tablet for today.");
  await expect(page.getByTestId("proud-number")).toHaveText("1");
  await expect(page.getByTestId("supply-card")).toContainText("You have 29 tablets of your blood pressure tablet left.");

  // The State card is there, with the boundary; the reading prompt is one action.
  await expect(page.getByTestId("state-card")).toContainText("Your day is steady.");
  await expect(page.getByTestId("state-card")).toContainText("Ask your doctor.");
  await expect(page.getByTestId("reading-prompt")).toContainText("Write down this morning's number.");

  // No badges, no counts on the tabs; the layout is vertical only.
  await expect(page.locator("nav.tabbar")).toHaveText(/^\s*Today\s*Me\s*$/);
  const scrollWidth = await page.evaluate(() => document.documentElement.scrollWidth);
  const clientWidth = await page.evaluate(() => document.documentElement.clientWidth);
  expect(scrollWidth).toBeLessThanOrEqual(clientWidth);

  // Sign out: the token is refused from then on and the phone screen is back.
  await page.getByRole("button", { name: "Me" }).click();
  await expect(page.getByText("You are signed in as Pa.")).toBeVisible();
  await page.getByTestId("sign-out").click();
  await expect(page.getByLabel("Your phone number")).toBeVisible();
  await page.reload();
  await expect(page.getByLabel("Your phone number")).toBeVisible();
});

test("a refusal is one plain sentence, never the class name", async ({ page }) => {
  const phone = freshPhone();
  await page.goto("./");
  await page.getByLabel("Your phone number").fill(phone);
  await page.getByTestId("send-code").click();
  await page.getByLabel("The code").fill("000000");
  await page.getByTestId("verify-code").click();
  const notice = page.getByTestId("notice");
  await expect(notice).toHaveText("That code is not right.");
  await expect(notice).not.toContainText("WrongCode");
});

test("the language picker changes every string and persists on the device", async ({ page }) => {
  const phone = freshPhone();
  await signInThroughTheApp(page, phone, "Pa");
  await page.getByTestId("door-for-me").click();
  await page.getByTestId("agree").click();
  await page.getByRole("button", { name: "Me" }).click();
  await page.getByTestId("lang-ms").click();
  await expect(page.locator("html")).toHaveAttribute("lang", "ms");
  await expect(page.getByTestId("sign-out")).toHaveText("Daftar keluar");
  await page.reload();
  await expect(page.locator("html")).toHaveAttribute("lang", "ms");
  await page.getByRole("button", { name: "Hari Ini" }).click();
  await expect(page.getByTestId("no-medicines")).toContainText("Nura belum ada ubat untuk anda.");
});
