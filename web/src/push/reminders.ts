/** "Get reminders on this phone" (Web Push, ADR 0001). The phone is asked for permission here
 *  and nowhere else: in `turnOn`, which only a tap on that button calls — never on load. On a
 *  yes the browser subscribes with the deployment's push key (`GET /deployment`) and the
 *  subscription goes to the backend for this profile; the pushes that follow say only "Nura
 *  has something for you." The browser's push APIs come in through `PushEnv`, so the tests can
 *  stand in for them. */

import * as nura from "../api/nura";

export type RemindersState = "unsupported" | "off" | "on" | "denied";

export interface PushEnv {
  permission(): NotificationPermission;
  requestPermission(): Promise<NotificationPermission>;
  registration(): Promise<ServiceWorkerRegistration | null>;
}

export interface Backend {
  subscribe(subscription: PushSubscriptionJSON): Promise<unknown>;
  forget(endpoint: string): Promise<unknown>;
}

/** This browser's push APIs, or null where there are none (iOS Safari before the app is on the
 *  Home Screen, an old browser). */
export function browserEnv(): PushEnv | null {
  if (typeof window === "undefined" || typeof navigator === "undefined") return null;
  if (!("serviceWorker" in navigator) || !("PushManager" in window) || !("Notification" in window)) return null;
  return {
    permission: () => Notification.permission,
    requestPermission: () => Notification.requestPermission(),
    registration: async () => (await navigator.serviceWorker.getRegistration()) ?? null,
  };
}

/** The push key as the bytes `pushManager.subscribe` wants. */
export function keyBytes(key: string): ArrayBuffer {
  const base64 = key.replace(/-/g, "+").replace(/_/g, "/").padEnd(Math.ceil(key.length / 4) * 4, "=");
  const text = atob(base64);
  const bytes = new Uint8Array(new ArrayBuffer(text.length));
  for (let i = 0; i < text.length; i++) bytes[i] = text.charCodeAt(i);
  return bytes.buffer;
}

/** Whether this phone gets reminders now. Reads; never asks. */
export async function remindersState(env: PushEnv | null): Promise<RemindersState> {
  if (!env) return "unsupported";
  if (env.permission() === "denied") return "denied";
  const registration = await env.registration();
  if (!registration) return "unsupported";
  return (await registration.pushManager.getSubscription()) ? "on" : "off";
}

/** After his tap: ask the phone, subscribe, and tell the backend. */
export async function turnOn(env: PushEnv | null, key: string, backend: Backend): Promise<RemindersState> {
  if (!env) return "unsupported";
  const registration = await env.registration();
  if (!registration) return "unsupported";
  const answer = await env.requestPermission();
  if (answer !== "granted") return answer === "denied" ? "denied" : "off";
  const subscription = await registration.pushManager.subscribe({ userVisibleOnly: true, applicationServerKey: keyBytes(key) });
  await backend.subscribe(subscription.toJSON());
  return "on";
}

/** Stop reminders on this phone: the backend forgets it, and so does the browser. */
export async function turnOff(env: PushEnv | null, backend: Backend): Promise<RemindersState> {
  if (!env) return "unsupported";
  const registration = await env.registration();
  const subscription = registration ? await registration.pushManager.getSubscription() : null;
  if (subscription) {
    await backend.forget(subscription.endpoint);
    await subscription.unsubscribe();
  }
  return "off";
}

export function backendFor(token: string, profileId: string): Backend {
  return {
    subscribe: (subscription) => nura.subscribePush(token, profileId, subscription),
    forget: (endpoint) => nura.forgetPush(token, profileId, endpoint),
  };
}
