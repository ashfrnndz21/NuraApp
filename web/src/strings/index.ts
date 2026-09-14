import { signal } from "@preact/signals";
import { en } from "./en";
import { ms } from "./ms";
import { zh } from "./zh";
import { LANGUAGES, type Language, type Strings } from "./types";

export { LANGUAGES, type Language, type Strings };

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
export function t(): Strings {
  return CATALOGUE[language.value];
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

/** The one plain sentence for a refusal, by its class name; never the name, never an id. */
export function refusalSentence(refusal: string | undefined, code: Language = language.value): string {
  const map = CATALOGUE[code].refusals;
  return (refusal && map[refusal]) || map.default;
}

/** BCP 47 tags for speech and dates, per language, for the two countries Nura serves. */
export const LOCALE: Record<Language, string> = { en: "en-SG", ms: "ms-MY", zh: "zh-CN" };
