import { expect, test } from "@playwright/test";
import { FROZEN_CLOCK } from "../../playwright.config";
import { API, backendClock, fixClock, seedFeed, seedVisit, signInThroughTheApp, todayReady } from "./helpers";

/** The Services tab (D1, the concept board's Services screen), against `make dev` serving the
 *  build, the clock frozen at 10:00 in Singapore on Monday 14 September: reached from the tab
 *  bar like every other tab, showing Care services (the feed's local alerts and the providers
 *  his own record names), Near you (his coarse area, never guessed) and Guides (the same
 *  learning and clip cards Home's learning section would show him) — nothing invented, every
 *  card its own why line, and a clip's poster is what opens the player. */

const auth = (token: string) => ({ headers: { Authorization: `Bearer ${token}` } });

test.beforeAll(async ({ request }) => {
  const backend = await backendClock(request);
  if (!backend.frozen || Date.parse(backend.now) !== Date.parse(FROZEN_CLOCK)) {
    throw new Error(`the backend's clock is not frozen at ${FROZEN_CLOCK} (it says ${JSON.stringify(backend)})`);
  }
});

test.beforeEach(async ({ page }) => {
  await fixClock(page);
});

test("the Services tab, reached from the nav: his care services, his area and his guides — nothing invented, and a clip's poster opens the player", async ({ page, request }) => {
  const pa = await seedFeed(request);
  // Dr Tan, from the visit he has (E03-03): the "providers/clinics his own record names".
  await seedVisit(request, pa.token, pa.profileId);
  const area = await request.put(`${API}/profiles/${pa.profileId}/area`, { ...auth(pa.token), data: { area: "Toa Payoh" } });
  expect(area.ok(), await area.text()).toBe(true);

  await signInThroughTheApp(page, pa.phone, "Pa");
  await todayReady(page);

  // Reached from the nav, like every other tab (D1, one tab set).
  await page.getByTestId("tab-services").click();
  await expect(page.getByTestId("visits-screen")).toBeVisible();
  await expect(page.getByTestId("tab-services")).toHaveAttribute("aria-current", "page");

  // Care services: no local alert applies to him (nothing in his conditions or medicines
  // matches a hazard), so no local card sits here — but the doctor from his visit is the real
  // "care service" near him, with the way in to his own directory, so the section is not the
  // empty state.
  await expect(page.getByTestId("care-empty")).toHaveCount(0);
  await expect(page.getByTestId("care-provider").first()).toContainText("Dr Tan");
  await expect(page.getByTestId("care-providers-all")).toBeVisible();

  // Near you: the area he set, never guessed at.
  await expect(page.getByTestId("near-you")).toHaveText("Nura knows your area is Toa Payoh.");

  // Guides: the same learning explainer Home's learning section would show him, its own why
  // line under it.
  const guide = page.getByTestId("guide-card").first();
  await expect(guide).toBeVisible();
  await expect(guide.getByTestId("why")).not.toHaveText("");

  // A video card: its poster is the whole button, nothing plays until it is tapped, and
  // tapping it is what opens the player.
  const clip = page.getByTestId("guide-clip").first();
  await expect(clip).toBeVisible();
  await expect(clip.getByTestId("clip-player")).toHaveCount(0);
  await clip.getByTestId("guide-play").click();
  await expect(clip.getByTestId("clip-player")).toBeVisible();
});
