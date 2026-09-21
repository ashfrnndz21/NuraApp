import type { InsightConfidence, InsightOut, InsightsReportOut, InsightsReportSummaryOut, InsightSectionKey } from "../api/types";
import { fill, type Strings } from "../strings";
import type { TraceStep } from "../ui/kit";

/** The weekly report (W1, docs/design/nura-concept-board.html): the six sections, always in
 *  this order, whichever of them a key's scope opens. Pure view logic only — no fetch, no
 *  hook — so it renders the same from a test as it does on the screen. */
export const SECTION_ORDER: readonly InsightSectionKey[] = [
  "what_changed",
  "worth_a_look",
  "medicines_and_supplements",
  "what_you_pay",
  "screenings_due",
  "questions_for_the_doctor",
];

/** One section as the screen draws it: the backend's own title and lines when it sent the
 *  section at all; `withheld` when the key's scope leaves it out of `sections` entirely — never
 *  confused with a section Nura looked at and found nothing to say, which is `present` with an
 *  empty `insights` list and says so in its own line. */
export type SectionView =
  | { key: InsightSectionKey | string; state: "withheld" }
  | { key: InsightSectionKey | string; state: "present"; title: string; insights: readonly InsightOut[] };

/** Every section the report could hold, in the fixed order, each present or withheld. A
 *  section the backend sends under a key this order does not name is still shown, at the end,
 *  rather than dropped: the backend's own keys are the source of truth this checks against,
 *  never a fixed list stale on its own (the hard-won rule against a name silently falling
 *  outside a hard-coded list). */
export function sectionsFor(report: Pick<InsightsReportOut, "sections">): SectionView[] {
  const byKey = new Map(report.sections.map((section) => [section.key, section]));
  const known: SectionView[] = SECTION_ORDER.map((key) => {
    const found = byKey.get(key);
    return found ? { key, state: "present", title: found.title, insights: found.insights } : { key, state: "withheld" };
  });
  const namedKeys = new Set<string>(SECTION_ORDER);
  const extra: SectionView[] = report.sections.filter((section) => !namedKeys.has(section.key)).map((section) => ({ key: section.key, state: "present", title: section.title, insights: section.insights }));
  return [...known, ...extra];
}

/** The one line the Health card leads with: the first insight of the first section that has
 *  one, in the fixed order — "what changed" first, since that is what is most worth a look.
 *  Null when every section is withheld or empty. */
export function headlineInsight(report: Pick<InsightsReportOut, "sections">): InsightOut | null {
  for (const section of sectionsFor(report)) {
    if (section.state === "present" && section.insights.length > 0) return section.insights[0] ?? null;
  }
  return null;
}

/** The trace while the report is building: every step but the one still streaming is done —
 *  the same rule `AskScreen` draws its own trace by (`ui/kit/Conversation.tsx`'s `TraceStep`). */
export function insightsTraceSteps(steps: readonly { key: string; label: string }[]): TraceStep[] {
  return steps.map((step, at) => ({ key: step.key, text: step.label, done: at < steps.length - 1 }));
}

/** Which catalogue word says how sure Nura is: the backend's `worth_a_look` becomes the
 *  catalogue's `worthALook`, the only one whose spelling does not match its own key. */
export function confidenceWordKey(confidence: InsightConfidence): "sure" | "likely" | "worthALook" {
  return confidence === "worth_a_look" ? "worthALook" : confidence;
}

/** A section's insights with one already shown as the screen's own headline left out of the
 *  list underneath it (package 10 review: "say it once") — never dropped, only not repeated;
 *  its own chip/why/ask row still shows, attached under the headline instead
 *  (`InsightActions`). `emptyBecausePromoted` tells the caller the section is not genuinely
 *  empty (which would say `sectionEmpty`) — it only looks that way because its one finding
 *  moved up top. Pure, so the "say it once" rule is a unit on its own. */
export interface SectionRenderView {
  insights: readonly InsightOut[];
  emptyBecausePromoted: boolean;
}
export function sectionInsightsView(original: readonly InsightOut[], promotedId: string | null | undefined): SectionRenderView {
  if (!promotedId) return { insights: original, emptyBecausePromoted: false };
  const insights = original.filter((one) => one.insight_id !== promotedId);
  return { insights, emptyBecausePromoted: insights.length === 0 && original.length > 0 };
}

/** Who an insight's "Ask … this" button names (package 10 review): the backend's `ask_who` is
 *  always one of `AskWho`'s three members — `"doctor"`, `"pharmacist"`, `"nobody"` — never a
 *  literal name (`app.reasoning.analyst.port.AskWho`), so `"Ask {ask_who} this"` read verbatim
 *  ("Ask doctor this") is broken wording, not a real doctor's name Nura invented.
 *
 *  A real name is used only when the record already names one — the doctor of the next visit
 *  (`AppointmentOut.doctor`), never guessed — else the plain, always-true word ("your doctor" /
 *  "{name}'s doctor" in the caregiver's voice), the same fallback `doctor_to_ask` already picks
 *  on the backend when no visit names one. `"nobody"` (an insight with no one worth asking)
 *  returns `null`: no button, never "Ask nobody this". Pure, unit-testable on its own for the
 *  named/unnamed × owner/caregiver matrix. */
export function askWhoLabel(askWho: string | null, s: Strings, owner: boolean, name: string, nextVisitDoctor: string | null): string | null {
  if (askWho === "doctor") {
    if (nextVisitDoctor) return nextVisitDoctor;
    return owner ? s.insights.yourDoctor : fill(s.insights.yourDoctorOther, { name });
  }
  if (askWho === "pharmacist") {
    return owner ? s.insights.yourPharmacist : fill(s.insights.yourPharmacistOther, { name });
  }
  return null;
}

// --- the Health Analyst screen's own live stream (package 10) --------------------------------

/** The screen while `POST …/insights/stream` is in flight, then settled — one state, never
 *  two truths at once (a report and a working line both on screen, or a report and an error
 *  both on screen). Pure and hookless, like every other view-logic function in this file, so
 *  it is a unit on its own, not only ever seen through a rendered screen (`insights.test.ts`).
 *
 *  `working`'s `statusText` is ONE line, replaced in place as each real `step` event arrives —
 *  never an accumulating list (`docs/design/README.md` rule 2). It starts empty (before the
 *  connection has answered with anything at all) and is never cleared once set: a network
 *  failure mid-stream keeps whatever the last real stage said, so the person can see how far
 *  Nura got rather than losing that the moment the connection drops (package 10 §4, "what
 *  arrived stays"). */
export type AnalystStreamState =
  | { phase: "idle" }
  | { phase: "working"; statusText: string }
  | { phase: "done"; report: InsightsReportOut; statusText: string }
  | { phase: "error"; statusText: string; message: string };

export type AnalystStreamAction =
  | { type: "start" }
  | { type: "step"; label: string }
  | { type: "report"; report: InsightsReportOut }
  | { type: "error"; message: string }
  | { type: "reset" };

export const ANALYST_STREAM_IDLE: AnalystStreamState = { phase: "idle" };

export function analystStreamReducer(state: AnalystStreamState, action: AnalystStreamAction): AnalystStreamState {
  switch (action.type) {
    case "start":
      return { phase: "working", statusText: "" };
    case "step":
      // A step arriving after the stream has already settled (a stray, late event) never
      // reopens a finished or failed screen — the same "settle once" rule `insightsStream`
      // itself keeps for its own promise.
      return state.phase === "working" ? { phase: "working", statusText: action.label } : state;
    case "report":
      return { phase: "done", report: action.report, statusText: state.phase === "working" ? state.statusText : "" };
    case "error": {
      const statusText = state.phase === "working" || state.phase === "error" ? state.statusText : "";
      return { phase: "error", statusText, message: action.message };
    }
    case "reset":
      return ANALYST_STREAM_IDLE;
  }
}

/** "What Nura looked at": the real stages' bare nouns, joined the same way Ask's own
 *  `lookedAtParts` already joins them (`Ask.tsx`) — comma-and-space, never an invented "and".
 *  Used to fill the SAME catalogue string Ask uses, `feed.askLookedAt`
 *  ("What Nura looked at: {parts}"), never a second translation of the same words. */
export function lookedAtParts(steps: readonly { name: string }[]): string {
  return steps.map((step) => step.name).join(", ");
}

/** Every past report, newest first — the ordering "Health Analyst"'s own quiet list draws in
 *  (`GET /profiles/{id}/insights/list` already answers newest first; this is the client's own
 *  guarantee of it, not a trust in the wire order, and the tie-breaker a frozen clock in a test
 *  or a checkpoint needs). */
export function pastReportsNewestFirst(reports: readonly InsightsReportSummaryOut[]): InsightsReportSummaryOut[] {
  return [...reports].sort((a, b) => Date.parse(b.generated_at) - Date.parse(a.generated_at) || b.report_id.localeCompare(a.report_id));
}
