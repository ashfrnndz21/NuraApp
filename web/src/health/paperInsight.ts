import type { AppointmentOut, PaperInsightKeepOut, PaperInsightOut } from "../api/types";

/** Checkpoint 3, "What it means for you" (`docs/design/experience-blueprint.html` scene
 *  `insight`): pure view logic for the screen that follows a confirmed paper — no fetch, no
 *  hook — so it renders the same from a test as it does on the screen. Nothing here invents a
 *  stage, a delay or a value: every field is either the backend's own real step/report, or the
 *  next visit's own real fields (`AppointmentOut`), read the same way `web/src/screens/tabs.tsx`'s
 *  own `VisitList` already reads them. */

/** One real stage of the stream, as it arrived. */
export interface PaperInsightStep {
  key: string;
  label: string;
}

/** Everything the stream has produced so far: every step in the order it arrived, and the
 *  finished insight once the `report` event lands — `null` until then, and still `null` (never
 *  cleared) if the stream fails partway: whatever arrived stays on screen (checkpoint 3's own
 *  "network failure mid-stream: what arrived stays, a retry"). */
export interface PaperInsightStreamState {
  steps: readonly PaperInsightStep[];
  report: PaperInsightOut | null;
}

export const initialPaperInsightState: PaperInsightStreamState = { steps: [], report: null };

/** One more real step, appended — never reordered, never replaced: the same append-only rule
 *  `feed/askStream.ts`'s `appendSentence` holds to. */
export function withPaperInsightStep(state: PaperInsightStreamState, key: string, label: string): PaperInsightStreamState {
  return { ...state, steps: [...state.steps, { key, label }] };
}

/** The finished insight lands: the steps already shown stay (they are still "what Nura looked
 *  at", and a screen leaving them up costs nothing), the report is now there to draw from. */
export function withPaperInsightReport(state: PaperInsightStreamState, report: PaperInsightOut): PaperInsightStreamState {
  return { ...state, report };
}

/** ONE status line while the stream is still working (`docs/design/README.md` rule 2: never an
 *  accumulating checklist): the newest real step's own label, or `fallback` before the first
 *  one has arrived. Once `report` is there this is never read — the screen moves on to the
 *  headline. */
export function paperInsightStatusText(state: PaperInsightStreamState, fallback: string): string {
  return state.steps.length > 0 ? state.steps[state.steps.length - 1]!.label : fallback;
}

/** Nothing worth asking about, said plainly by the backend's own headline
 *  (`PAPER_NOTHING_LINE`) rather than a fixed line here: the finished report has no
 *  questions at all. */
export function paperInsightHasNothingToAsk(report: Pick<PaperInsightOut, "questions">): boolean {
  return report.questions.length === 0;
}

/** "Looked at": the backend's own real labels, in the order the stream gave them — never a
 *  fixed list, never invented when the stream/response names nothing (`report.looked_at`
 *  empty gives an empty list here too, and the caller draws nothing for it). */
export function lookedAtLabels(report: Pick<PaperInsightOut, "looked_at">): string[] {
  return report.looked_at.map((each) => each.label);
}

// --- the card's own title: "For {doctor} on {date}", or the generic fallback ---------------

export type CardVisit = { kind: "named"; doctor: string; scheduledAt: string } | { kind: "generic" };

/** The next visit, the same "soonest first" order `nura.appointments()` already answers in
 *  (`web/src/screens/tabs.tsx`'s own `VisitList`) — named by its doctor and its date only when
 *  both are real fields on it; otherwise the generic card title, never a guessed doctor or a
 *  visit invented where none is booked. */
export function cardVisitOf(visits: readonly Pick<AppointmentOut, "doctor" | "scheduled_at">[]): CardVisit {
  const next = visits[0];
  if (next && next.doctor && next.doctor.trim()) {
    return { kind: "named", doctor: next.doctor, scheduledAt: next.scheduled_at };
  }
  return { kind: "generic" };
}

// --- after "Keep": where the questions went -------------------------------------------------

export type KeptWhere = { kind: "visit" } | { kind: "unfiled" };

/** Read straight off `PaperInsightKeepOut.filed` — never a guess, and never a visit named that
 *  the response itself did not name (the response carries an id, not a doctor or a date; saying
 *  more than that would be inventing a visit the way checkpoint 3's own rules forbid). */
export function whereKept(result: Pick<PaperInsightKeepOut, "filed">): KeptWhere {
  return result.filed === "visit" ? { kind: "visit" } : { kind: "unfiled" };
}
