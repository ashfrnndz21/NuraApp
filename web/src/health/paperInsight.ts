import type { InsightOut, PaperInsightKeepOut, PaperInsightOut, ReviewCardOut } from "../api/types";
import { reportRow, type ReportRowView } from "../onboarding/review";
import type { Strings } from "../strings";

/** Checkpoint 3, "What it means for you" (`docs/design/experience-blueprint.html` scene
 *  `insight`): pure view logic for the screen that follows a confirmed paper — no fetch, no
 *  hook — so it renders the same from a test as it does on the screen. Nothing here invents a
 *  stage, a delay or a value: every field is either the backend's own real step/report, or a
 *  row already computed off the confirmed card's own printed ranges (`reportRow`, reused
 *  unchanged from the onboarding report table — the same "Above/In range/Below" logic, never a
 *  second one). */

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

/** "What stands out on this paper": every field of the just-confirmed card whose reading falls
 *  outside the range printed on the paper itself — the same `reportRow`/`rangeStatus` the
 *  report table already draws every row through (`web/src/onboarding/review.ts`), filtered to
 *  the rows worth a second look. Ordered as the paper prints them (`position`), never
 *  re-ranked. Computed from the card the person just confirmed (already in hand — it is the
 *  same object `ReviewStep.looksRight()` just sent to the backend), never a second read of the
 *  paper-scoped insight, which carries no raw values or ranges at all. */
export function standoutRows(card: Pick<ReviewCardOut, "fields">, s: Strings, locale: string): ReportRowView[] {
  return [...card.fields]
    .sort((a, b) => a.position - b.position)
    .map((field) => reportRow(field, s, locale))
    .filter((row) => row.status === "above" || row.status === "below");
}

// --- the questions: which ones the person wants to keep ------------------------------------

export type QuestionSelection = ReadonlySet<string>;

/** Every question pre-selected (the blueprint's own card: every question offered is one Nura
 *  would ask, none struck out by default). */
export function initialQuestionSelection(questions: readonly Pick<InsightOut, "insight_id">[]): QuestionSelection {
  return new Set(questions.map((question) => question.insight_id));
}

/** One row tapped: in the set, out of it — never a third state. */
export function toggleQuestionSelection(selection: QuestionSelection, insightId: string): QuestionSelection {
  const next = new Set(selection);
  if (next.has(insightId)) next.delete(insightId);
  else next.add(insightId);
  return next;
}

/** Whether "Keep these questions" has anything to act on: at least one row still checked. The
 *  backend's own `POST …/insight/keep` files every question on the paper's saved insight, with
 *  no way yet to file a caller-chosen subset (confirmed against its own tests: the call sends
 *  no body, and `kept_count` always equals the whole report's question count) — so a person who
 *  has unchecked every row is stopped here, on the client, rather than being told something was
 *  kept when nothing they still wanted was singled out. */
export function hasQuestionSelection(selection: QuestionSelection): boolean {
  return selection.size > 0;
}

// --- after "Keep": where the questions went -------------------------------------------------

export type KeptWhere = { kind: "visit" } | { kind: "unfiled" };

/** Read straight off `PaperInsightKeepOut.filed` — never a guess, and never a visit named that
 *  the response itself did not name (the response carries an id, not a doctor or a date; saying
 *  more than that would be inventing a visit the way checkpoint 3's own rules forbid). */
export function whereKept(result: Pick<PaperInsightKeepOut, "filed">): KeptWhere {
  return result.filed === "visit" ? { kind: "visit" } : { kind: "unfiled" };
}
