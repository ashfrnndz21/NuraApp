import type { InsightConfidence, InsightOut, InsightsReportOut, InsightSectionKey } from "../api/types";
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
