import { signal } from "@preact/signals";
import * as nura from "./api/nura";
import type { ClaimableOut, DoorsOut, ProfileOut } from "./api/types";
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
  | { name: "doors"; doors: DoorsOut }
  | { name: "consent" }
  | { name: "claim"; offer: ClaimableOut }
  | { name: "forSomeone" }
  | { name: "today"; saved?: boolean }
  | { name: "reading" }
  | { name: "me" };

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
  if (doors.own && known.length === 1 && doors.claimable.length === 0) {
    await chooseProfile(doors.own);
    return go({ name: "today" });
  }
  go({ name: "doors", doors });
}

export async function openProfile(chosen: ProfileOut): Promise<void> {
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
