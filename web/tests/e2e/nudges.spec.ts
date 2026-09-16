import AxeBuilder from "@axe-core/playwright";
import { expect, test, type APIRequestContext, type Request } from "@playwright/test";
import { FROZEN_CLOCK } from "../../playwright.config";
import { API, backendClock, captureSpeech, fixClock, nothingDrawnOverLines, seedOwner, setBackendClock, signInThroughTheApp, todayReady} from "./helpers";

/** E17-03's web half: the day's nudge on Today (E11-07 put it there, PR #138; this closes what
 *  was left — the dismiss round trip, the quiet day it leaves behind, both densities, and axe).
 *  Every assertion reads the backend's own answer rather than a line this file guesses at: the
 *  client composes no sentence, so a test that hard-codes one is testing the wrong thing. */

const auth = (token: string) => ({ headers: { Authorization: `Bearer ${token}` } });
const posted = (path: RegExp) => (sent: { request(): Request } | Request) => {
  const req = "request" in sent && typeof sent.request === "function" ? sent.request() : (sent as Request);
  return req.method() === "POST" && path.test(new URL(req.url()).pathname);
};

test.beforeAll(async ({ request }) => {
  const backend = await backendClock(request);
  if (!backend.frozen || Date.parse(backend.now) !== Date.parse(FROZEN_CLOCK)) {
    throw new Error(`the backend's clock is not frozen at ${FROZEN_CLOCK} (it says ${JSON.stringify(backend)})`);
  }
});

test.beforeEach(async ({ page }) => {
  await fixClock(page);
  await captureSpeech(page);
});

async function medicineLine(request: APIRequestContext, token: string, profileId: string): Promise<string> {
  const lines = (await (await request.get(`${API}/profiles/${profileId}/medicines?language=en`, auth(token))).json()) as { line_id: string }[];
  return lines[0]!.line_id;
}

/** A profile with no medicine at all: no state change for a check-in to answer, so the plan's
 *  one draft is presence's quiet-week line ("Nura is here if you need it."), rendered as the
 *  tile — a check-in draft would never show here regardless, since the feeling cloud is the
 *  check-in while it is on Today (`web/src/day/TodayDay.tsx`). */
const bareOwner = (request: APIRequestContext) => seedOwner(request, "Pa", []);

test("he can act on the day's nudge or dismiss it: Not today is a real round trip, not just the tile going away", async ({ page, request }) => {
  const pa = await bareOwner(request);
  const plan = (await (await request.get(`${API}/profiles/${pa.profileId}/nudges/plan`, auth(pa.token))).json()) as { drafts: { kind: string; lines: string[]; why: string }[] };
  const draft = plan.drafts[0]!;
  await signInThroughTheApp(page, pa.phone, "Pa");
  const nudge = page.getByTestId("nudge");
  await expect(nudge.getByTestId("nudge-lines").locator("p")).toHaveText(draft.lines);
  await expect(nudge.getByTestId("nudge-why")).toHaveText(draft.why);

  const handed = page.waitForResponse(posted(/\/nudges\/plan$/));
  const answered = page.waitForResponse(posted(/\/nudges\/[^/]+\/response$/));
  await nudge.getByTestId("nudge-dismiss").click();
  expect((await handed).status()).toBe(201);
  expect((await answered).request().postDataJSON()).toEqual({ kind: "dismissed" });
  await expect(page.getByTestId("nudge")).toHaveCount(0);

  // The round trip, proved on the row the engine kept, not the tile going away: the day's
  // nudge carries his "Not today" back (`GET /nudges`), which is what feeds the engine's
  // ranking (docs/smart-nudges.md §1) — a dismissal the client never sent could not do that.
  const day = (await (await request.get(`${API}/profiles/${pa.profileId}/nudges`, auth(pa.token))).json()) as { nudges: { kind: string; responses: string[] }[] };
  expect(day.nudges).toHaveLength(1);
  expect(day.nudges[0]).toMatchObject({ kind: draft.kind, responses: ["dismissed"] });
});

test("one a day, honoured on the client too: once the day's nudge is handled, the surface stays quiet for the rest of that day", async ({ page, request }) => {
  const pa = await bareOwner(request);
  await signInThroughTheApp(page, pa.phone, "Pa");
  const nudge = page.getByTestId("nudge");
  await expect(nudge).toBeVisible();
  await nudge.getByTestId("nudge-dismiss").click();
  await expect(page.getByTestId("nudge")).toHaveCount(0);

  // Hours pass on his phone, still the same day (region midnight, the offline cache's own
  // expiry key): nothing reappears, not the dismissed kind and not a different one either —
  // the cap was spent for the day, and the client never fills it back in from the plan.
  await page.clock.fastForward("06:00");
  await expect(page.getByTestId("nudge")).toHaveCount(0);
  // Reloading reads the backend fresh, which is the strongest version of "nothing to show":
  // not a client that merely forgot, but the same answer read again.
  await page.reload();
  await todayReady(page);
  await expect(page.getByTestId("nudge")).toHaveCount(0);
});

test("none on a day with a red flag: the client shows no nudge once one has been raised today", async ({ page, request }) => {
  const pa = await bareOwner(request);
  const plan = (await (await request.get(`${API}/profiles/${pa.profileId}/nudges/plan`, auth(pa.token))).json()) as { drafts: unknown[] };
  expect(plan.drafts.length).toBeGreaterThan(0); // a nudge was due today, before the flag
  const flagged = await request.post(`${API}/profiles/${pa.profileId}/feelings`, { ...auth(pa.token), data: { word: "chest_tightness", language: "en" } });
  expect(flagged.ok(), await flagged.text()).toBe(true);
  const afterFlag = (await (await request.get(`${API}/profiles/${pa.profileId}/nudges/plan`, auth(pa.token))).json()) as { none_because: string | null };
  expect(afterFlag.none_because).toBe("red_flag");

  await signInThroughTheApp(page, pa.phone, "Pa");
  // The red flag opens the urgent card first; Today itself carries no nudge, today or after.
  await expect(page.getByTestId("nudge")).toHaveCount(0);
});

test("a dismissal feeds ranking: the kind he sends away today is not the kind the engine leads with tomorrow", async ({ page, request }) => {
  const pa = await seedOwner(request);
  const lineId = await medicineLine(request, pa.token, pa.profileId);
  try {
    // A medicine no longer new (docs/smart-nudges.md, `_a_week_on`'s own recipe): a steady
    // week, where recognition leads over presence's quiet-week fallback (priority 90 vs 80).
    const start = await backendClock(request);
    const weekOn = new Date(Date.parse(start.now) + 8 * 24 * 60 * 60 * 1000).toISOString();
    await setBackendClock(request, weekOn);
    await request.post(`${API}/profiles/${pa.profileId}/medicines/${lineId}/taken`, { ...auth(pa.token), data: { anchor: "breakfast" } });

    const today = (await (await request.get(`${API}/profiles/${pa.profileId}/nudges/plan`, auth(pa.token))).json()) as { drafts: { kind: string }[] };
    expect(today.drafts[0]?.kind).toBe("recognition");

    await fixClock(page, new Date(weekOn));
    await signInThroughTheApp(page, pa.phone, "Pa");
    const nudge = page.getByTestId("nudge");
    await expect(nudge).toBeVisible();
    await expect(nudge.getByTestId("nudge-accept")).toHaveText("OK"); // recognition, not commitment's "It went well"
    await nudge.getByTestId("nudge-dismiss").click();
    await expect(page.getByTestId("nudge")).toHaveCount(0);

    // Tomorrow: recognition would lead again on the numbers alone (another day taken), but
    // today's "Not today" moved it down (`DISMISSAL_STEP`, `app/delivery/nudges/engine.py`) —
    // so presence leads instead, and the plan says recognition is held for it.
    const tomorrow = new Date(Date.parse(weekOn) + 24 * 60 * 60 * 1000).toISOString();
    await setBackendClock(request, tomorrow);
    await request.post(`${API}/profiles/${pa.profileId}/medicines/${lineId}/taken`, { ...auth(pa.token), data: { anchor: "breakfast" } });
    const plan = (await (await request.get(`${API}/profiles/${pa.profileId}/nudges/plan`, auth(pa.token))).json()) as {
      drafts: { kind: string }[];
      held: { kind: string; because: string }[];
    };
    expect(plan.drafts[0]?.kind).toBe("presence");
    expect(plan.held.find((h) => h.kind === "recognition")).toBeTruthy();

    // And it is presence the client shows him, not a repeat of what he sent away.
    await fixClock(page, new Date(tomorrow));
    await page.reload();
    await expect(page.getByTestId("nudge").getByTestId("nudge-lines")).toBeVisible();
    await expect(page.getByTestId("nudge").getByTestId("nudge-why")).toHaveText(
      (await (await request.get(`${API}/profiles/${pa.profileId}/nudges/plan`, auth(pa.token))).json() as { drafts: { why: string }[] }).drafts[0]!.why,
    );
  } finally {
    await setBackendClock(request, FROZEN_CLOCK);
  }
});

test("both densities show the day's nudge with nothing drawn over a line", async ({ page, request }) => {
  const pa = await bareOwner(request);
  await signInThroughTheApp(page, pa.phone, "Pa");
  const nudge = page.getByTestId("nudge");
  await expect(nudge).toBeVisible();
  expect(await nothingDrawnOverLines(nudge, { lines: "p", controls: "button", minTarget: 56 })).toEqual([]);

  await page.getByRole("button", { name: "Me", exact: true }).click();
  await page.getByTestId("density-caregiver").click();
  await expect(page.locator("html")).toHaveAttribute("data-density", "caregiver");
  // Me is a sheet over the screen (D1): shut it, and Today is the screen it was opened from.
  await page.getByTestId("sheet-close").click();
  await todayReady(page);
  await expect(nudge).toBeVisible();
  expect(await nothingDrawnOverLines(nudge, { lines: "p", controls: "button", minTarget: 48 })).toEqual([]);
});

test("the day's nudge passes axe with no serious or critical finding", async ({ page, request }) => {
  const pa = await bareOwner(request);
  await signInThroughTheApp(page, pa.phone, "Pa");
  await expect(page.getByTestId("nudge")).toBeVisible();
  const results = await new AxeBuilder({ page }).include('[data-testid="nudge"]').analyze();
  const serious = results.violations.filter((each) => each.impact === "serious" || each.impact === "critical");
  expect(serious.map((each) => `${each.id} (${each.impact}): ${each.nodes.map((node) => node.target.join(" ")).join(" | ")}`)).toEqual([]);
});

test("a nudge with no why does not render", async ({ page, request }) => {
  // The engine always carries a why (`app/delivery/nudges/strings.py`); this is the client's
  // own defence, exercised by routing the plan read through a stub that drops it. A bare
  // profile is used so a nudge would otherwise show (presence's quiet-week line) — proving
  // the guard actually suppresses something, not asserting an absence that was there anyway.
  const pa = await bareOwner(request);
  await page.route("**/api/profiles/*/nudges/plan", async (route) => {
    const original = await route.fetch();
    const body = (await original.json()) as { drafts: { why: string }[] };
    for (const draft of body.drafts) draft.why = "";
    await route.fulfill({ response: original, json: body });
  });
  await signInThroughTheApp(page, pa.phone, "Pa");
  await todayReady(page);
  await expect(page.getByTestId("nudge")).toHaveCount(0);
});
