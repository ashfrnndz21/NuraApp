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

const KEYS = {
  token: "session.token",
  profile: "session.profile",
  language: "device.language",
  density: "device.density",
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
  html.dataset.posture = posture.value;
  html.lang = language.value;
});

export async function restoreSession(): Promise<void> {
  const [savedToken, savedProfile, savedLanguage, savedDensity] = await Promise.all([
    kvGet<string>(KEYS.token),
    kvGet<ProfileOut>(KEYS.profile),
    kvGet<string>(KEYS.language),
    kvGet<Density>(KEYS.density),
  ]);
  language.value = isLanguage(savedLanguage)
    ? savedLanguage
    : deviceLanguage(typeof navigator === "undefined" ? [] : navigator.languages ?? [navigator.language]);
  densityChosen.value = savedDensity ?? null;
  token.value = savedToken ?? null;
  profile.value = savedProfile ?? null;
  restored.value = true;
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

export async function setDensity(value: Density | null): Promise<void> {
  await (value ? kvSet(KEYS.density, value) : kvDel(KEYS.density));
  densityChosen.value = value;
}

/** Forget who was signed in and whose papers were open; keep the device's language and look. */
export async function clearSession(): Promise<void> {
  me.value = null;
  await Promise.all([setToken(null), chooseProfile(null)]);
}

/** Whose papers these are, when not the reader's own: the chrome that speaks to him is said about
 *  him by name on every screen of hers (strings `aboutWhom`). */
effect(() => {
  const papers = profile.value;
  aboutWhom.value = papers && papers.standing !== "owner" ? papers.display_name || null : null;
});
