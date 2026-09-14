import { expect, test } from "@playwright/test";
import { BASE_URL } from "../../playwright.config";
import { API, apiToken, freshPhone, seedMedicine, signInThroughTheApp } from "./helpers";

/** With the network gone, the app opens on today's medicines from the phone: the service
 *  worker serves the shell, IndexedDB holds the last Today page, and there is no spinner. */
test("Today opens offline with today's medicines", async ({ page, context, request }) => {
  test.skip(!BASE_URL.startsWith("http://127.0.0.1:8000"), "needs the built app the backend serves (the worker is not built in dev)");
  const phone = freshPhone();
  const token = await apiToken(request, phone);
  const words = (await (await request.get(`${API}/consent/wording?language=en`)).json()) as { version: string };
  const opened = await request.post(`${API}/profiles/mine`, {
    headers: { Authorization: `Bearer ${token}` },
    data: { consent: { wording_version: words.version, language: "en", captured_via: "app" }, display_name: "Pa", language: "en" },
  });
  const profileId = ((await opened.json()) as { profile_id: string }).profile_id;
  await seedMedicine(request, token, profileId, { generic: "amlodipine", strength: "5 mg", dose_text: "1 tab OM", quantity: 30 });

  await signInThroughTheApp(page, phone, "Pa");
  await expect(page.getByTestId("now-card")).toContainText("Your blood pressure tablet");
  // Let the worker finish installing and the page be controlled by it.
  await page.evaluate(async () => {
    const registration = await navigator.serviceWorker.ready;
    if (!navigator.serviceWorker.controller) {
      await new Promise<void>((done) => navigator.serviceWorker.addEventListener("controllerchange", () => done(), { once: true }));
    }
    return registration.active?.state;
  });

  await context.setOffline(true);
  await page.reload();
  const now = page.getByTestId("now-card");
  await expect(now).toContainText("Take 1 tablet of your blood pressure tablet with breakfast.");
  await expect(page.getByTestId("offline")).toContainText("You are not connected right now.");
  await expect(page.getByTestId("proud-number")).toBeVisible();
  expect(await page.locator("[role=progressbar], .spinner").count()).toBe(0);
  await context.setOffline(false);
});
