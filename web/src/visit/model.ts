import type { LogisticsOut, VisitSummaryOut } from "../api/types";
import type { ClipRef } from "../player/player";

/** The visit day as the Visit screen shows it, from the backend's answers alone: the phone
 *  writes no sentence of the logistics card, the notice or the post-visit card. */

/** The refusals that mean the RECORDING consent is not in force: the owner is shown the words. */
export const CONSENT_REFUSALS: ReadonlySet<string> = new Set([
  "ConsentWithheld",
  "ConsentRevoked",
  "NoConsent",
  "NotTheCurrentWording",
]);

export interface LogisticsView {
  lines: { section: string; text: string }[];
  /** The chief's note, as she wrote it, under her name. */
  note: { label: string; text: string } | null;
  /** The roster's person on duty then, waiting for the yes this key may give. */
  suggestion: { personId: string; name: string } | null;
  spoken: string[];
}

export function logisticsView(card: LogisticsOut): LogisticsView {
  const driver = card.driver;
  return {
    lines: card.lines.map((line) => ({ section: line.section, text: line.text })),
    note: card.note ? { label: card.note.label, text: card.note.text } : null,
    suggestion:
      driver.status === "suggested" && driver.can_say_yes && driver.person_id && driver.name
        ? { personId: driver.person_id, name: driver.name }
        : null,
    spoken: [...card.spoken],
  };
}

export interface SummaryLine {
  text: string;
  /** The stretch of the recording this line was said in, when there is one. */
  clip: ClipRef | null;
}

export interface SummaryView {
  lines: SummaryLine[];
  boundary: string[];
  spoken: string[];
}

/** The card's lines in the backend's order, each with the clip of the item it says, and the
 *  boundary last. An item is matched to its line by its words, once each. */
export function summaryView(summary: VisitSummaryOut): SummaryView {
  const boundary = summary.boundary ? summary.boundary.split("\n") : [];
  const body = summary.lines.slice(0, Math.max(0, summary.lines.length - boundary.length));
  const unused = [...summary.items];
  const lines = body.map((text): SummaryLine => {
    const at = unused.findIndex((item) => item.text === text);
    const item = at >= 0 ? unused.splice(at, 1)[0] : undefined;
    const clip =
      item && summary.recording_artifact_id && item.clip_start_s != null && item.clip_end_s != null
        ? { artifact_id: summary.recording_artifact_id, start_s: item.clip_start_s, end_s: item.clip_end_s }
        : null;
    return { text, clip };
  });
  return { lines, boundary, spoken: [...summary.spoken] };
}

/** "1:06": minutes and seconds beside the red dot. Digits only, nothing to decode. */
export function timer(seconds: number): string {
  const whole = Math.max(0, Math.floor(seconds));
  return `${Math.floor(whole / 60)}:${String(whole % 60).padStart(2, "0")}`;
}
