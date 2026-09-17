import { effect, signal } from "@preact/signals";
import type { MeOut, Posture, ProfileOut } from "../api/types";
import { aboutWhom, deviceLanguage, isLanguage, language, type Language } from "../strings";
import { kvDel, kvGet, kvSet } from "./kv";

/** Who is signed in, whose papers are open, and how the app looks — as signals, persisted
 *  in IndexedDB so a home-screen app reopens where it was. */

export type Density = "patient" | "caregiver";

export const token = signal<string | null>(null);
export const me = signal<MeOut | null>(null);
export const profile = signal<ProfileOut | null>(null);
/** The person's own choice of density, if made; else it follows his standing. */
export const densityChosen = signal<Density | null>(null);
export const posture = signal<Posture>("stable");
export const restored = signal(false);
/** His large-text setting (E15-04), taken from his State on his own phone: one step bigger
 *  than his density, on top of whatever text size the phone itself is set to. */
export const largeText = signal(false);
/** His speed for the one player, as the phone keeps it: read with the rest of the session,
 *  before any screen shows, so the first tap after opening is already at his speed. The player
 *  takes it from here (`player/voice.ts`). */
export const savedSpeed = signal<number | null>(null);
export const SPEED_KEY = "device.speed";
/** Whether this phone has been past the welcome screen (docs/design-direction.md): the welcome
 *  is shown once a phone, before its first sign-in. It says nothing about anyone — no name, no
 *  papers — so signing out does not forget it, and the next person goes straight to sign-in. */
export const welcomed = signal(false);

const KEYS = {
  token: "session.token",
  profile: "session.profile",
  language: "device.language",
  density: "device.density",
  text: "device.text",
  speed: SPEED_KEY,
  welcomed: "device.welcomed",
} as const;

/** Patient density for the owner of the papers; caregiver density for anyone holding a key. */
export function densityFor(standing: ProfileOut["standing"] | undefined, chosen: Density | null): Density {
  if (chosen) return chosen;
  return standing === "owner" || standing === undefined ? "patient" : "caregiver";
}

export function density(): Density {
  return densityFor(profile.value?.standing, densityChosen.value);
}

function root(): HTMLElement | null {
  return typeof document === "undefined" ? null : document.documentElement;
}

// The densities and the wash are attributes on <html>; tokens.css does the rest.
effect(() => {
  const html = root();
  if (!html) return;
  html.dataset.density = densityFor(profile.value?.standing, densityChosen.value);
  // How big the phone's own writing is, against the 16px a browser starts from. A media query
  // cannot answer this — `em` and `rem` there are the browser's initial size, not the root's —
  // so the layout reads it here, and the chrome gives way rather than his lines.
  const rootSize = parseFloat(getComputedStyle(html).fontSize);
  if (Number.isFinite(rootSize) && rootSize >= 24) html.dataset.writing = "large";
  else delete html.dataset.writing;
  html.dataset.posture = posture.value;
  html.lang = language.value;
  if (largeText.value) html.dataset.text = "large";
  else delete html.dataset.text;
});

export async function restoreSession(): Promise<void> {
  const [savedToken, savedProfile, savedLanguage, savedDensity, savedText, savedRate, savedWelcomed] = await Promise.all([
    kvGet<string>(KEYS.token),
    kvGet<ProfileOut>(KEYS.profile),
    kvGet<string>(KEYS.language),
    kvGet<Density>(KEYS.density),
    kvGet<string>(KEYS.text),
    kvGet<number>(KEYS.speed),
    kvGet<boolean>(KEYS.welcomed),
  ]);
  welcomed.value = savedWelcomed === true;
  largeText.value = savedText === "large";
  savedSpeed.value = typeof savedRate === "number" ? savedRate : null;
  language.value = isLanguage(savedLanguage)
    ? savedLanguage
    : deviceLanguage(typeof navigator === "undefined" ? [] : navigator.languages ?? [navigator.language]);
  densityChosen.value = savedDensity ?? null;
  token.value = savedToken ?? null;
  profile.value = savedProfile ?? null;
  restored.value = true;
}

/** Past the welcome: kept on the phone first, then shown, like every device setting here. */
export async function setWelcomed(): Promise<void> {
  await kvSet(KEYS.welcomed, true);
  welcomed.value = true;
}

export async function setToken(value: string | null): Promise<void> {
  token.value = value;
  await (value ? kvSet(KEYS.token, value) : kvDel(KEYS.token));
}

export async function chooseProfile(value: ProfileOut | null): Promise<void> {
  profile.value = value;
  await (value ? kvSet(KEYS.profile, value) : kvDel(KEYS.profile));
}

/** Persist first, then show: what the screen says is what the device will remember. */
export async function setLanguage(code: Language): Promise<void> {
  await kvSet(KEYS.language, code);
  language.value = code;
}

/** His large-text setting, as his State says it: kept on the phone so it opens that way offline. */
export async function setLargeText(value: boolean): Promise<void> {
  if (largeText.peek() === value) return;
  await (value ? kvSet(KEYS.text, "large") : kvDel(KEYS.text));
  largeText.value = value;
}

export async function setDensity(value: Density | null): Promise<void> {
  await (value ? kvSet(KEYS.density, value) : kvDel(KEYS.density));
  densityChosen.value = value;
}

/** Whose papers these are, when not the reader's own: the chrome that speaks to him is said about
 *  him by name on every screen of hers (strings `aboutWhom`). */
effect(() => {
  const papers = profile.value;
  aboutWhom.value = papers && papers.standing !== "owner" ? papers.display_name || null : null;
});
