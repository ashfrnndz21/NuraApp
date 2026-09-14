import { signal } from "@preact/signals";
import * as nura from "./api/nura";
import type { ClaimableOut, DoorsOut, FeedItemOut, ProfileOut } from "./api/types";
import { forgetFeed } from "./feed/session";
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
  /** The vertical feed (E21): one card a screen, from Today's "See more for you". */
  | { name: "feed" }
  /** Ask about one card: E03's recall (`POST /profiles/{id}/ask`), shown as the backend wrote it. */
  | { name: "ask"; item: FeedItemOut }
  | { name: "reading" }
  /** The visit day (E05-03, E05-04): the logistics card and the one button that records. */
  | { name: "visit"; appointmentId: string }
  | { name: "me" }
  | { name: "onboarding" }
  /** His emergency card, one tap from Today, readable with no network (E00-08, E13-01). */
  | { name: "emergency" }
  /** Papers from his photos: many picked at once, one yes, one review card each (E18-01). */
  | { name: "papers" };

export const screen = signal<Screen>({ name: "loading" });

export function go(next: Screen): void {
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
