import { signal } from "@preact/signals";
import * as nura from "../api/nura";
import { kvGet, kvSet } from "./kv";

/** Whether this deployment is a demo (ADR 0008: the fixtures, test numbers only, wiped each
 *  night). Asked of the backend once at start (`GET /api/deployment`) and remembered, so the
 *  banner is there on every screen even when the home-screen app opens offline. */
export const demo = signal(false);

const KEY = "deployment.demo";

export async function learnDeployment(): Promise<void> {
  try {
    if ((await kvGet<boolean>(KEY)) === true) demo.value = true;
  } catch {
    // Nothing remembered: the backend's answer below decides.
  }
  try {
    const answer = await nura.deployment();
    demo.value = answer.demo;
    await kvSet(KEY, answer.demo);
  } catch {
    // Offline or the server away: keep what was remembered.
  }
}
