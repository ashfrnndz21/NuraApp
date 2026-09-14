import type { ProfileOut, SettingsIn, SettingsOut } from "../api/types";
import type { Density } from "../store/session";
import { isLanguage, type Language } from "../strings";

/** About you (E01-03): the questions, in order, and what his answers change on the phone.
 *  Pure, so it is unit-tested (`tests/unit/about.test.ts`). */

export const ABOUT_ITEMS = ["name", "language", "born", "doctor", "breakfast", "sight", "hearing", "hands", "memory"] as const;
export type AboutItem = (typeof ABOUT_ITEMS)[number];

/** The four yes/no tiles, by the settings field each one writes. */
export const FUNCTION_TILES = { sight: "sight", hearing: "hearing", hands: "hands", memory: "cognitive" } as const;
export type FunctionItem = keyof typeof FUNCTION_TILES;

export function isFunctionItem(item: AboutItem): item is FunctionItem {
  return item in FUNCTION_TILES;
}

/** Birth-year decades he picks from: a decade, never a date of birth. */
export const DECADES = [1930, 1940, 1950, 1960, 1970, 1980, 1990] as const;

/** Breakfast times he picks from, as the settings store them ("07:30"). Each has a whole
 *  line in the catalogue ("At half past 7"), never a clock string on the screen. */
export const BREAKFAST_TIMES = ["06:00", "06:30", "07:00", "07:30", "08:00", "08:30", "09:00", "10:00"] as const;
export type BreakfastTime = (typeof BREAKFAST_TIMES)[number];

export function isBreakfastTime(value: string | null): value is BreakfastTime {
  return (BREAKFAST_TIMES as readonly string[]).includes(value ?? "");
}

/** Where the answers start: what the backend already holds, else the profile's own name and
 *  language, else nothing — never a guess. */
export function startingSettings(saved: SettingsOut | null, profile: ProfileOut | null, fallback: Language): SettingsIn {
  return {
    preferred_name: saved?.preferred_name ?? profile?.display_name ?? null,
    language: saved?.language ?? profile?.language ?? fallback,
    birth_decade: saved?.birth_decade ?? null,
    doctor: saved?.doctor ?? null,
    breakfast_time: saved?.breakfast_time ?? null,
    sight: saved?.sight ?? false,
    hearing: saved?.hearing ?? false,
    hands: saved?.hands ?? false,
    cognitive: saved?.cognitive ?? false,
  };
}

/** Clean what was typed before it is sent: trimmed, and empty means "not given". */
export function tidy(settings: SettingsIn): SettingsIn {
  const text = (value: string | null) => {
    const trimmed = (value ?? "").trim();
    return trimmed.length ? trimmed : null;
  };
  return { ...settings, preferred_name: text(settings.preferred_name), doctor: text(settings.doctor) };
}

export interface DeviceEffects {
  language: Language | null;
  density: Density | null;
}

/** What the answers change on this phone, at once (E01-03: "settings drive density mode and
 *  voice language immediately"). Only when the papers are his own: a daughter setting up for
 *  her father keeps her own language and her own density on her own phone.
 *  - His language becomes the phone's, so every line and the spoken twin follow.
 *  - Small print, small buttons or memory: the big-and-simple look. A "no" to all three
 *    changes nothing — it never makes the screen smaller than it is. */
export function deviceEffects(settings: SettingsIn, standing: ProfileOut["standing"] | undefined): DeviceEffects {
  if (standing !== "owner") return { language: null, density: null };
  return {
    language: isLanguage(settings.language) ? settings.language : null,
    density: settings.sight || settings.hands || settings.cognitive ? "patient" : null,
  };
}
