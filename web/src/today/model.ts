import type { DocumentKind, FactOut, FeedItemOut, LineOut, NowOut, Posture, SlotOut, StateDriverOut, StateOut } from "../api/types";
import { kindTitle } from "../onboarding/review";
import { fill, type Language, type Strings } from "../strings";

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
  // A profile with no name yet is greeted without the comma and the gap ("Good morning."),
  // never "Good morning, ." — the name's own separator goes with it, in every language.
  const said = name.trim() ? line : line.replace(/[,，]\s*\{name\}/, "");
  return fill(said, { name: name.trim() });
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

/** His large-text setting as his State holds it (the `vision` subject of the functional
 *  dimension, E01's settings): true or false, or null when this key does not read that part of
 *  the State and the phone keeps what it has. */
export function largeTextOf(state: Pick<StateOut, "dimensions"> | null): boolean | null {
  const functional = state?.dimensions?.functional;
  if (!functional) return null;
  return functional.facts?.vision?.large_text?.value === true;
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

/** "14 September" — the day and the month, for under a weekday already said (the visit tile). */
export function dayMonthLine(date: Date, locale: string): string {
  const format = new Intl.DateTimeFormat(locale, { day: "numeric", month: "long" });
  if (locale.startsWith("zh")) return format.format(date);
  const parts = format.formatToParts(date);
  const part = (type: Intl.DateTimeFormatPartTypes) => parts.find((each) => each.type === type)?.value ?? "";
  return `${part("day")} ${part("month")}`;
}

/** "8:05 pm" in English; "20:05" in Malay and Chinese, with no abbreviation to decode. */
export function timeLine(date: Date, locale: string): string {
  return new Intl.DateTimeFormat(locale, { hour: "numeric", minute: "2-digit", hour12: locale.startsWith("en") }).format(date);
}

/** One dose tile under "Now" (D1): each dose the backend marks due and not yet tapped, in its
 *  order, with its own sentence and source — as many tiles as the hero's number counts. */
export interface DueCard {
  /** The backend's word on the button: "Taken" to him, "Pa took it" to anyone else. */
  takenLabel: string;
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
      takenLabel: slot.taken_label,
    }));
}

/** The proud number's line: the catalogue's, for none, one, or the backend's count. */
export function proudLine(proud: number | null, s: Strings): string {
  return proud === null || proud === 0 ? s.today.proudNone : proud === 1 ? s.today.proudOne : fill(s.today.proud, { count: proud });
}

/** The line under the State's word on her Home: nothing that reassures while a red-flag card is
 *  on the page (the flag goes first; the State does not count it), the stale line when the State
 *  is behind or the page is the phone's kept copy, else the backend's own line. */
export function homeHeroWords(page: Pick<TodayModel, "stale" | "line">, on: { flagged: boolean; kept: boolean }, s: Strings): string | null {
  if (on.flagged) return null;
  if (page.stale || on.kept) return s.today.staleState;
  return page.line ?? null;
}

/** What her Home's hero shows. While a red-flag card is on the page, nothing of the State: no
 *  word ("Steady" in large type over a flag reassures), no line, no chips — the flag goes first
 *  and the State does not count it. On the phone's kept page, the word with the stale line and no
 *  chips (they read as now). Otherwise the State's word, its line, and its chips. */
export function homeHero(
  page: Pick<TodayModel, "stale" | "line" | "word">,
  on: { flagged: boolean; kept: boolean },
  s: Strings,
): { word: string | null; line: string | null; drivers: boolean } {
  if (on.flagged) return { word: null, line: null, drivers: false };
  return { word: page.word ?? null, line: homeHeroWords(page, on, s), drivers: !on.kept };
}

/** Safety check 5: whether the Hero's furniture — its wave, its "How is he feeling?" question,
 *  its illustration — and the daily check-in card may draw. Never while a red-flag card is on
 *  the page: a wave and a smiling illustration over a flag read as reassurance exactly the way a
 *  State word would, so they follow the same rule as `homeHero`, on both densities. */
export function heroFurnitureAllowed(on: { flagged: boolean }): boolean {
  return !on.flagged;
}

/** The day of the week in full, in his language: "Thursday", never "Thu" (plain words, rule 5). */
export function weekdayOf(date: Date, locale: string): string {
  return new Intl.DateTimeFormat(locale, { weekday: "long" }).format(date);
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

// --- the new Home's hero (P1's orb): the day's top item, and the one headline it earns -------

/** The day's one thing to say, as a closed set of real, already-known facts — never a generic
 *  feed card's own title (the defect the owner found: "Your tablets *today*" said nothing).
 *  Each variant carries only what its own template needs, and only from where that fact
 *  already lives: the dose the backend marks due, the day's own reading, the next visit within
 *  a week, a medicine nearing its reorder point, or a feed card the backend itself flagged an
 *  insight (its own real headline, never re-composed). */
/** A newly confirmed paper's own range summary (owner review round 3, fix #2): the review
 *  card's own fields, each against its own printed range (`rangeStatus`, onboarding/review.ts —
 *  reused, never a second reckoning of the same question). `outside`/`total` are both `null`
 *  with no field on the paper carrying a printed range at all — the honest "no ranges" case,
 *  never a "0 of 0" pretending to be a real count. */
export interface PaperSummary {
  item: FeedItemOut;
  documentKind: DocumentKind;
  /** The date printed on the paper (fix #3) — never `created_at`, the day it happened to be
   *  confirmed. */
  date: Date;
  outside: number | null;
  total: number | null;
}

export type HomeTopItem =
  | { kind: "doseDue"; title: string; when: string }
  | { kind: "allTaken" }
  | { kind: "reading"; systolic: number; diastolic: number }
  | { kind: "visit"; doctor: string | null; at: Date }
  | { kind: "reorder"; title: string; days: number }
  | ({ kind: "paper" } & PaperSummary);

export interface HomeTopInputs {
  dose: NowCard | null;
  /** Today's own reading, or null with none written down today (a reading from another day
   *  never drives the headline — that is not "today's" anything). */
  reading: { systolic: number; diastolic: number } | null;
  nextVisit: { scheduled_at: string; doctor: string | null } | null;
  lines: readonly LineOut[];
  /** A newly confirmed paper's own range summary, read for the feed's own top insight/alert
   *  card (`category`) — `null` with no such card, or with one whose own summary has not
   *  finished loading yet (`usePaperInsight`, screens/Today.tsx: the caller holds this at `null`
   *  until it knows one way or the other, never guesses). No other feed card type earns a
   *  headline here (owner review round 3): a card type with no template of its own is a quiet
   *  day, never a bare title standing in for one (the defect the owner found, "From your
   *  papers"). */
  paper: PaperSummary | null;
}

const WEEK_MS = 7 * 24 * 60 * 60 * 1000;

/** The single fact Home's hero speaks about today, in priority order: the dose due right now,
 *  else every dose already taken, else today's own reading, else a visit within the week, else
 *  a medicine close enough to run out to reorder, else the feed's own flagged insight — else
 *  none, which is a quiet day (`homeState` below), never a bare card title standing in. */
export function homeTopItem(on: HomeTopInputs, now: Date, s: Strings): HomeTopItem | null {
  if (on.dose?.kind === "due") return { kind: "doseDue", title: on.dose.title, when: on.dose.anchor };
  if (on.dose?.kind === "allTaken") return { kind: "allTaken" };
  if (on.reading) return { kind: "reading", systolic: on.reading.systolic, diastolic: on.reading.diastolic };
  if (on.nextVisit) {
    const at = new Date(on.nextVisit.scheduled_at);
    const until = at.getTime() - now.getTime();
    if (until >= 0 && until <= WEEK_MS) return { kind: "visit", doctor: on.nextVisit.doctor, at };
  }
  const nearest = nearestToRunOut(on.lines);
  if (nearest?.count?.reorder_due && typeof nearest.count.days_left === "number") {
    return { kind: "reorder", title: lineTitle(nearest, s), days: nearest.count.days_left };
  }
  if (on.paper) return { kind: "paper", ...on.paper };
  return null;
}

export type HomeState = "safety" | "busy" | "quiet";

/** Which of Home's three hero treatments draws (safety check 5's own rule, extended): a flag
 *  or an act posture outranks everything, including the quiet-day greeting — neither a big
 *  breathing orb nor a chip asking "what shall we look at" may sit over either, so this never
 *  reaches `busy`/`quiet` while one holds. Only once neither holds does the day's own top item
 *  decide busy from quiet. */
export function homeState(on: { flagged: boolean; act: boolean; topItem: HomeTopItem | null }): HomeState {
  if (on.flagged || on.act) return "safety";
  return on.topItem === null ? "quiet" : "busy";
}

/** The one italic accent a Home headline carries (`SoftText`'s `*word*`): the sentence's own
 *  last word, always — the way every example in the blueprint accents its closing word
 *  ("...raise with your *doctor.*"). Never a free choice, and safe with a slot value that is
 *  itself more than one word (a time, a name): the accent lands on the sentence's true last
 *  word, not necessarily the whole filled phrase. A sentence with no words is returned as is. */
export function accentLastWord(text: string): string {
  const words = text.trim().split(/\s+/).filter(Boolean);
  if (words.length === 0) return text;
  const last = words[words.length - 1]!;
  const match = last.match(/^(.*?)([.,!?;:]*)$/);
  const stem = match?.[1] || last;
  const punct = match?.[2] ?? "";
  if (!stem) return text;
  words[words.length - 1] = `*${stem}*${punct}`;
  return words.join(" ");
}

/** `lineTitle` reads the backend's own colloquial name for the class straight through
 *  (`app/medicines/strings.py`), some of which carry a self-voiced possessive of their own —
 *  English leading "your"/"the" ("your blood pressure tablet"), Malay a trailing "anda"
 *  ("ubat tekanan darah anda"), Chinese a leading "您的" — the same word for every reader
 *  (DoseSection's own cards show it verbatim to a caregiver too). A caregiver headline that
 *  also names her by "{patient}'s" cannot repeat that word without contradicting it ("Pa's Your
 *  blood pressure tablet"), so her templates use the bare noun phrase this strips to — never a
 *  different name for the medicine, only the one word this reader's line never carries. */
export function dropPossessive(title: string): string {
  return title
    .replace(/^(your|the)\s+/i, "")
    .replace(/\s+anda$/i, "")
    .replace(/^您的/, "");
}

/** `lineTitle` capitalises its first letter for a sentence that starts with it (a card's own
 *  title). Embedded mid-sentence instead ("...of {title} are left"), that capital reads as a
 *  mistake, so a template that does not open on `title` reads it back down first. */
function lowerFirst(text: string): string {
  return text.length ? text[0]!.toLowerCase() + text.slice(1) : text;
}

/** The catalogue template for each `HomeTopItem` kind, filled only from that item's own real
 *  facts and accented on its own last word — never the model's free text. An `insight` card
 *  keeps the backend's own real headline, accented the same way; every other kind is composed
 *  from a whole-sentence template in `strings/*.ts` (`home.headline*`/`…Other`). */
export function homeHeadlineFor(item: HomeTopItem, s: Strings, locale: string, self: boolean, patientName: string): string {
  const h = s.home;
  const slots = { patient: patientName } as Record<string, string | number>;
  switch (item.kind) {
    case "doseDue":
      // Self opens the sentence with `title` (its own leading capital is correct there);
      // the caregiver's puts it after "{patient}'s", so it reads back down first.
      Object.assign(slots, { title: self ? item.title : lowerFirst(dropPossessive(item.title)), when: item.when });
      return accentLastWord(fill(self ? h.headlineDoseDue : h.headlineDoseDueOther, slots));
    case "allTaken":
      return accentLastWord(self ? h.headlineAllTaken : fill(h.headlineAllTakenOther, slots));
    case "reading":
      Object.assign(slots, { systolic: item.systolic, diastolic: item.diastolic });
      return accentLastWord(fill(self ? h.headlineReading : h.headlineReadingOther, slots));
    case "visit": {
      Object.assign(slots, { weekday: weekdayOf(item.at, locale), doctor: item.doctor ?? "" });
      const template = item.doctor ? (self ? h.headlineVisit : h.headlineVisitOther) : self ? h.headlineVisitNoDoctor : h.headlineVisitNoDoctorOther;
      return accentLastWord(fill(template, slots));
    }
    case "reorder":
      // Neither template opens on `title` here ("About {days} days of {title}..."), so both
      // read it back down first.
      Object.assign(slots, { title: self ? lowerFirst(item.title) : lowerFirst(dropPossessive(item.title)), days: item.days });
      return accentLastWord(fill(self ? h.headlineReorder : h.headlineReorderOther, slots));
    case "paper": {
      // `kindTitle` capitalises its first letter for a title ("Blood test"); no template here
      // opens on `{kind}`, so it reads back down first, the same reasoning `lowerFirst` already
      // carries elsewhere in this file.
      const kind = lowerFirst(kindTitle(item.documentKind, s));
      const date = dayMonthLine(item.date, locale);
      if (item.total !== null && item.total > 0) {
        if (item.outside !== null && item.outside > 0) {
          Object.assign(slots, { n: item.outside, m: item.total, kind, date });
          return accentLastWord(fill(self ? h.headlinePaperOutside : h.headlinePaperOutsideOther, slots));
        }
        Object.assign(slots, { kind, date });
        return accentLastWord(fill(self ? h.headlinePaperAllIn : h.headlinePaperAllInOther, slots));
      }
      Object.assign(slots, { kind, date });
      return accentLastWord(fill(self ? h.headlinePaperNoRange : h.headlinePaperNoRangeOther, slots));
    }
  }
}

/** What `insightExtraLines` needs beyond the `HomeTopItem` itself: real facts already on the
 *  page or already being fetched for another part of Today, never a new request made only for
 *  this card. Each field is `null`/empty with nothing yet known, never a placeholder line. */
export interface InsightExtraContext {
  /** The due dose's own source line ("As your doctor set it.") — `NowCard`'s "due" variant. */
  doseProvenance: string | null;
  /** Today's own dose count, whole and taken — the day's own tally, not a week the phone does
   *  not carry (there is no weekly count on this page to draw one from truthfully). */
  slotsTotal: number;
  slotsDone: number;
  /** The most recent reading from a day *before* today, if one exists — the insight card's own
   *  comparison for a "reading" headline, which already gave today's own numbers in full. */
  priorSystolic: number | null;
  /** The next visit's own place/driver lines, from its logistics card (`useLogistics`'s own
   *  fetch, read again for Home — the visit tile's card, not a new endpoint). */
  visitAbout: readonly string[];
  /** The medicine's own first reorder sentence, from its `count.lines` (the backend's own
   *  wording — a delivery date or a pharmacy it names — not the day-count the headline used). */
  reorderLine: string | null;
}

/** The insight card's own extra fact (owner review round 2): a real thing the headline did not
 *  already say, from the same `HomeTopItem`'s own kind and real fields — never the headline's
 *  sentence again (the defect the owner found: "Every tablet for today is taken." twice, 40px
 *  apart). `null` when there genuinely is nothing more to say yet (a dose with no source line, a
 *  reading with no earlier one to compare, a visit whose logistics have not loaded, a reorder
 *  with no backend sentence of its own): the card itself does not render then (`HomeHero`,
 *  screens/Today.tsx) — the rows under it still do, directly under the headline. An `insight`
 *  item keeps the feed's own body lines, the one place free text from the backend is shown,
 *  unchanged — that was never the duplicate the owner found. */
export function insightExtraLines(item: HomeTopItem, on: InsightExtraContext, s: Strings, self: boolean, patientName: string): string[] | null {
  const h = s.home;
  const slots = { patient: patientName } as Record<string, string | number>;
  switch (item.kind) {
    case "doseDue":
      return on.doseProvenance ? [on.doseProvenance] : null;
    case "allTaken":
      return on.slotsTotal > 0 ? [fill(self ? h.tookCount : h.tookCountOther, { ...slots, done: on.slotsDone, total: on.slotsTotal })] : null;
    case "reading": {
      if (on.priorSystolic === null) return null;
      const diff = item.systolic - on.priorSystolic;
      const template = diff > 3 ? (self ? h.trendHigher : h.trendHigherOther) : diff < -3 ? (self ? h.trendLower : h.trendLowerOther) : self ? h.trendSame : h.trendSameOther;
      return [fill(template, slots)];
    }
    case "visit":
      return on.visitAbout.length > 0 ? on.visitAbout.slice(0, 2) : null;
    case "reorder":
      return on.reorderLine ? [on.reorderLine] : null;
    case "paper": {
      const lines = feedLines(item.item).lines.slice(0, 2);
      return lines.length > 0 ? lines : null;
    }
  }
}

/** The date the insight card's chip is about — never the feed row's own `created_at` (a
 *  seeding or a generation timestamp, not what the card is *about*, the defect the owner found:
 *  a card about today's tablets showing the day it happened to be written). Today for a dose or
 *  a reading (both are always about today); the visit's own date for a visit; the reorder
 *  read's own moment for a reorder (there is no other date to give it); a paper's own printed
 *  date for a paper (owner review round 3, fix #3 — the defect the owner found: a paper dated
 *  22 January showing "18 Sep", the day it happened to be confirmed, never the day it is about). */
export function homeTopItemDate(item: HomeTopItem, now: Date): Date {
  switch (item.kind) {
    case "doseDue":
    case "allTaken":
    case "reading":
      return now;
    case "visit":
      return item.at;
    case "reorder":
      return now;
    case "paper":
      return item.date;
  }
}

/** "12 September" split for the insight card's date chip: the day, and the month short enough
 *  to sit under it (the blueprint's `<div class="date"><b>12</b><small>Sep</small></div>`). */
export function dateChip(date: Date, locale: string): { day: string; month: string } {
  const parts = new Intl.DateTimeFormat(locale, { day: "numeric", month: "short" }).formatToParts(date);
  const part = (type: Intl.DateTimeFormatPartTypes) => parts.find((each) => each.type === type)?.value ?? "";
  // Three letters, the blueprint's own width for the chip (owner review round 2) — `en-SG`'s
  // own "short" gives "Sept" (four), which the chip has no more room for than "Sep"; slicing
  // after the period is stripped only ever shortens a Latin abbreviation further, and is a
  // no-op on ms's own three letters or zh's bare numeral.
  return { day: part("day"), month: part("month").replace(/\.$/, "").slice(0, 3) };
}

/** The hour the way he says it (plain words, rule 5; the backend's `when_words.say_clock`):
 *  "10 in the morning", "half past 7 in the evening", "8.05 in the morning"; in Malay
 *  "pukul 8 pagi", in Chinese "上午8点半". Twelve-hour, never a colon, on the region's clock. */
export function clockWords(date: Date, language: Language, zone?: string): string {
  const parts = new Intl.DateTimeFormat("en-GB", { hour: "numeric", minute: "numeric", hourCycle: "h23", timeZone: zone }).formatToParts(date);
  const hour24 = Number(parts.find((part) => part.type === "hour")?.value ?? "0") % 24;
  const minute = Number(parts.find((part) => part.type === "minute")?.value ?? "0");
  const words = {
    en: ["in the morning", "in the afternoon", "in the evening", "at night"],
    ms: ["pagi", "petang", "malam", "malam"],
    zh: ["上午", "下午", "晚上", "晚上"],
  }[language];
  const part = words[hour24 < 12 ? 0 : hour24 < 17 ? 1 : hour24 < 21 ? 2 : 3];
  const hour = hour24 % 12 || 12;
  const padded = String(minute).padStart(2, "0");
  if (language === "zh") return `${part}${hour}点${minute === 0 ? "" : minute === 30 ? "半" : `${minute}分`}`;
  if (language === "ms") return `pukul ${minute === 0 ? hour : `${hour}.${padded}`} ${part}`;
  if (minute === 0) return `${hour} ${part}`;
  if (minute === 30) return `half past ${hour} ${part}`;
  return `${hour}.${padded} ${part}`;
}
