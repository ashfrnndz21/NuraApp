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

/** The plain lines for a refusal, by its class name — one, or two when the second says what
 *  to do next; never the name, never an id. */
export function refusalLines(refusal: string | undefined, code: Language = language.value, slots?: { contact?: string }): string[] {
  const map = CATALOGUE[code].refusals;
  const found = (refusal && map[refusal]) || map.default;
  const lines = typeof found === "string" ? [found] : [...found];
  // A refusal that names where to write (`contact`, from the backend): its first line, then
  // the one that says where, filled with the backend's address.
  const writeTo = refusal && slots?.contact ? map[`${refusal}WriteTo`] : undefined;
  if (typeof writeTo === "string" && lines[0]) return [lines[0], fill(writeTo, { contact: slots!.contact! })];
  return lines;
}

/** The same, as one string: the lines one after the other. */
export function refusalSentence(refusal: string | undefined, code: Language = language.value): string {
  return refusalLines(refusal, code).join(" ");
}

/** BCP 47 tags for speech and dates, per language, for the two countries Nura serves. */
export const LOCALE: Record<Language, string> = { en: "en-SG", ms: "ms-MY", zh: "zh-CN" };
