import { expect, test, type APIRequestContext } from "@playwright/test";
import { BASE_URL, FROZEN_CLOCK } from "../../playwright.config";
import { API, backendClock, fixClock, signInThroughTheApp, todayReady } from "./helpers";
import { auth, caregiverScreenOk, cutKey, patientScreenOk, seedFamily, type Family } from "./familySeed";

/** Connect, from the nav (docs/design/nura-concept-board.html, the Connect screen): the tab's
 *  own overview — his family, his next call, near him, and the family thread — in front of the
 *  Family screens each row still opens; against `make dev` serving the build, both clocks at
 *  10 in the morning in Singapore on Monday 14 September. */

test.beforeAll(async ({ request }) => {
  const backend = await backendClock(request);
  if (!backend.frozen || Date.parse(backend.now) !== Date.parse(FROZEN_CLOCK)) {
    throw new Error(`the backend's clock is not frozen at ${FROZEN_CLOCK} (it says ${JSON.stringify(backend)})`);
  }
});

test.beforeEach(async ({ page }) => {
  await fixClock(page);
});

async function ok(what: string, answer: { ok(): boolean; status(): number; text(): Promise<string> }): Promise<void> {
  if (!answer.ok()) throw new Error(`${what}: ${answer.status()} ${await answer.text()}`);
}

/** A call with Kit, Saturday 19 September at 7:30 in the evening, the same call the approved
 *  board draws — put on the calendar by Mei, his chief, on her own yes, exactly the way
 *  `family/Calls.tsx` mints one. */
async function seedCall(request: APIRequestContext, family: Family): Promise<void> {
  const scheduled_at = "2026-09-19T19:30:00+08:00";
  const minted = await request.post(`${API}/profiles/${family.profileId}/confirmations`, {
    headers: auth(family.mei.token),
    data: { subject: "call", with_person_id: family.kit.personId, scheduled_at, call_link: null },
  });
  await ok("mint call", minted);
  const { confirmation_id } = (await minted.json()) as { confirmation_id: string };
  await ok(
    "schedule call",
    await request.post(`${API}/profiles/${family.profileId}/calls`, {
      headers: auth(family.mei.token),
      data: { with_person_id: family.kit.personId, scheduled_at, call_link: null, label: null, confirmation_id },
    }),
  );
}

test("Pa's Connect: his family, his next call, and the family thread, one glance each", async ({ page, request }) => {
  const family = await seedFamily(request);
  await seedCall(request, family);
  await signInThroughTheApp(page, family.pa.phone, "Pa");
  await todayReady(page);

  await page.getByTestId("tab-connect").click();
  const screen = page.getByTestId("connect-screen");
  await expect(screen).toBeVisible();
  await expect(page.locator("h1")).toHaveText("Connect");

  // "Your family": Mei, Kit and Siti, each with a key, drawn as an avatar and a role; a tap on
  // one opens the existing keys screen — never a second screen invented for the same row.
  await expect(page.getByTestId("connect-family-member")).toHaveCount(2); // Mei (chief) and Kit (caregiver); Siti holds no key yet
  await expect(page.getByTestId("connect-family-member").filter({ hasText: "Mei" })).toBeVisible();
  await page.getByTestId("connect-family-member").filter({ hasText: "Kit" }).click();
  await expect(page.getByTestId("family-keys")).toBeVisible();
  await expect(page.getByTestId("grant").filter({ hasText: "Kit" })).toBeVisible();
  expect(await patientScreenOk(page)).toEqual([]);

  await page.getByTestId("tab-connect").click();
  // "Next call": Kit, Saturday 19 September, 7:30 in the evening; "Change" opens the calls
  // screen (#235's own model, the calling screen this PR builds for it).
  const callCard = page.getByTestId("connect-call-card");
  await expect(callCard).toContainText("Saturday 19 September");
  await expect(callCard).toContainText("7:30");
  await page.getByTestId("connect-change-call").click();
  await expect(page.getByTestId("family-calls")).toBeVisible();
  await expect(page.getByTestId("call-row")).toContainText("Kit");

  await page.getByTestId("tab-connect").click();
  // "Near you": nothing was seeded local to him today, so the section says so — never a stub
  // tile standing in for a feature that is not built.
  await expect(page.getByTestId("connect-no-near-you")).toBeVisible();

  // "Messages": Kit's word to the family shows on Connect, in the backend's own line, and
  // opens the same thread screen the Family menu's "Messages" opens.
  await ok("message", await request.post(`${API}/profiles/${family.profileId}/thread`, { headers: auth(family.kit.token), data: { text: "I will visit on Sunday." } }));
  await page.reload();
  await todayReady(page);
  await page.getByTestId("tab-connect").click();
  await expect(page.getByTestId("connect-message-row").first()).toContainText("I will visit on Sunday.");
  await page.getByTestId("connect-message-row").first().click();
  await expect(page.getByTestId("family-thread")).toBeVisible();

  // Back on Connect, every section remounts and re-fetches (D1: a fresh screen, not a cache) —
  // wait for the section that fetches last to carry real words again before scanning the
  // layout, or the scan can catch a line mid-swap (an empty-state paragraph Preact is about to
  // replace with the message row), which reads as "covered" by whatever sits at (0,0) once the
  // stale node's rect has collapsed to nothing — the header, not a real layout fault.
  await page.getByTestId("tab-connect").click();
  await expect(page.getByTestId("connect-message-row").first()).toContainText("I will visit on Sunday.");
  expect(await patientScreenOk(page)).toEqual([]);
});

test("Mei's Connect: his family, his next call and near him, said about Pa by name — a key without the family scope sees no Connect tab", async ({ page, request, browser }) => {
  const family = await seedFamily(request, { sitiKey: true });
  await seedCall(request, family);
  await signInThroughTheApp(page, family.mei.phone, "Mei");
  await page.getByTestId("door-key").click();
  await todayReady(page);

  await page.getByTestId("tab-connect").click();
  await expect(page.locator("h1")).toHaveText("Connect");
  // The existing rule (#237): the tabs are the same list for everyone, filtered by what a key
  // opens — Mei's caregiver key holds the family scope, so Connect is on her bar too.
  await expect(page.getByTestId("tab-connect")).toBeVisible();
  await expect(page.getByTestId("connect-family").locator("h2")).toHaveText("Pa's family");
  const callCard = page.getByTestId("connect-call-card");
  await expect(callCard).toContainText("Kit");
  expect(await caregiverScreenOk(page)).toEqual([]);

  // Siti's key was cut with no family scope (`SITIS` in familySeed.ts): Connect never reaches
  // her bar, because the tab a key does not open is left off before a tap could ask the
  // backend for it (`nav.ts`). A browser of her own, the way family.spec.ts's `secondPhone`
  // is: Mei's session lives in local storage, which a cookie clear on the same context never
  // touches.
  const sitiContext = await browser.newContext({ baseURL: BASE_URL, viewport: { width: 360, height: 640 }, timezoneId: "Asia/Singapore", serviceWorkers: "allow" });
  const sitiPage = await sitiContext.newPage();
  await fixClock(sitiPage);
  await signInThroughTheApp(sitiPage, family.siti.phone, "Siti");
  await sitiPage.getByTestId("door-key").click();
  await expect(sitiPage.getByTestId("open-me")).toBeVisible();
  await expect(sitiPage.getByTestId("tab-connect")).toHaveCount(0);
  await sitiContext.close();
});
