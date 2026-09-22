import { expect, test } from "@playwright/test";
import { API, fixClock, freshPhone, signInThroughTheApp } from "./helpers";

/** RFC 8291's example browser keys: a real P-256 point and a 16-byte secret, so the backend
 *  keeps the subscription; the push service behind them is a stand-in, never called. */
const P256DH = "BCVxsr7N_eNgVRqvHtD0zTZsEc6-VV-JvLexhqUzORcxaOzi6-AYWXvTBHm4bjyPjs7Vd8pZGH6SRpkNtoIAiw4";
const AUTH = "BTBZMqHH6r4Tts7J_aSIgg";
const ENDPOINT = "https://push.example.test/nura-e2e";

test.beforeEach(async ({ page }) => {
  await fixClock(page);
});

test("reminders on this phone: nothing asked on load; a tap asks once, subscribes and tells the backend; stop forgets it", async ({ page, request }) => {
  const deployment = (await (await request.get(`${API}/deployment`)).json()) as { push_key?: string | null };
  test.skip(!deployment.push_key, "this backend has no Web Push keys (a dev server started without them)");

  // The browser's own push service needs Google's servers; this stands in for it, and counts
  // every time the page asks the phone for permission.
  await page.addInitScript(
    ({ endpoint, p256dh, auth }) => {
      const w = window as unknown as { __asked: number };
      w.__asked = 0;
      let granted = false;
      let subscribed = false;
      Object.defineProperty(Notification, "permission", { get: () => (granted ? "granted" : "default"), configurable: true });
      Notification.requestPermission = async () => {
        w.__asked += 1;
        granted = true;
        return "granted";
      };
      const subscription = {
        endpoint,
        toJSON: () => ({ endpoint, keys: { p256dh, auth } }),
        unsubscribe: async () => {
          subscribed = false;
          return true;
        },
      };
      PushManager.prototype.subscribe = async function () {
        subscribed = true;
        return subscription as unknown as PushSubscription;
      };
      PushManager.prototype.getSubscription = async function () {
        return subscribed ? (subscription as unknown as PushSubscription) : null;
      };
    },
    { endpoint: ENDPOINT, p256dh: P256DH, auth: AUTH },
  );

  await signInThroughTheApp(page, freshPhone(), "Pa");
  await page.getByTestId("door-for-me").click();
  await page.getByTestId("who-continue").click();
  await page.getByTestId("agree").click();
  await page.getByTestId("set-up-later").click();
  await page.getByTestId("open-me").click();

  // Me offers reminders, and nothing has asked the phone yet: not on load, not on Me.
  await expect(page.getByTestId("reminders-get")).toHaveText("Get reminders on this phone");
  expect(await page.evaluate(() => (window as unknown as { __asked: number }).__asked)).toBe(0);

  const subscribed = page.waitForResponse((r) => r.request().method() === "POST" && r.url().endsWith("/push-subscriptions"));
  await page.getByTestId("reminders-get").click();
  expect((await subscribed).status()).toBe(201);
  expect(await page.evaluate(() => (window as unknown as { __asked: number }).__asked)).toBe(1);
  await expect(page.getByTestId("reminders-on")).toHaveText("Reminders are on for this phone.");

  const forgotten = page.waitForResponse((r) => r.request().method() === "DELETE" && r.url().endsWith("/push-subscriptions"));
  await page.getByTestId("reminders-stop").click();
  expect((await forgotten).status()).toBe(204);
  await expect(page.getByTestId("reminders-get")).toBeVisible();
  expect(await page.evaluate(() => (window as unknown as { __asked: number }).__asked)).toBe(1);
});
