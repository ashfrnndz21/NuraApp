import { signal } from "@preact/signals";
import { Refused } from "./api/client";
import * as nura from "./api/nura";
import { resolveOpen, takeOpen } from "./push/open";
import type { ClaimableOut, DoorsOut, FeedItemOut, FeelingOut, ProfileOut } from "./api/types";
import { forgetFeed } from "./feed/session";
import type { RecordAt } from "./record/places";
import { clearAllProfileData, clearProfileData } from "./offline/todayCache";
import { voice } from "./player/voice";
import { language } from "./strings";
import { chooseProfile, me, profile, setToken, token } from "./store/session";

/** Which one thing is on the screen. There is no URL routing: the app is one page, opened
 *  from the home screen on the Now card, and every screen is one step from here. */
export type Screen =
  | { name: "loading" }
  | { name: "signin" }
  | { name: "code"; phone: string }
  | { name: "email" }
  | { name: "emailToken"; email: string }
  /** `refusal`: why the remembered papers are not open any more, said on the doors. */
  | { name: "doors"; doors: DoorsOut; refusal?: string }
  | { name: "consent" }
  | { name: "claim"; offer: ClaimableOut }
  | { name: "forSomeone" }
  | { name: "today"; saved?: boolean }
  | { name: "card"; item: FeedItemOut }
  /** The vertical feed (E21): one card a screen, from Today's "See more for you". */
  | { name: "feed" }
  /** Ask about one card: E03's recall (`POST /profiles/{id}/ask`), shown as the backend wrote it. */
  | { name: "ask"; item: FeedItemOut }
  | { name: "reading" }
  /** The visit day (E05-03, E05-04): the logistics card and the one button that records. */
  | { name: "visit"; appointmentId: string }
  | { name: "me" }
  /** The Record (W5): his medicines, papers, day, visits, blood tests, doctors, what changed
   *  and the family's papers; `at` is the one screen under it. */
  | { name: "record"; at?: RecordAt }
  | { name: "onboarding" }
  /** His emergency card, one tap from Today, readable with no network (E00-08, E13-01). */
  | { name: "emergency" }
  /** Papers from his photos: many picked at once, one yes, one review card each (E18-01). */
  | { name: "papers" }
  /** The patient's day (W7): the button, what to do now, a tapped word's one question, the
   *  symptom log, the whole pre-visit brief, the questions for the visit. */
  | { name: "notWell" }
  | { name: "whatToDo"; lines: string[]; offline: "network" | "server" | null; refusal: string | null }
  | { name: "feeling"; tap: FeelingOut }
  | { name: "symptoms" }
  | { name: "brief"; appointmentId: string }
  | { name: "questions"; appointmentId: string }
  /** Family (E12, E00-02, E00-07, E17-05, E18-02): his circle and his trail first, then the
   *  parts the backend lets each person reach. */
  | { name: "family"; part?: FamilyPart };

/** One part of Family at a time. */
export type FamilyPart =
  | "home"
  | "keys"
  | "trail"
  | "onlyMe"
  | "consents"
  | "record"
  | "thread"
  | "roster"
  | "messages"
  | "metrics"
  | "calendar"
  | "deliveries"
  | "settings"
  | "documents";

export type Tab = "today" | "record" | "family" | "me";

/** The tab bar's places: Today, the Record (*Papers*), Family, Me. */
export function openTab(tab: Tab): void {
  if (tab === "record") return go({ name: "record", at: { name: "hub" } });
  go(tab === "family" ? { name: "family", part: "home" } : { name: tab });
}

export const screen = signal<Screen>({ name: "loading" });

export function go(next: Screen): void {
  screen.value = next;
}

/** After a token is in hand: who am I, which doors apply, and where to land. */
export async function afterSignIn(): Promise<void> {
  const opening = takeOpen();
  const bearer = token.value;
  if (!bearer) return go({ name: "signin" });
  try {
    me.value = await nura.me(bearer);
  } catch (failure) {
    // His own account is closing (#151): the backend opens nothing of his papers now, him
    // included, and `me` reads through them — so it says no. The doors still answer and name
    // the closing, and below nothing of those papers stays on the phone.
    if (!(failure instanceof Refused && failure.refusal === "AccountClosing")) throw failure;
  }
  const doors = await nura.doors(bearer, language.value);
  const remembered = profile.value;
  const known = [doors.own, ...doors.invited, ...doors.stewarding].filter((each): each is ProfileOut => each !== null);
  const still = remembered && known.find((each) => each.profile_id === remembered.profile_id);
  if (still) {
    await chooseProfile(still);
    return landOn(opening);
  }
  const closing = doors.closing ?? [];
  if (remembered && !still) {
    // The key to the remembered papers was closed since, or their owner is closing his
    // account (#143): nothing of them stays on the phone, and he is told why he is back at
    // the doors.
    await clearProfileData(remembered.profile_id);
    forgetFeed();
    await chooseProfile(null);
    const why = closing.includes(remembered.profile_id) ? "AccountClosing" : "NoKey";
    return go({ name: "doors", doors, refusal: why });
  }
  if (doors.own && known.length === 1 && doors.claimable.length === 0) {
    await chooseProfile(doors.own);
    return landOn(opening);
  }
  if (known.length === 0 && closing.length > 0) return go({ name: "doors", doors, refusal: "AccountClosing" });
  go({ name: "doors", doors });
}

/** Where a restored session lands: the card a push opened (`?open=`, #143), else Today. */
async function landOn(opening: string | null): Promise<void> {
  const bearer = token.value;
  const chosen = profile.value;
  if (opening && bearer && chosen) {
    const opened = await resolveOpen(opening, {
      feedItem: (id) => nura.feedItem(bearer, chosen.profile_id, id),
      dayNudges: () => nura.dayNudges(bearer, chosen.profile_id),
    });
    if (opened.kind === "card") return go({ name: "card", item: opened.item });
  }
  go({ name: "today" });
}

/** Open one profile's papers. Whatever the phone kept of another profile's page is dropped:
 *  a page read under one key is never shown under another. */
export async function openProfile(chosen: ProfileOut): Promise<void> {
  const before = profile.value;
  if (before && before.profile_id !== chosen.profile_id) {
    await clearProfileData(before.profile_id);
    forgetFeed();
    voice.forget();
  }
  await chooseProfile(chosen);
  go({ name: "today" });
}

export async function signOutEverywhere(): Promise<void> {
  const bearer = token.value;
  if (bearer) {
    try {
      await nura.signOut(bearer);
    } catch {
      /* the token is forgotten here whatever the server said */
    }
  }
  // Nothing of anyone's papers stays on the phone after sign-out: the token, the chosen
  // profile and every cached Today page go.
  await clearAllProfileData();
  forgetFeed();
  voice.forget();
  // Whose papers were open is forgotten before the token: a sign-out cut short (the app closed
  // half-way) never leaves the next person to sign in on this phone on the last one's papers.
  await chooseProfile(null);
  await setToken(null);
  me.value = null;
  go({ name: "signin" });
}

export async function reloadDoors(): Promise<void> {
  const bearer = token.value;
  if (!bearer) return go({ name: "signin" });
  go({ name: "doors", doors: await nura.doors(bearer, language.value) });
}
