import { signal } from "@preact/signals";
import * as nura from "../api/nura";
import { kvGet, kvSet } from "./kv";

/** Whether this deployment is a demo (ADR 0008: the fixtures, test numbers only, wiped each
 *  night). Asked of the backend once at start (`GET /api/deployment`) and remembered, so the
 *  banner is there on every screen even when the home-screen app opens offline. */
export const demo = signal(false);

/** Whether this deployment is a declared dev run (`NURA_DEV_CODE_SENDER=1`). Not remembered
 *  across a start the way `demo` is: a dev run is a laptop, always reachable when it matters,
 *  and a phone should not go on showing dev-only doors once it is talking to somewhere else. */
export const dev = signal(false);

/** The Web Push key the home-screen app subscribes with, when this deployment has Web Push
 *  (ADR 0001); null otherwise, and then Me offers no reminders. Not remembered: it is asked
 *  each start, and a phone offline cannot subscribe anyway. */
export const pushKey = signal<string | null>(null);

/** A `device.` key, like the language and the density: what this phone remembers about the
 *  server it talks to, never anything about the person (the onboarding spec holds the phone
 *  to that list of prefixes). */
const KEY = "device.demo";

export async function learnDeployment(): Promise<void> {
  try {
    if ((await kvGet<boolean>(KEY)) === true) demo.value = true;
  } catch {
    // Nothing remembered: the backend's answer below decides.
  }
  try {
    const answer = await nura.deployment();
    demo.value = answer.demo;
    dev.value = answer.dev ?? false;
    pushKey.value = answer.push_key ?? null;
    await kvSet(KEY, answer.demo);
  } catch {
    // Offline or the server away: keep what was remembered.
  }
}
