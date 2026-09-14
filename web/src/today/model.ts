import type { LineOut, Posture, SlotOut } from "../api/types";
import { fill, type Strings } from "../strings";

/** The Today page, built from what the backend already says in his words: today's dose
 *  cards, the reconciled list with its counts, and the State posture. No sentence is
 *  assembled here; every line shown is a whole line from the API or from the catalogue. */

export interface TodayModel {
  posture: Posture;
  slots: SlotOut[];
  lines: LineOut[];
  fetchedAt: string;
}

export type NowCard =
  | { kind: "dose"; lineId: string; anchor: string; title: string; sentence: string; left: number }
  | { kind: "allTaken"; count: number }
  | { kind: "none" };

const ANCHOR_ORDER = ["breakfast", "lunch", "dinner", "bed"];

function anchorRank(anchor: string): number {
  const index = ANCHOR_ORDER.indexOf(anchor);
  return index < 0 ? ANCHOR_ORDER.length : index;
}

function titleCase(name: string): string {
  return name.length ? name[0]!.toUpperCase() + name.slice(1) : name;
}

/** The one thing now: the first dose of the day not yet tapped, by his anchors in order. */
export function nextDose(slots: readonly SlotOut[], lines: readonly LineOut[]): NowCard {
  if (slots.length === 0) return { kind: "none" };
  const due = [...slots]
    .filter((slot) => !slot.taken)
    .sort((a, b) => anchorRank(a.anchor) - anchorRank(b.anchor));
  const next = due[0];
  if (!next) return { kind: "allTaken", count: slots.length };
  const line = lines.find((each) => each.line_id === next.line_id);
  return {
    kind: "dose",
    lineId: next.line_id,
    anchor: next.anchor,
    title: titleCase(line?.name ?? next.generic),
    sentence: next.card,
    left: due.length,
  };
}

export function greeting(hour: number, name: string, s: Strings): string {
  const template =
    hour < 12 ? s.today.greetingMorning : hour < 18 ? s.today.greetingAfternoon : s.today.greetingEvening;
  return fill(template, { name });
}

/** "You took it this morning." — the moment named the way he would, never as a clock time. */
export function tookLine(hour: number, s: Strings): string {
  if (hour < 12) return s.today.tookMorning;
  if (hour < 18) return s.today.tookAfternoon;
  if (hour < 21) return s.today.tookEvening;
  return s.today.tookNight;
}

export function stateLines(posture: Posture, s: Strings): string[] {
  const first =
    posture === "act" ? s.today.stateAct : posture === "watch" ? s.today.stateWatch : s.today.stateStable;
  return [first, s.today.boundary1, s.today.boundary2];
}

/** The tablets card: the line nearest to running out, in the backend's own sentences. */
export function supplyLines(lines: readonly LineOut[]): string[] | null {
  const counted = lines
    .filter((line) => line.count && line.count.lines.length > 0)
    .sort((a, b) => (a.count!.days_left ?? 1e9) - (b.count!.days_left ?? 1e9));
  const first = counted[0];
  if (!first || !first.count) return null;
  return [...first.count.lines, ...first.count.reorder];
}

/** A local calendar day, `YYYY-MM-DD`, in the phone's own time zone. */
export function dayKey(date: Date): string {
  const y = date.getFullYear();
  const m = String(date.getMonth() + 1).padStart(2, "0");
  const d = String(date.getDate()).padStart(2, "0");
  return `${y}-${m}-${d}`;
}

/** "Monday 14 September" in his language: the day and the date, never "the 14th". */
export function dateLine(date: Date, locale: string): string {
  return new Intl.DateTimeFormat(locale, { weekday: "long", day: "numeric", month: "long" }).format(date);
}
