import type { ProfileOut, SettingsIn, SettingsOut } from "../api/types";
import type { Density } from "../store/session";
import { isLanguage, type Language } from "../strings";

/** About you (E01-03, #117's settings): the questions, in order, and what his answers change on
 *  the phone. Pure, so it is unit-tested (`tests/unit/about.test.ts`). One question per switch
 *  the settings hold, as #117's contract asks ("one per switch the screen shows"). */

export const SWITCHES = ["large_text", "high_contrast", "voice_on", "big_targets", "one_thing_per_screen", "read_back", "repeat_prompts"] as const;
export type SwitchItem = (typeof SWITCHES)[number];

export const ABOUT_ITEMS = ["name", "language", "born", "doctor", "breakfast", ...SWITCHES, "density"] as const;
export type AboutItem = (typeof ABOUT_ITEMS)[number];

export function isSwitch(item: AboutItem): item is SwitchItem {
  return (SWITCHES as readonly string[]).includes(item);
}

/** Birth-year decades he picks from: a decade, never a date of birth. */
export const DECADES = [1930, 1940, 1950, 1960, 1970, 1980, 1990] as const;

/** Breakfast times he picks from, as the settings store them ("07:30"). */
export const BREAKFAST_TIMES = ["06:00", "06:30", "07:00", "07:30", "08:00", "08:30", "09:00", "10:00"] as const;
export type BreakfastTime = (typeof BREAKFAST_TIMES)[number];

export function isBreakfastTime(value: string | null): value is BreakfastTime {
  return (BREAKFAST_TIMES as readonly string[]).includes(value ?? "");
}

/** Where the answers start: what the backend already holds, else the profile's own name and
 *  language, else the backend's defaults (nothing tapped, detailed, every help off). */
export function startingSettings(saved: SettingsOut | null, profile: ProfileOut | null, fallback: Language): SettingsIn {
  return {
    language: saved?.language ?? profile?.language ?? fallback,
    conditions: saved?.conditions ?? [],
    density: saved?.density ?? "detailed",
    large_text: saved?.large_text ?? false,
    high_contrast: saved?.high_contrast ?? false,
    voice_on: saved?.voice_on ?? false,
    big_targets: saved?.big_targets ?? false,
    one_thing_per_screen: saved?.one_thing_per_screen ?? false,
    read_back: saved?.read_back ?? false,
    repeat_prompts: saved?.repeat_prompts ?? false,
    preferred_name: saved?.preferred_name ?? profile?.display_name ?? null,
    doctor_name: saved?.doctor_name ?? null,
    breakfast_time: saved?.breakfast_time ?? null,
    birth_decade: saved?.birth_decade ?? null,
  };
}

/** Clean what was typed before it is sent: trimmed, and empty means "not given". */
export function tidy(settings: SettingsIn): SettingsIn {
  const text = (value: string | null) => {
    const trimmed = (value ?? "").trim();
    return trimmed.length ? trimmed : null;
  };
  return { ...settings, preferred_name: text(settings.preferred_name), doctor_name: text(settings.doctor_name) };
}

export interface DeviceEffects {
  language: Language | null;
  density: Density | null;
}

/** What the answers change on this phone, at once — only when the papers are his own (a
 *  daughter setting up for her father keeps her own phone as it is). His language becomes the
 *  phone's; bigger writing, bigger buttons, one thing at a time or the simple density bring the
 *  big-and-simple look. Nothing here ever makes the screen smaller. */
export function deviceEffects(settings: SettingsIn, standing: ProfileOut["standing"] | undefined): DeviceEffects {
  if (standing !== "owner") return { language: null, density: null };
  const simpler = settings.large_text || settings.big_targets || settings.one_thing_per_screen || settings.density === "simple";
  return { language: isLanguage(settings.language) ? settings.language : null, density: simpler ? "patient" : null };
}
