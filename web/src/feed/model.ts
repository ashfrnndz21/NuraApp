import type { FeedItemOut, ThreadCardKind } from "../api/types";
import { isLanguage, type Language } from "../strings";
import { feedLines, whyLine } from "../today/model";

/** One feed card as the pager shows it, taken whole from the backend's item: its headline,
 *  its body (the boundary lines kept apart, as the boundary), its why, its spoken twin, the
 *  State it was rendered from. Nothing here writes a sentence, and nothing re-ranks: the
 *  pager shows the items in the order the backend answered them. The catalogue only names
 *  the section a card sits in and the buttons around it. */

export type Variant =
  | "flag"
  | "now"
  | "reading"
  | "gate"
  | "duty"
  | "story"
  | "learning"
  | "memo"
  | "reorder"
  | "visit"
  | "notice"
  | "recallAction"
  | "clip"
  | "recap"
  | "local"
  | "seasonal"
  | "food"
  | "text";

const VARIANTS: Record<string, Variant> = {
  flag: "flag",
  now: "now",
  reading: "reading",
  gate: "gate",
  duty: "duty",
  story: "story",
  learning: "learning",
  memo: "memo",
  reorder: "reorder",
  visit: "visit",
  // The logistics card, the day before a visit and on the day (E05-03): a visit card.
  visit_logistics: "visit",
  notice: "notice",
  // His own pack is one of a recall's batches (#183): what he can do about it today.
  recall_action: "recallAction",
  // The feed's richer formats (F1): a compressed video, his week in 30 seconds, a local
  // alert, a season coming, and the week's food choice.
  clip: "clip",
  recap: "recap",
  local: "local",
  seasonal: "seasonal",
  food: "food",
};

/** The card's look, by the backend's type. A type this client does not know yet is shown as
 *  plain text — its own lines, never dropped and never guessed at. */
export function variantOf(item: Pick<FeedItemOut, "type">): Variant {
  return VARIANTS[item.type] ?? "text";
}

/** The small label above a card: the section of the supply it came from. None for a red
 *  flag (its headline says it) or the gate. */
export type Section = "now" | "today" | "story" | "learning";

export function sectionOf(item: Pick<FeedItemOut, "supply">): Section | null {
  switch (item.supply) {
    case "now":
    case "today":
    case "story":
    case "learning":
      return item.supply;
    default:
      return null;
  }
}

/** The buttons down the side of every card. The gate is not content: it keeps its spoken twin
 *  and its one action, Keep going. The duty card is not a gate — the caregiver's list has
 *  none — so it carries every side action, Not for me and Hear among them. */
export type SideAction = "hear" | "ask" | "family" | "notForMe";
const EVERY: readonly SideAction[] = ["hear", "ask", "family", "notForMe"];
const GATE_ONLY: readonly SideAction[] = ["hear"];

/** The one action a card may carry besides the side actions. The now card says "Tap Taken"
 *  — Taken lives on Today's Now card, where the backend says which dose is due, so here the
 *  action goes there; the gate's is Keep going. No other card has one. */
export type CardAction = "keepGoing" | "toTablets";

/** Which of E12's thread cards a feed card can be shared as, by reference. Only the kinds the
 *  thread can render from a State: a reading and a visit. Anything else cannot be sent yet
 *  and the card says so — the client never copies a card's words into the thread. */
const SHARE_AS: Partial<Record<Variant, ThreadCardKind>> = { reading: "reading", visit: "visit" };

export function shareAs(item: Pick<FeedItemOut, "type">): ThreadCardKind | null {
  return SHARE_AS[variantOf(item)] ?? null;
}

export interface CardView {
  itemId: string;
  variant: Variant;
  section: Section | null;
  headline: string;
  /** The body, without the boundary lines it ends on. */
  lines: string[];
  /** The boundary an inferring card ends on (a learning card, a notice), line by line. */
  boundary: string[];
  /** Why am I seeing this: the backend's plain line. */
  why: string;
  /** The page a learning card cites (E21-06): who published it, and the link to it, from
   *  the backend's cite. Null on every other card, and on a cite without an https link. */
  source: { publisher: string; url: string } | null;
  /** A clip (a compressed video, or his week in 30 seconds): what the card plays on a tap. */
  clip: ClipView | null;
  /** The spoken twin: the backend's voice script; where it wrote none, the lines shown. */
  spoken: string[];
  /** The State the card was rendered from. */
  stateId: string;
  language: string;
  actions: readonly SideAction[];
  action: CardAction | null;
}

/** The cards made from an allowlisted page: each names its publisher and links it. */
const SOURCED = new Set(["learning", "clip", "local", "seasonal", "food"]);

/** The cited page of a card made from an allowlisted page, as the backend's cite names it:
 *  its publisher and an https link. Nothing for any other card, and nothing the backend did
 *  not send. */
export function sourceOf(item: Pick<FeedItemOut, "type" | "cite">): CardView["source"] {
  if (!SOURCED.has(item.type) || item.cite === null) return null;
  const { publisher, url } = item.cite as { publisher?: unknown; url?: unknown };
  if (typeof publisher !== "string" || publisher.trim() === "") return null;
  if (typeof url !== "string" || !url.startsWith("https://")) return null;
  return { publisher, url };
}

/** What a clip card plays, from the backend's card and its cite — never guessed:
 *  the still (always, from Nura's own server), the excerpt only where the publisher's licence
 *  let the server keep one, and the whole video's page on the publisher's own site, linked for
 *  him to tap. His week in 30 seconds has no video behind it, so no link. */
export interface ClipView {
  /** The server kept an excerpt (the licence allows reuse): it plays under the narration. */
  excerpt: boolean;
  /** The whole video on the publisher's site, https only; null for the recap. */
  fullUrl: string | null;
  publisher: string | null;
}

export function clipOf(item: Pick<FeedItemOut, "format" | "cite">): ClipView | null {
  if (item.format !== "clip") return null;
  const cite = (item.cite ?? {}) as { excerpt?: unknown; full_url?: unknown; publisher?: unknown; media?: unknown };
  const video = cite.media === "video";
  const fullUrl = video && typeof cite.full_url === "string" && cite.full_url.startsWith("https://") ? cite.full_url : null;
  const publisher = typeof cite.publisher === "string" && cite.publisher.trim() !== "" ? cite.publisher : null;
  return { excerpt: video && cite.excerpt === true, fullUrl: fullUrl && publisher ? fullUrl : null, publisher };
}

export function cardView(item: FeedItemOut): CardView {
  const { lines, boundary } = feedLines(item);
  const variant = variantOf(item);
  const gate = variant === "gate";
  return {
    itemId: item.item_id,
    variant,
    section: sectionOf(item),
    headline: item.headline,
    lines,
    boundary,
    why: whyLine(item),
    source: sourceOf(item),
    clip: clipOf(item),
    spoken: item.voice.length > 0 ? [...item.voice] : [item.headline, ...item.body].filter((line) => line.trim().length > 0),
    stateId: item.rendered_from_state,
    language: item.language,
    actions: gate ? GATE_ONLY : EVERY,
    action: variant === "gate" ? "keepGoing" : variant === "now" ? "toTablets" : null,
  };
}

/** The caregiver's list says what became of each card on his page, from the backend's own
 *  status; the patient's never does. The duty card is hers, about who is on duty, not something
 *  sent to him. */
export type StatusLine = "statusHeld" | "statusSent" | "statusOpened" | "statusPlayed" | "statusDismissed";

export function statusLine(item: Pick<FeedItemOut, "status" | "type">, audience: string): StatusLine | null {
  if (audience !== "caregiver" || item.type === "duty") return null;
  switch (item.status) {
    case "held":
      return "statusHeld";
    case "sent":
      return "statusSent";
    case "opened":
      return "statusOpened";
    case "played":
      return "statusPlayed";
    case "dismissed":
      return "statusDismissed";
    default:
      return null;
  }
}

/** The language a card is read out in: the card's own, when Nura speaks it; else the app's. */
export function speechLanguage(code: string, fallback: Language): Language {
  const short = code.toLowerCase().slice(0, 2);
  return isLanguage(short) ? short : fallback;
}
