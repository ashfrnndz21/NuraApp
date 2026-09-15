import type { FactOut, FeedItemOut, LineOut, NowOut, Posture, SlotOut, StateDriverOut } from "../api/types";
import { fill, type Strings } from "../strings";

/** The Today page, built only from what the backend already says in his words: today's dose
 *  cards with the backend's own `due_now` / `missed` and source line, the reconciled list with
 *  its counts and its questions for the doctor, the State with its id and staleness, the
 *  feed's cards for today, and the proud number the backend counted. No sentence is
 *  assembled here, and no dose is ranked or timed here: the Now card is the first dose the
 *  backend marks due. */

export interface TodayModel {
  stateId: string | null;
  posture: Posture;
  stale: boolean | null;
  computedAt: string | null;
  slots: SlotOut[];
  lines: LineOut[];
  feed: FeedItemOut[];
  proud: number | null;
  /** The chief's name, read by the owner when the State says act: whom to call. */
  chief: string | null;
  /** The State's own boundary lines (E16-01): what Nura did, not a doctor's advice, whom to ask. */
  boundary: string[];
  fetchedAt: string;
  /** D1: the hero's number and words (`…/medicines/now`); the State's word, line and drivers. */
  hero?: NowOut | null;
  word?: string | null;
  line?: string | null;
  drivers?: StateDriverOut[];
}

export type NowCard =
  | { kind: "due"; lineId: string; anchor: string; title: string; sentence: string; provenance: string }
  | { kind: "missed"; title: string; lines: string[]; provenance: string }
  | { kind: "allTaken" }
  | { kind: "nothingNow" }
  | { kind: "none" };

function titleCase(name: string): string {
  return name.length ? name[0]!.toUpperCase() + name.slice(1) : name;
}

/** His word for the medicine, never the chemical name alone. */
export function lineTitle(line: LineOut | undefined, s: Strings): string {
  return line?.name ? titleCase(line.name) : s.today.aTablet;
}

/** The one thing now: the first dose the backend marks due; else the first it marks missed,
 *  with the story's own lines and no Taken; else "all taken" or "nothing right now". */
export function nowCard(slots: readonly SlotOut[], lines: readonly LineOut[], s: Strings): NowCard {
  if (slots.length === 0) return { kind: "none" };
  const lineOf = (id: string) => lines.find((each) => each.line_id === id);
  const due = slots.find((slot) => slot.due_now && !slot.taken);
  if (due) {
    return {
      kind: "due",
      lineId: due.line_id,
      anchor: due.anchor,
      title: lineTitle(lineOf(due.line_id), s),
      sentence: due.card,
      provenance: due.source,
    };
  }
  const missed = slots.find((slot) => slot.missed && !slot.taken);
  if (missed) {
    return { kind: "missed", title: lineTitle(lineOf(missed.line_id), s), lines: missed.if_forgotten, provenance: missed.source };
  }
  return slots.every((slot) => slot.taken) ? { kind: "allTaken" } : { kind: "nothingNow" };
}

/** Today's dose cards as a list, for a page the phone kept: each the backend's own sentence
 *  with its moment of the day, and no "now" — a kept page cannot know what is due. */
export function todayList(slots: readonly SlotOut[]): string[] {
  return slots.map((slot) => slot.card);
}

export interface FeedCards {
  flags: FeedItemOut[];
  forYou: FeedItemOut[];
}

/** The feed's red flags (first, never capped) and its first two now and today cards, in the
 *  backend's order. Nothing is re-ranked here; a card he said "Not for me" to is not shown. */
export function feedCards(items: readonly FeedItemOut[]): FeedCards {
  const shown = items.filter((item) => item.status !== "dismissed");
  return {
    flags: shown.filter((item) => item.supply === "flag"),
    forYou: shown.filter((item) => item.supply === "now" || item.supply === "today").slice(0, 2),
  };
}

/** The feed card's source line: the backend's own "why am I seeing this". */
export function whyLine(item: FeedItemOut): string {
  return typeof item.why.plain === "string" ? item.why.plain : "";
}

/** The backend's boundary, as lines: one idea per line. */
export function boundaryOf(text: string | null | undefined): string[] {
  return (text ?? "").split("\n").map((line) => line.trim()).filter(Boolean);
}

/** A feed card's body and its boundary, the boundary taken from the card's own field: the
 *  body's closing lines are those same words, so they are shown once, as the boundary. */
export function feedLines(item: FeedItemOut): { lines: string[]; boundary: string[] } {
  const boundary = boundaryOf(item.boundary);
  const tail = item.body.slice(item.body.length - boundary.length);
  const endsOnIt = boundary.length > 0 && tail.length === boundary.length && tail.every((line, index) => line.trim() === boundary[index]);
  return { lines: endsOnIt ? item.body.slice(0, item.body.length - boundary.length) : [...item.body], boundary };
}

export function greeting(hour: number, name: string, s: Strings): string {
  const line = hour < 12 ? s.today.greetingMorning : hour < 18 ? s.today.greetingAfternoon : s.today.greetingEvening;
  return fill(line, { name });
}

/** What he did, in the past tense, for the moment of the day he did it. */
export function tookLine(hour: number, s: Strings): string {
  if (hour < 12) return s.today.tookMorning;
  if (hour < 17) return s.today.tookAfternoon;
  if (hour < 21) return s.today.tookEvening;
  return s.today.tookNight;
}

export function readingLead(hour: number, s: Strings): string {
  return hour < 12 ? s.today.readingLead : s.today.readingLeadEvening;
}

/** The State card's own lines; its boundary is the backend's (`TodayModel.boundary`), shown
 *  under them. `act` never gets a calm sentence: it says what to do — the flag card above it
 *  when the feed has one, else whom to call — even from an earlier State. A stale State, or
 *  one the phone kept, says only that it is from earlier today. */
export function stateLines(
  model: Pick<TodayModel, "posture" | "stale" | "chief">,
  s: Strings,
  where: { flagAbove: boolean; kept: boolean },
): string[] {
  const earlier = model.stale === true || where.kept;
  if (model.posture === "act") {
    const act = where.flagAbove
      ? [s.today.stateAct, s.today.stateActSub]
      : [s.today.stateAct, model.chief ? fill(s.today.callChief, { name: model.chief }) : s.today.callFamily];
    return earlier ? [...act, s.today.staleState] : act;
  }
  if (earlier) return [s.today.staleState];
  if (model.posture === "watch") return [s.today.stateWatch, s.today.stateWatchSub];
  return [s.today.stateStable];
}

/** Every question for the doctor the backend wrote — dose changes and interaction flags —
 *  once each, in the list's order. */
export function questionLines(lines: readonly LineOut[]): string[] {
  const seen = new Set<string>();
  const out: string[] = [];
  for (const line of lines) {
    for (const text of [...line.doctor_question, ...line.flags.flatMap((flag) => flag.question)]) {
      if (!seen.has(text)) {
        seen.add(text);
        out.push(text);
      }
    }
  }
  return out;
}

/** The line nearest to running out, by the backend's own count; a line with no end date last. */
export function nearestToRunOut(lines: readonly LineOut[]): LineOut | null {
  const counted = lines.filter((line) => line.count && line.count.lines.length > 0);
  counted.sort((a, b) => (a.count!.days_left ?? Number.MAX_SAFE_INTEGER) - (b.count!.days_left ?? Number.MAX_SAFE_INTEGER));
  return counted[0] ?? null;
}

/** The medicines card: the backend's sentences for the tablets nearest to running out (left
 *  out when the feed carries today's cards) and every question for the doctor, under the
 *  source line of the medicine it speaks of. Nothing to say, no card. */
export function medicinesCard(lines: readonly LineOut[], withSupply: boolean): { lines: string[]; provenance: string } | null {
  const nearest = withSupply ? nearestToRunOut(lines) : null;
  const questions = questionLines(lines);
  const body = [...(nearest?.count?.lines ?? []), ...questions];
  if (body.length === 0) return null;
  const about = nearest ?? lines.find((line) => line.doctor_question.length > 0 || line.flags.length > 0) ?? null;
  return { lines: body, provenance: about?.source ?? "" };
}

export function dayKey(date: Date): string {
  const pad = (n: number) => String(n).padStart(2, "0");
  return `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())}`;
}

/** "Monday 14 September" — never with a comma, never "the 14th" (plain words, rule 5). */
export function dateLine(date: Date, locale: string): string {
  const format = new Intl.DateTimeFormat(locale, { weekday: "long", day: "numeric", month: "long" });
  if (locale.startsWith("zh")) return format.format(date);
  const parts = format.formatToParts(date);
  const part = (type: Intl.DateTimeFormatPartTypes) => parts.find((each) => each.type === type)?.value ?? "";
  return `${part("weekday")} ${part("day")} ${part("month")}`;
}

/** "8:05 pm" in English; "20:05" in Malay and Chinese, with no abbreviation to decode. */
export function timeLine(date: Date, locale: string): string {
  return new Intl.DateTimeFormat(locale, { hour: "numeric", minute: "2-digit", hour12: locale.startsWith("en") }).format(date);
}

/** One dose tile under "Now" (D1): each dose the backend marks due and not yet tapped, in its
 *  order, with its own sentence and source — as many tiles as the hero's number counts. */
export interface DueCard {
  lineId: string;
  anchor: string;
  title: string;
  sentence: string;
  provenance: string;
}

export function dueCards(slots: readonly SlotOut[], lines: readonly LineOut[], s: Strings): DueCard[] {
  return slots
    .filter((slot) => slot.due_now && !slot.taken)
    .map((slot) => ({
      lineId: slot.line_id,
      anchor: slot.anchor,
      title: lineTitle(lines.find((each) => each.line_id === slot.line_id), s),
      sentence: slot.card,
      provenance: slot.source,
    }));
}

/** The proud number's line: the catalogue's, for none, one, or the backend's count. */
export function proudLine(proud: number | null, s: Strings): string {
  return proud === null || proud === 0 ? s.today.proudNone : proud === 1 ? s.today.proudOne : fill(s.today.proud, { count: proud });
}

/** "Thu 10:00" — the next visit's day and time as a figure, in his locale's own short forms. */
export function shortWhen(date: Date, locale: string): string {
  const day = new Intl.DateTimeFormat(locale, { weekday: "short" }).format(date);
  const time = new Intl.DateTimeFormat(locale, { hour: "numeric", minute: "2-digit", hour12: false }).format(date);
  return `${day} ${time}`;
}

/** His blood pressures' top numbers, oldest first, the last ten — the backend's readings as it
 *  holds them (subject `blood_pressure`, attribute `reading`), never a number worked out here. */
export function systolics(facts: readonly FactOut[]): number[] {
  return facts
    .filter((fact) => fact.subject === "blood_pressure" && fact.attribute === "reading")
    .map((fact) => ({ at: Date.parse(fact.valid_from), top: (fact.value as { systolic?: unknown } | null)?.systolic }))
    .filter((each): each is { at: number; top: number } => typeof each.top === "number" && Number.isFinite(each.at))
    .sort((a, b) => a.at - b.at)
    .slice(-10)
    .map((each) => each.top);
}
