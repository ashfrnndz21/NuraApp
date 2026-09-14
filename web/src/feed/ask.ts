import type { AnswerLineOut, AnswerOut, AskMode } from "../api/types";
import type { Density } from "../store/session";

/** Ask about a card (E21-04 → E03-05). His question goes to the backend word for word; the
 *  answer is shown as the backend made it — its cited lines, each under a source line, then
 *  the honest line when nothing answers, then the boundary, last. The phone writes no sentence
 *  of the answer: the catalogue only says where a line came from, by what it cites. */

/** Voice for the patient (one thing, heard), text for the caregiver (up to five lines, read). */
export function askMode(density: Density): AskMode {
  return density === "patient" ? "voice" : "text";
}

/** Where a cited line came from, as a catalogue line: his medicines list, his visits, or his
 *  papers (a fact, the event or paper under it). A line that cites nothing has none. */
export type SourceLine = "sourceMedicines" | "sourceVisits" | "sourcePapers";

export function sourceOf(cites: AnswerLineOut["cites"]): SourceLine | null {
  if (cites.length === 0) return null;
  const kinds = new Set(cites.map((cite) => cite.kind));
  if (kinds.has("medication_line")) return "sourceMedicines";
  if (kinds.has("appointment") || kinds.has("provider")) return "sourceVisits";
  return "sourcePapers";
}

export interface AnswerView {
  lines: { text: string; source: SourceLine | null }[];
  honest: string[];
  boundary: string[];
  spoken: string[];
  withheld: boolean;
}

/** The answer in the order it is shown and heard: cited lines, honest lines, boundary last. */
export function answerView(answer: AnswerOut): AnswerView {
  return {
    lines: answer.lines.map((line) => ({ text: line.text, source: sourceOf(line.cites) })),
    honest: [...answer.honest],
    boundary: [...answer.boundary],
    spoken: [...answer.spoken],
    withheld: answer.withheld.length > 0,
  };
}
