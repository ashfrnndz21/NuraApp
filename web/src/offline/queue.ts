import { Refused, Unreachable } from "../api/client";
import { kvDel, kvGet, kvSet } from "../store/kv";
import { midnightAfter, sameBinding, type Binding } from "./todayCache";

/** Taps made while the phone could not reach Nura (E00-08): held on the phone, then sent once
 *  each, in the order he made them, when the network is back.
 *
 *  A tap is what he did and when: *Taken* on a dose the backend had marked due (the Now card
 *  came from a live read), or a word on the feeling strip. Each keeps the moment he tapped, so
 *  the backend writes it at that moment, and the backend takes the same tap twice as once
 *  (`POST …/taken` with the same `taken_at`), so nothing is ever counted twice. The queue is
 *  kept under the same rules as the Today page: bound to the key and the scope set that made
 *  the taps, and good until the midnight after the first one on the region's clock — a tap from
 *  yesterday is never written as today's. A refusal, a switch of profile and sign-out delete it
 *  with every other page the phone keeps (`clearProfileData`, `clearAllProfileData`).
 *
 *  A red word is never held: it is the moment to call, not to wait for a network. */

export type Tap =
  | { id: string; kind: "taken"; lineId: string; anchor: string | null; at: string }
  | { id: string; kind: "feeling"; word: string; language: string; at: string };

export interface KeptTaps {
  taps: Tap[];
  binding: Binding;
  expiresAt: string;
}

export const QUEUE_PREFIX = "queue.";
const key = (profileId: string) => `${QUEUE_PREFIX}${profileId}`;

/** What one replay did: what went, what the backend said no to (in order), and whether the
 *  network went again before the end (the rest wait for the next time). */
export interface Replayed {
  sent: Tap[];
  refused: { tap: Tap; failure: Refused }[];
  stopped: boolean;
}

/** Hold one tap. A red feeling word is refused here (`null`): it is never held. So is a feeling
 *  tap with no moment of its own (#171) — every tap the queue holds, *taken* or *feeling*
 *  alike, must carry its own `at`, the way `Taken` already does, or a replay would have nothing
 *  truer to write it under than whatever day the network happens to come back on. */
export async function hold(
  profileId: string,
  tap: Tap,
  binding: Binding,
  now: Date,
  zone: string,
  red = false,
): Promise<Tap[] | null> {
  if (tap.kind === "feeling" && (red || !tap.at)) return null;
  const kept = await load(profileId, binding, now);
  const entry: KeptTaps = kept
    ? { ...kept, taps: [...kept.taps, tap] }
    : { taps: [tap], binding, expiresAt: midnightAfter(now, zone).toISOString() };
  await kvSet(key(profileId), entry);
  return entry.taps;
}

/** The taps still waiting, oldest first. Taps held under another key or scope set, or past
 *  their midnight, are deleted, not returned. */
export async function waiting(profileId: string, binding: Binding, now: Date): Promise<Tap[]> {
  return (await load(profileId, binding, now))?.taps ?? [];
}

async function load(profileId: string, binding: Binding, now: Date): Promise<KeptTaps | null> {
  const entry = await kvGet<KeptTaps>(key(profileId));
  if (!entry) return null;
  if (!entry.binding || !sameBinding(entry.binding, binding) || new Date(entry.expiresAt).getTime() <= now.getTime()) {
    await kvDel(key(profileId));
    return null;
  }
  return entry;
}

async function drop(profileId: string, id: string): Promise<void> {
  const entry = await kvGet<KeptTaps>(key(profileId));
  if (!entry) return;
  const taps = entry.taps.filter((tap) => tap.id !== id);
  if (taps.length === 0) await kvDel(key(profileId));
  else await kvSet(key(profileId), { ...entry, taps });
}

const running = new Map<string, Promise<Replayed>>();

/** Send every waiting tap once, oldest first, one at a time. A tap leaves the phone's list as
 *  soon as the backend has answered it — yes or no — so a reload never sends it again; a lost
 *  network, or a server that could not answer, stops the replay and keeps the rest. One replay
 *  at a time per profile: a second call while one runs gets the same answer. */
export function replay(profileId: string, binding: Binding, now: Date, send: (tap: Tap) => Promise<unknown>): Promise<Replayed> {
  const already = running.get(profileId);
  if (already) return already;
  const run = (async (): Promise<Replayed> => {
    const done: Replayed = { sent: [], refused: [], stopped: false };
    for (const tap of await waiting(profileId, binding, now)) {
      try {
        await send(tap);
        await drop(profileId, tap.id);
        done.sent.push(tap);
      } catch (failure) {
        if (failure instanceof Unreachable || (failure instanceof Refused && failure.status >= 500)) {
          done.stopped = true;
          break;
        }
        await drop(profileId, tap.id);
        if (failure instanceof Refused) done.refused.push({ tap, failure });
        else done.refused.push({ tap, failure: new Refused("HttpError", 0) });
      }
    }
    return done;
  })();
  running.set(profileId, run);
  return run.finally(() => running.delete(profileId));
}

/** A fresh id for a tap: random, so it names nothing. */
export function tapId(): string {
  if (typeof crypto !== "undefined" && "randomUUID" in crypto) return crypto.randomUUID();
  return `${Date.now().toString(36)}-${Math.random().toString(36).slice(2)}`;
}
