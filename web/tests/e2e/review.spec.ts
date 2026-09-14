import { expect, test } from "@playwright/test";
import { API, nothingDrawnOverLines, seedFeed } from "./helpers";

/** The pharmacist's queue (E22-04, ADR 0007) on the web: its own page at /app/review/, signed
 *  in with a staff token from the deployment's list, never a patient's session, never linked
 *  from the patient app and never kept by its service worker. It shows no profile: the queue
 *  holds none. */

const STAFF = "nura-dev-pharmacist-token-0001";

test.use({ viewport: { width: 360, height: 640 } });

test("the pharmacist's queue: a patient's token refused, the staff token opens it, approve, reject with a reason, rewrite as a proposal; nobody in it", async ({ page, request }) => {
  const pa = await seedFeed(request);
  // His feed rendered: the first cards of each type are sampled for review, with nobody in them.
  expect((await request.get(`${API}/profiles/${pa.profileId}/feed`, { headers: { Authorization: `Bearer ${pa.token}` } })).status()).toBe(200);

  await page.goto("review/");
  await page.getByLabel("Staff token").fill(pa.token);
  await page.getByTestId("review-open").click();
  await expect(page.getByTestId("notice")).toContainText("Only Nura's pharmacist can open this.");

  await page.getByLabel("Staff token").fill(STAFF);
  await page.getByTestId("review-open").click();
  await expect(page.getByTestId("review-status")).toBeVisible();
  await expect(page.getByTestId("review-type").first()).toBeVisible();
  const cards = page.getByTestId("review-item").filter({ hasText: "card" });
  await expect(cards.first()).toBeVisible();
  expect(await nothingDrawnOverLines(page.locator("main"), { lines: "h1, h2, p, .label, td, th", controls: "button, input.field" })).toEqual([]);
  expect(await page.evaluate(() => document.documentElement.scrollWidth - window.innerWidth)).toBeLessThanOrEqual(0);

  await cards.first().getByTestId("review-approve").click();
  await expect(page.getByTestId("review-status")).toBeVisible();
  await cards.first().getByLabel("Why").fill("Too long for him to hear.");
  await cards.first().getByTestId("review-reject").click();
  await expect(page.getByTestId("review-status")).toBeVisible();
  await cards.first().getByTestId("review-rewrite").click();
  await cards.first().getByLabel("Headline").fill("Your tablets this morning");
  await cards.first().getByTestId("review-save-rewrite").click();

  await page.getByTestId("review-all").click();
  const decided = page.getByTestId("review-decided");
  await expect(decided.filter({ hasText: "approved" }).first()).toBeVisible();
  await expect(decided.filter({ hasText: "Too long for him to hear." }).first()).toContainText("rejected");
  await expect(decided.filter({ hasText: "rewritten" }).first()).toBeVisible();

  // Nobody is in the queue: not his profile, not his number, not his name as a person.
  const text = await page.locator("main").innerText();
  expect(text).not.toContain(pa.profileId);
  expect(text).not.toContain(pa.phone);

  // The patient app has no way in, and its service worker never keeps the staff page.
  await page.goto("./");
  await expect(page.locator('a[href*="review"]')).toHaveCount(0);
  const worker = await (await request.get(new URL("sw.js", page.url()).toString())).text();
  expect(worker).not.toContain("review");
});
