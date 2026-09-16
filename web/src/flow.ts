import { signal } from "@preact/signals";
import type { Tab } from "./nav";
import { Refused } from "./api/client";
import * as nura from "./api/nura";
import { resolveOpen, takeOpen } from "./push/open";
import type { ClaimableOut, DoorsOut, FeedItemOut, FeelingOut, ProfileOut } from "./api/types";
import { forgetFeed } from "./feed/session";
import { forgetKnown } from "./store/profiles";
import type { RecordAt } from "./record/places";
import { clearAllProfileData, clearProfileData } from "./offline/todayCache";
import { todayPage } from "./today/page";
import { voice } from "./player/voice";
import { language } from "./strings";
import { chooseProfile, me, profile, setLargeText, setToken, token } from "./store/session";

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
  /** The emergency card, as the backend prints it: from the Me sheet, one tap. */
  | { name: "emergency" }
  /** The vertical feed (E21): one card a screen, from Today's "See more for you". */
  | { name: "feed" }
  /** Ask about one card, or ask or search from Today: E03's recall (`POST /profiles/{id}/ask`)
   *  and the ask bar's Web, Providers and Videos filters, shown as the backend wrote them.
   *  `question` is what was typed into the ask bar the shell puts on every screen (D1). */
  | { name: "ask"; item?: FeedItemOut; question?: string }
  | { name: "reading" }
  /** The visit day (E05-03, E05-04): the logistics card and the one button that records. */
  | { name: "visit"; appointmentId: string }
  /** The visits tab: his visits, and getting ready for the next one. */
  | { name: "visits" }
  /** The Record (W5): his medicines, papers, day, visits, blood tests, doctors, what changed
   *  and the family's papers; `at` is the one screen under it. Each persona's tabs open into
   *  it (nav.ts, `recordTab`). */
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

export type { Tab };

/** Each tab's first screen — one tab set for everyone (nav.ts). Medicines and Records are
 *  places in the Record (W5); Visits is his visits and getting ready for the next one. */
export function openTab(tab: Tab): void {
  switch (tab) {
    case "medicines":
      return go({ name: "record", at: { name: "medicines" } });
    case "records":
      return go({ name: "record", at: { name: "hub" } });
    case "family":
      return go({ name: "family", part: "home" });
    default:
      return go({ name: tab });
  }
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
    voice.forget();
    // His large-text setting came from his State: it goes with the rest.
    await setLargeText(false);
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

/** Nothing of anyone's papers stays on the phone: the token, the chosen profile, every cached
 *  Today page, what the player fetched, whose papers this person could open, and his large-text
 *  setting (read from his State). Whose papers were open is forgotten first, then the token — so
 *  a wipe cut short never leaves the next person on the last one's papers, and a page still
 *  being read is not kept (useToday checks the token) — and the cache goes after both.
 *
 *  Every way the app can land on sign-in runs this. A session that expired is the same leak as
 *  a sign-out, through a door people walk through far more often. */
export async function forgetEverything(): Promise<void> {
  voice.forget();
  await setLargeText(false);
  await chooseProfile(null);
  await setToken(null);
  me.value = null;
  todayPage.value = null;
  await clearAllProfileData();
  forgetFeed();
  forgetKnown();
}

/** Back to sign-in with nothing of the last person left behind. */
export async function signOutHere(): Promise<void> {
  await forgetEverything();
  go({ name: "signin" });
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
  await signOutHere();
}

export async function reloadDoors(): Promise<void> {
  const bearer = token.value;
  if (!bearer) return go({ name: "signin" });
  go({ name: "doors", doors: await nura.doors(bearer, language.value) });
}
