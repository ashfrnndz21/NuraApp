import type { AnswerLineOut, AnswerOut, AskMode, ClipOut } from "../api/types";
import type { Density } from "../store/session";

/** Ask about a card (E21-04 → E03-05). His question goes to the backend word for word; the
 *  answer is shown as the backend made it — its cited lines, each under a source line, then
 *  the honest line when nothing answers, then the boundary, last. The phone writes no sentence
 *  of the answer: the catalogue only says where a line came from, by what it cites. */

/** Voice for the patient (one thing, heard), text for the caregiver (up to five lines, read). */
export function askMode(density: Density): AskMode {
  return density === "patient" ? "voice" : "text";
}

/** Where a cited line came from, as a catalogue line: his medicines list, his visits, a paper
 *  still waiting for his own yes (never one already confirmed — those are `sourcePapers`), or
 *  his papers (a fact, the event or paper under it). A line that cites nothing has none. */
export type SourceLine = "sourceMedicines" | "sourceVisits" | "sourceReviewCard" | "sourcePapers";

export function sourceOf(cites: AnswerLineOut["cites"]): SourceLine | null {
  if (cites.length === 0) return null;
  const kinds = new Set(cites.map((cite) => cite.kind));
  if (kinds.has("medication_line")) return "sourceMedicines";
  if (kinds.has("appointment") || kinds.has("provider") || kinds.has("summary_item") || kinds.has("visit_summary")) return "sourceVisits";
  // A card still waiting for his own yes (W2, `app.search.ask.waiting_papers`) is not one of
  // "his papers" yet — that caption would wrongly say it is already confirmed and read.
  if (kinds.has("review_card")) return "sourceReviewCard";
  return "sourcePapers";
}

export interface AnswerView {
  /** `clip`: a line about a recorded visit, which plays what the doctor said on a tap (E03-05). */
  lines: { text: string; source: SourceLine | null; clip: ClipOut | null }[];
  honest: string[];
  boundary: string[];
  spoken: string[];
  withheld: boolean;
}

/** The answer in the order it is shown and heard: cited lines, honest lines, boundary last. */
export function answerView(answer: AnswerOut): AnswerView {
  return {
    lines: answer.lines.map((line) => ({ text: line.text, source: sourceOf(line.cites), clip: line.clip ?? null })),
    honest: [...answer.honest],
    boundary: [...answer.boundary],
    spoken: [...answer.spoken],
    withheld: answer.withheld.length > 0,
  };
}
