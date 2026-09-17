import { signal } from "@preact/signals";
import { en } from "./en";
import { ms } from "./ms";
import { zh } from "./zh";
import { LANGUAGES, RELATIONSHIPS, type Language, type Relationship, type Strings } from "./types";

export { LANGUAGES, RELATIONSHIPS, type Language, type Relationship, type Strings };

const CATALOGUE: Record<Language, Strings> = { en, ms, zh };

/** The language every string is read in. Persisted per device by the session store. */
export const language = signal<Language>("en");

export function isLanguage(code: string | null | undefined): code is Language {
  return (LANGUAGES as readonly string[]).includes(code ?? "");
}

/** The language the phone speaks, if Nura speaks it too; else English. */
export function deviceLanguage(tags: readonly string[]): Language {
  for (const tag of tags) {
    const code = tag.toLowerCase().slice(0, 2);
    if (isLanguage(code)) return code;
  }
  return "en";
}

/** The current catalogue. Call inside a component so it re-renders on a language change. */
/** Whose papers these are when they are not the reader's own: his name, set by the session from
 *  the papers' standing (store/session). On a key that is not his, the few lines of chrome that
 *  speak to him are said about him by name ("Pa is not feeling well"), as the backend says his
 *  cards about him (app/channels/about_him.py) — whole catalogue lines, never composed here. */
export const aboutWhom = signal<string | null>(null);

/** The chrome that speaks to him, by section, each key with its "…Other" twin in the catalogue. */
const ABOUT_HIM = {
  today: ["stateStable", "stateWatch", "callFamily", "offlineSub", "asOf", "cannotReach", "emergencySoon", "todayList", "fromToday", "tookMorning", "allTaken", "readingTitle", "emergencyOpen"],
  day: ["notWell", "symptomsOpen", "notWellTitle", "wordsLabel", "symptomsLead", "briefOpen", "questionsOpen"],
  places: ["visitsOwn"],
  hub: ["howFeeling", "checkLine", "doTitle"],
  record: ["medicines", "papers", "routine", "timeline", "trends", "providers", "back", "papersNone", "storyAsk", "twice", "outcomeNew", "outcomeRefill", "flaggedNone", "added", "noteSaved", "sureYes", "notSet", "setDay", "dayAsk"],
  reading: ["title"],
  visit: ["open"],
} as const satisfies Partial<Record<keyof Strings, readonly string[]>>;

/** The same, for the chrome kept as a map of lines rather than one line a key: his blood tests
 *  are named one per code ("Your cholesterol"), and each name has its twin in `…Other`. */
const ABOUT_HIM_MAPS = {
  record: ["analytes", "anchors"],
} as const satisfies Partial<Record<keyof Strings, readonly string[]>>;
const theirs = new Map<string, Strings>();

/** The catalogue with his chrome said about him by name: `{patient}` is his name. */
export function aboutHim(s: Strings, name: string): Strings {
  const said = (template: string) => template.split("{patient}").join(name);
  const out = { ...s } as Record<string, unknown>;
  for (const [section, keys] of Object.entries(ABOUT_HIM)) {
    const own = s[section as keyof Strings] as unknown as Record<string, string>;
    const copy: Record<string, unknown> = { ...(out[section] as Record<string, unknown> | undefined) ?? own };
    for (const key of keys) copy[key] = said(own[`${key}Other`] ?? own[key] ?? "");
    out[section] = copy;
  }
  for (const [section, keys] of Object.entries(ABOUT_HIM_MAPS)) {
    const own = s[section as keyof Strings] as unknown as Record<string, Record<string, string>>;
    const copy: Record<string, unknown> = { ...(out[section] as Record<string, unknown> | undefined) ?? own };
    for (const key of keys) {
      const mine = own[key] ?? {};
      const twin = own[`${key}Other`] ?? {};
      const named: Record<string, string> = {};
      for (const code of Object.keys(mine)) named[code] = said(twin[code] ?? mine[code] ?? "");
      copy[key] = named;
    }
    out[section] = copy;
  }
  return out as unknown as Strings;
}

export function t(): Strings {
  const s = CATALOGUE[language.value];
  const name = aboutWhom.value;
  if (!name) return s;
  const key = `${language.value}:${name}`;
  let found = theirs.get(key);
  if (!found) {
    found = aboutHim(s, name);
    theirs.set(key, found);
  }
  return found;
}

export function stringsFor(code: Language): Strings {
  return CATALOGUE[code];
}

/** Fill `{slots}` in one whole line. Lines are never assembled from pieces; only the name,
 *  the date and the number go into the slots the line already has. */
export function fill(template: string, slots: Record<string, string | number>): string {
  return template.replace(/\{(\w+)\}/g, (whole, key: string) => {
    const value = slots[key];
    return value === undefined ? whole : String(value);
  });
}

/** The plain lines for a refusal, by its class name — one, or two when the second says what
 *  to do next; never the name, never an id. */
export function refusalLines(refusal: string | undefined, code: Language = language.value): string[] {
  const map = CATALOGUE[code].refusals;
  const found = (refusal && map[refusal]) || map.default;
  return typeof found === "string" ? [found] : [...found];
}

/** The same, as one string: the lines one after the other. */
export function refusalSentence(refusal: string | undefined, code: Language = language.value): string {
  return refusalLines(refusal, code).join(" ");
}

/** BCP 47 tags for speech and dates, per language, for the two countries Nura serves. */
export const LOCALE: Record<Language, string> = { en: "en-SG", ms: "ms-MY", zh: "zh-CN" };
