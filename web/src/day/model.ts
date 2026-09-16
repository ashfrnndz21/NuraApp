import type {
  BriefOut,
  CardClipOut,
  CloudOut,
  DayNudgesOut,
  FeedItemOut,
  ItemDecision,
  NudgePlanOut,
  OfflineCardsOut,
  Region,
  VisitQuestionsOut,
  VisitSummaryOut,
  WhatToDoOut,
} from "../api/types";
import type { Strings } from "../strings";
import type { ClipRef } from "../player/player";

/** The patient's day (W7) as Today, the Visit screen and Me show it, from the backend's answers
 *  alone. Nothing here writes a sentence: every line a function returns is a line the backend
 *  sent, in the order it sent them, or — only for a phone that cannot reach Nura and kept no
 *  copy — the backend's own offline card, word for word, from the catalogue. */

/** The what-to-do card's lines exactly as the backend ordered them: never re-ordered, never
 *  trimmed. The first is the first thing he reads; the last is the boundary it ends on. */
export function whatToDoLines(card: WhatToDoOut): string[] {
  return card.lines.map((line) => line.text);
}

/** Which offline card: a red word tapped with no network, or the button pressed with none. */
export type OfflineKind = "red_flag" | "unknown";

export interface OfflineView {
  lines: string[];
  /** `kept`: the backend's card as the phone kept it. `catalogue`: the same words, built in. */
  from: "kept" | "catalogue";
}

/** What the phone shows when it cannot reach Nura. Never nothing: the kept card when the phone
 *  has one in his language, else the catalogue's copy of the backend's card for his region. */
export function offlineLines(kind: OfflineKind, kept: OfflineCardsOut | null, region: Region | undefined, s: Strings, language: string): OfflineView {
  // A card kept in another language than he reads now is not his card: the catalogue's is.
  const found = kept && kept.language === language ? kept[kind] : [];
  if (found.length > 0) return { lines: found.map((line) => line.text), from: "kept" };
  const f = s.day.fallback;
  const malaysia = region === "MY";
  const lines =
    kind === "red_flag"
      ? [f.youDidRight, f.notSent, malaysia ? f.call999 : f.call995, f.closing]
      : [f.youDidRight, f.notSent, f.callFamily, malaysia ? f.bad999 : f.bad995, f.closing];
  return { lines, from: "catalogue" };
}

export interface BriefView {
  lines: { section: string; text: string }[];
  boundary: string[];
  spoken: string[];
}

/** The whole brief in the backend's order — purpose, what changed, the questions, what to
 *  bring — and the boundary it ends on, last. */
export function briefView(brief: BriefOut): BriefView {
  const body = brief.lines.filter((line) => line.section !== "boundary");
  const fromRows = brief.lines.filter((line) => line.section === "boundary").map((line) => line.text);
  const boundary = brief.boundary ? brief.boundary.split("\n") : fromRows;
  return {
    lines: body.map(({ section, text }) => ({ section, text })),
    boundary,
    spoken: [...body.map((line) => line.spoken), ...boundary],
  };
}

export interface QuestionLine {
  text: string;
  /** The question this line is, when it is one; null for the card's own lines after them. */
  questionId: string | null;
}

/** His one card, line by line in the backend's order, each question line with its id so it can
 *  be taken off on his yes. The reassurance and the boundary lines carry no id. */
export function questionCard(found: VisitQuestionsOut): QuestionLine[] {
  const open = found.questions.filter((question) => !question.removed);
  const used = new Set<string>();
  return found.card.map((text) => {
    const match = open.find((question) => question.text === text && !used.has(question.question_id));
    if (match) used.add(match.question_id);
    return { text, questionId: match?.question_id ?? null };
  });
}

function isClip(value: unknown): value is CardClipOut {
  const clip = value as CardClipOut | null;
  return (
    typeof clip === "object" &&
    clip !== null &&
    typeof clip.line === "string" &&
    typeof clip.artifact_id === "string" &&
    typeof clip.start_s === "number" &&
    typeof clip.end_s === "number" &&
    clip.end_s > clip.start_s
  );
}

/** Where each line of a feed card was said in a consult recording (E21-03), by the line's own
 *  words: the memo card's `cite.clips`. A card with none has an empty map. */
export function clipsOf(item: FeedItemOut): Map<string, CardClipOut> {
  const raw = (item.cite as { clips?: unknown } | null)?.clips;
  const found = new Map<string, CardClipOut>();
  if (!Array.isArray(raw)) return found;
  for (const one of raw) if (isClip(one) && !found.has(one.line)) found.set(one.line, one);
  return found;
}

export function clipRef(clip: CardClipOut): ClipRef {
  return { artifact_id: clip.artifact_id, start_s: clip.start_s, end_s: clip.end_s };
}

export interface CloudView {
  prompt: string[];
  words: { word: string; label: string; red: boolean; size: 1 | 2 | 3 }[];
}

/** The strip on Today, when the backend says it shows: its question, then the words in the
 *  backend's order, biggest first. The reasons stay in the answer, never on his screen. */
export function cloudView(cloud: CloudOut | null): CloudView | null {
  if (!cloud || !cloud.show || cloud.words.length === 0) return null;
  return {
    prompt: [...cloud.prompt],
    words: cloud.words.map((one) => ({ word: one.word, label: one.label, red: one.red, size: one.weight >= 3 ? 3 : one.weight >= 2 ? 2 : 1 })),
  };
}

export type NudgeShown =
  | { from: "handed"; nudgeId: string; kind: string; lines: string[]; why: string; spoken: string[] }
  | { from: "planned"; kind: string; lines: string[]; why: string; spoken: string[] };

const ANSWERED: ReadonlySet<string> = new Set(["accepted", "dismissed"]);

/** The day's nudge, where and when the backend plans it: the one handed over for today that
 *  he has not answered, from its time until it expires; else, with none handed over, the
 *  plan's one draft once its time has come. Never before its time, never after it expires,
 *  and never with no why (E17-03): a nudge is only ever shown with the reason under it, so
 *  one the backend sent with nothing to say for itself does not render. Cap and quiet hours
 *  are the backend's alone to enforce here — this only lays out what it already decided. */
export function nudgeToShow(day: DayNudgesOut | null, plan: NudgePlanOut | null, now: Date): NudgeShown | null {
  const within = (from: string, until: string) => Date.parse(from) <= now.getTime() && now.getTime() < Date.parse(until);
  for (const nudge of day?.nudges ?? []) {
    if (nudge.responses.some((kind) => ANSWERED.has(kind))) continue;
    if (!within(nudge.send_after, nudge.expires_at)) continue;
    if (!nudge.why.trim()) continue;
    const spoken = nudge.voice.length > 0 ? nudge.voice : nudge.lines;
    return { from: "handed", nudgeId: nudge.nudge_id, kind: nudge.kind, lines: [...nudge.lines], why: nudge.why, spoken: [...spoken] };
  }
  if ((day?.nudges.length ?? 0) > 0) return null;
  const draft = plan?.drafts[0];
  if (!draft || !within(draft.send_after, draft.expires_at) || !draft.why.trim()) return null;
  const spoken = draft.voice.length > 0 ? draft.voice : draft.lines;
  return { from: "planned", kind: draft.kind, lines: [...draft.lines], why: draft.why, spoken: [...spoken] };
}

/** Every item of the card, decided: kept, unless he said to leave it out. */
export function decisionsFor(summary: VisitSummaryOut, leftOut: ReadonlySet<string>): ItemDecision[] {
  return summary.items.map((item) => ({ item_id: item.item_id, decision: leftOut.has(item.item_id) ? "rejected" : "confirmed" }));
}

/** The newest card of a visit still waiting for his yes, or none. */
export function waitingSummary(found: readonly VisitSummaryOut[]): VisitSummaryOut | null {
  const waiting = found.filter((one) => !one.confirmed_at);
  waiting.sort((a, b) => Date.parse(b.created_at) - Date.parse(a.created_at));
  return waiting[0] ?? null;
}
