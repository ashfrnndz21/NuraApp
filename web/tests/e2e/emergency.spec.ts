import { expect, test, type Page } from "@playwright/test";
import { BASE_URL } from "../../playwright.config";
import { API, cutKey, expireEveryKeptPage, fixClock, keptKeys, medicinesInIndexedDb, seedOwner, signInThroughTheApp, waitForWorker, todayReady} from "./helpers";

/** The emergency card on the phone (E13-01's web half, ADR 0001's "the card one tap away"; its
 *  offline copy is E00-08's): read from `GET …/emergency-card`, the backend's lines and nothing
 *  else, the numbers to call as buttons, a big Print of the backend's printable page, readable
 *  with no network and still there past midnight (ADR 0010), and gone at sign-out. A neighbour's
 *  key to the card alone opens that card and nothing else. */

test.beforeEach(async ({ page }) => {
  await fixClock(page);
});

const auth = (token: string) => ({ headers: { Authorization: `Bearer ${token}` } });
const EVERY_PART = ["medicines", "visits", "readings", "records", "notes", "money", "family", "emergency", "ask", "send"];
interface CardOut {
  lines: { id: string; text: string }[];
}
const kept = (text: string) => /^(today|feed|queue|emergency)\./.test(text);

test("the emergency card, one tap from Today and from Me: the backend's lines only, Print opens its printable page, readable with no network and still there past midnight", async ({ page, context, request }) => {
  test.skip(BASE_URL.includes(":5173"), "needs the built app the backend serves (the worker is not built in dev)");
  const pa = await seedOwner(request);
  const mei = await cutKey(request, pa, { name: "Mei", prefix: "+659557" }, "chief", EVERY_PART);
  const card = (await (await request.get(`${API}/profiles/${pa.profileId}/emergency-card?language=en`, auth(pa.token))).json()) as CardOut;
  const lines = card.lines.map((line) => line.text);
  expect(lines).toContain("This is Pa's emergency card.");

  await signInThroughTheApp(page, pa.phone, "Pa");
  await todayReady(page);
  await page.getByTestId("open-emergency").click();
  await expect(page.locator("main h1")).toHaveText("Emergency card");
  await expect(page.locator("main h1")).toBeFocused();
  const shown = page.getByTestId("emergency-card");
  // Exactly the backend's lines, in its order: the client composes none of them.
  await expect(shown.getByTestId("emergency-lines").locator("p")).toHaveText(lines);
  await expect(shown.getByTestId("call-contact")).toHaveText("Call Mei");
  await expect(shown.getByTestId("call-contact")).toHaveAttribute("href", `tel:${mei.phone}`);
  await expect(shown.getByTestId("call-ambulance")).toHaveText("Call the ambulance on 995");
  await expect(shown.getByTestId("call-ambulance")).toHaveAttribute("href", "tel:995");

  // Print: the backend's printable page, opened from the copy the phone keeps.
  const [printable] = await Promise.all([context.waitForEvent("page"), shown.getByTestId("print-card").click()]);
  await printable.waitForLoadState();
  expect(printable.url()).toMatch(/^blob:/);
  await expect(printable.locator("body")).toContainText("This is Pa's emergency card.");
  await printable.close();

  // From Me, the same card.
  await page.getByTestId("open-me").click();
  await page.getByTestId("me-emergency").click();
  await expect(page.getByTestId("emergency-card").getByTestId("emergency-lines").locator("p")).toHaveText(lines);

  // No network, the next morning: nothing of the day on the phone, and the card still there,
  // dated, printable.
  await page.getByTestId("tab-home").click();
  await todayReady(page);
  await waitForWorker(page);
  // The printable page is read just after the card: kept on the phone before the network goes.
  await expect.poll(() => printableKept(page, pa.profileId)).toBe(true);
  await context.setOffline(true);
  expect(await expireEveryKeptPage(page)).toBeGreaterThan(0);
  await page.reload();
  await expect(page.getByTestId("cannot-reach")).toContainText("Nura cannot reach your papers right now.");
  const offline = page.getByTestId("emergency-card");
  await expect(offline.getByTestId("emergency-lines").locator("p")).toHaveText(lines);
  await expect(offline.getByTestId("emergency-read")).toHaveText("Nura last read this card on Monday 14 September.");
  const [offlinePrint] = await Promise.all([context.waitForEvent("page"), offline.getByTestId("print-card").click()]);
  await offlinePrint.waitForLoadState();
  await expect(offlinePrint.locator("body")).toContainText("This is Pa's emergency card.");
  await offlinePrint.close();
  expect(await medicinesInIndexedDb(page)).toEqual([]);
  expect(await medicinesInIndexedDb(page, { card: true })).toHaveLength(1);
  expect(await page.locator("[role=progressbar], .spinner").count()).toBe(0);
  await context.setOffline(false);

  // Sign-out leaves none of it on the phone.
  await page.reload();
  await todayReady(page);
  await page.getByTestId("open-me").click();
  await page.getByTestId("sign-out").click();
  await expect(page.getByLabel("Your phone number")).toBeVisible();
  expect((await keptKeys(page)).filter(kept)).toEqual([]);
});

test("her density: the chief reads the same card, one tap from Today", async ({ page, request }) => {
  const pa = await seedOwner(request);
  const mei = await cutKey(request, pa, { name: "Mei", prefix: "+659557" }, "chief", EVERY_PART);
  const card = (await (await request.get(`${API}/profiles/${pa.profileId}/emergency-card?language=en`, auth(pa.token))).json()) as CardOut;
  await signInThroughTheApp(page, mei.phone, "Mei");
  await page.getByTestId("door-key").click();
  await expect(page.locator("html")).toHaveAttribute("data-density", "caregiver");
  await page.getByTestId("open-emergency").click();
  await expect(page.getByTestId("emergency-card").getByTestId("emergency-lines").locator("p")).toHaveText(card.lines.map((line) => line.text));
});

test("a neighbour's key to the emergency card alone opens that card and nothing else", async ({ page, request }) => {
  const pa = await seedOwner(request);
  const kim = await cutKey(request, pa, { name: "Kim", prefix: "+659558" }, "emergency", ["emergency"]);
  const card = (await (await request.get(`${API}/profiles/${pa.profileId}/emergency-card?language=en`, auth(kim.token))).json()) as CardOut;
  await signInThroughTheApp(page, kim.phone, "Kim");
  await page.getByTestId("door-key").click();
  const shown = page.getByTestId("emergency-card");
  await expect(shown.getByTestId("emergency-lines").locator("p")).toHaveText(card.lines.map((line) => line.text));
  for (const none of ["now-card", "today-list", "medicines-card", "state-card", "open-feed", "proud", "reading-prompt", "open-visit", "notice"]) {
    await expect(page.getByTestId(none)).toHaveCount(0);
  }
  await expect(page.getByRole("button", { name: "Go back" })).toHaveCount(0);
  await page.getByTestId("tab-home").click();
  await expect(page.getByTestId("emergency-card")).toBeVisible();
  await page.getByTestId("open-me").click();
  await expect(page.getByTestId("set-up")).toHaveCount(0);
  await expect(page.getByTestId("open-papers")).toHaveCount(0);
  await page.getByTestId("me-emergency").click();
  await expect(page.getByTestId("emergency-card")).toBeVisible();
});

test("the medicine data: the register's chemical name and strength are visible on the phone screen for every medicine, even when the sentence cannot carry it, in English, Malay and Chinese, with the high-risk marker where it applies", async ({ page, request }) => {
  // frusemide: glossary-safe, its sentence also carries it. paracetamol: a #202-era generic
  // not in the glossary — its sentence says only "the pain tablet.", never "paracetamol"
  // (#222). warfarin: high-risk. Walking the rendered screen, not the JSON (#229) — a JSON
  // test is exactly how this got through the first time.
  const pa = await seedOwner(request, "Pa", [
    { generic: "frusemide", strength: "40 mg", dose_text: "1 tab OD morning", quantity: 30 },
    { generic: "paracetamol", strength: "500 mg", dose_text: "1 tab TDS", quantity: 30 },
    { generic: "warfarin", strength: "3 mg", dose_text: "1 tab ON", quantity: 30 },
  ]);
  await signInThroughTheApp(page, pa.phone, "Pa");
  await todayReady(page);
  await page.getByTestId("open-emergency").click();
  const shown = page.getByTestId("emergency-card");
  const rows = shown.getByTestId("medicine-chemical-name");
  await expect(rows).toHaveCount(3);
  const texts = await rows.allTextContents();
  expect(texts.some((one) => one.includes("frusemide") && one.includes("40 mg"))).toBe(true);
  expect(texts.some((one) => one.includes("paracetamol") && one.includes("500 mg"))).toBe(true);
  const warfarinRow = texts.find((one) => one.includes("warfarin"));
  expect(warfarinRow).toBeDefined();
  expect(warfarinRow).toContain("3 mg");
  expect(warfarinRow).toContain("high-risk");
  // The sentence itself never says "paracetamol" — proof the data row, not the sentence, is
  // what carries it here.
  const lines = await shown.getByTestId("emergency-lines").locator("p").allTextContents();
  expect(lines.some((one) => one.includes("paracetamol"))).toBe(false);
  expect(lines.some((one) => one.includes("frusemide"))).toBe(true);
  await page.getByRole("button", { name: "Me", exact: true }).click();
  await page.getByTestId("sign-out").click();

  // Malay and Chinese: the sentence never carries a chemical name in either language, but the
  // data row does — the register's name and strength are the register's, not translated.
  for (const language of ["ms", "zh"] as const) {
    const person = await seedOwner(request, "Pa", [{ generic: "paracetamol", strength: "500 mg", dose_text: "1 tab TDS", quantity: 30 }], language);
    await signInThroughTheApp(page, person.phone, "Pa");
    await todayReady(page);
    await page.getByTestId("open-emergency").click();
    const dataRows = page.getByTestId("emergency-card").getByTestId("medicine-chemical-name");
    await expect(dataRows).toHaveCount(1);
    await expect(dataRows).toContainText("paracetamol");
    await expect(dataRows).toContainText("500 mg");
    await page.getByRole("button", { name: "Me", exact: true }).click();
    await page.getByTestId("sign-out").click();
  }
});

test.describe("on an iPhone in Safari, before Nura is on the home screen", () => {
  test.use({ userAgent: "Mozilla/5.0 (iPhone; CPU iPhone OS 17_5 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.5 Mobile/15E148 Safari/604.1" });

  test("the emergency card says how to add Nura to the home screen", async ({ page, request }) => {
    const pa = await seedOwner(request);
    await signInThroughTheApp(page, pa.phone, "Pa");
    await page.getByTestId("open-emergency").click();
    const hint = page.getByTestId("home-screen-hint");
    await expect(hint).toContainText("You can add Nura to your home screen.");
    await expect(hint).toContainText("Then tap Add to Home Screen.");
  });
});

/** The card's printable page, kept with it on the phone (read just after the card). */
async function printableKept(page: Page, profileId: string): Promise<boolean> {
  return page.evaluate(
    (key) =>
      new Promise<boolean>((resolve) => {
        const opened = indexedDB.open("nura", 1);
        opened.onsuccess = () => {
          const got = opened.result.transaction("kv", "readonly").objectStore("kv").get(key);
          got.onsuccess = () => resolve(typeof (got.result as { html?: unknown } | undefined)?.html === "string");
          got.onerror = () => resolve(false);
        };
        opened.onerror = () => resolve(false);
      }),
    `emergency.${profileId}`,
  );
}
