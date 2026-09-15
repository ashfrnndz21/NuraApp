import { signal } from "@preact/signals";
import type { Tab } from "./nav";
import * as nura from "./api/nura";
import type { ClaimableOut, DoorsOut, FeedItemOut, FeelingOut, ProfileOut } from "./api/types";
import { forgetFeed } from "./feed/session";
import { clearAllProfileData, clearProfileData } from "./offline/todayCache";
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
  /** The vertical feed (E21): one card a screen, from Today's "See more for you". */
  | { name: "feed" }
  /** Ask (E03's recall, `POST /profiles/{id}/ask`), shown as the backend wrote it: about one
   *  card, or the question typed into the ask bar on top of Today and Home. */
  | { name: "ask"; item?: FeedItemOut; question?: string }
  | { name: "reading" }
  /** The visit day (E05-03, E05-04): the logistics card and the one button that records. */
  | { name: "visit"; appointmentId: string }
  /** The tabs that are not Today (D1): his medicines, his papers, his visits; her timeline and plan. */
  | { name: "medicines" }
  | { name: "records" }
  | { name: "visits" }
  | { name: "timeline" }
  | { name: "plan" }
  | { name: "onboarding" }
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

export type { Tab };

/** Each tab's first screen (nav.ts has which tabs each persona has). */
export function openTab(tab: Tab): void {
  go(tab === "family" ? { name: "family", part: "home" } : { name: tab });
}

export const screen = signal<Screen>({ name: "loading" });

/** Me (D1): a sheet over whatever screen is open, from the header's avatar — never a tab. */
export const meOpen = signal(false);

export function openMe(): void {
  meOpen.value = true;
}

export function closeMe(): void {
  meOpen.value = false;
}

/** A new screen closes the Me sheet: whatever was tapped in it has somewhere to go. */
export function go(next: Screen): void {
  meOpen.value = false;
  screen.value = next;
}

/** After a token is in hand: who am I, which doors apply, and where to land. */
export async function afterSignIn(): Promise<void> {
  const bearer = token.value;
  if (!bearer) return go({ name: "signin" });
  me.value = await nura.me(bearer);
  const doors = await nura.doors(bearer, language.value);
  const remembered = profile.value;
  const known = [doors.own, ...doors.invited, ...doors.stewarding].filter((each): each is ProfileOut => each !== null);
  const still = remembered && known.find((each) => each.profile_id === remembered.profile_id);
  if (still) {
    await chooseProfile(still);
    return go({ name: "today" });
  }
  if (remembered && !still) {
    // The key to the remembered papers was closed since: nothing of them stays on the phone,
    // and he is told why he is back at the doors.
    await clearProfileData(remembered.profile_id);
    forgetFeed();
    await chooseProfile(null);
    return go({ name: "doors", doors, refusal: "NoKey" });
  }
  if (doors.own && known.length === 1 && doors.claimable.length === 0) {
    await chooseProfile(doors.own);
    return go({ name: "today" });
  }
  go({ name: "doors", doors });
}

/** Open one profile's papers. Whatever the phone kept of another profile's page is dropped:
 *  a page read under one key is never shown under another. */
export async function openProfile(chosen: ProfileOut): Promise<void> {
  const before = profile.value;
  if (before && before.profile_id !== chosen.profile_id) {
    await clearProfileData(before.profile_id);
    forgetFeed();
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
  await setToken(null);
  await chooseProfile(null);
  me.value = null;
  go({ name: "signin" });
}

export async function reloadDoors(): Promise<void> {
  const bearer = token.value;
  if (!bearer) return go({ name: "signin" });
  go({ name: "doors", doors: await nura.doors(bearer, language.value) });
}
