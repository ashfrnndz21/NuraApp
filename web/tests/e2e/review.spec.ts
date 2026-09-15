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
  const cards = page.locator('[data-testid="review-item"][data-kind="card"]');
  await expect(cards.first()).toBeVisible();
  expect(await nothingDrawnOverLines(page.locator("main"), { lines: "h1, h2, p, .label, td, th", controls: "button, input.field" })).toEqual([]);
  expect(await page.evaluate(() => document.documentElement.scrollWidth - window.innerWidth)).toBeLessThanOrEqual(0);

  /** Decide the first card waiting, and wait for it to leave the list of the waiting. */
  const decide = async (how: (item: import("@playwright/test").Locator) => Promise<void>): Promise<string> => {
    const item = cards.first();
    const id = (await item.getAttribute("data-item"))!;
    await how(page.locator(`[data-item="${id}"]`));
    await expect(page.locator(`[data-item="${id}"]`)).toHaveCount(0);
    return id;
  };
  const approved = await decide(async (item) => item.getByTestId("review-approve").click());
  const rejected = await decide(async (item) => {
    await item.getByLabel("Why").fill("Too long for him to hear.");
    await item.getByTestId("review-reject").click();
  });
  const rewritten = await decide(async (item) => {
    await item.getByTestId("review-rewrite").click();
    await item.getByLabel("Headline").fill("Your tablets this morning");
    await item.getByTestId("review-save-rewrite").click();
  });
  await page.getByTestId("review-all").click();
  await expect(page.getByTestId("review-decided").first()).toBeVisible();

  // Each decision is the queue's, signed with the staff handle: read back over the API.
  const staff = { Authorization: `Bearer ${STAFF}` };
  const item = async (id: string) => (await (await request.get(`${API}/review/items/${id}`, { headers: staff })).json()) as { verdict: string; reason: string | null; decided_by: string | null; proposed: unknown };
  expect(await item(approved)).toMatchObject({ verdict: "approved", decided_by: "pharmacist" });
  expect(await item(rejected)).toMatchObject({ verdict: "rejected", reason: "Too long for him to hear.", decided_by: "pharmacist" });
  const proposal = await item(rewritten);
  expect(proposal.verdict).toBe("rewritten");
  expect(JSON.stringify(proposal.proposed)).toContain("Your tablets this morning");

  // Nobody is in the queue: not his profile, not his number, not his name as a person.
  const text = await page.locator("main").innerText();
  expect(text).not.toContain(pa.profileId);
  expect(text).not.toContain(pa.phone);

  // The patient app has no way in, and its service worker never keeps the staff page.
  await page.goto("./");
  await expect(page.locator('a[href*="review"]')).toHaveCount(0);
  const worker = await (await request.get(new URL("sw.js", page.url()).toString())).text();
  expect(worker).not.toContain("review/index.html");
  expect(worker).not.toMatch(/assets\/review-/);
});
