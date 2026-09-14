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

/** The buttons down the side of every card. The gate (and the caregiver's gate, the duty
 *  card) is not content: it keeps its spoken twin and its one action, Keep going. */
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
  /** The spoken twin: the backend's voice script; where it wrote none, the lines shown. */
  spoken: string[];
  /** The State the card was rendered from. */
  stateId: string;
  language: string;
  actions: readonly SideAction[];
  action: CardAction | null;
}

export function cardView(item: FeedItemOut): CardView {
  const { lines, boundary } = feedLines(item);
  const variant = variantOf(item);
  const gate = variant === "gate" || variant === "duty";
  return {
    itemId: item.item_id,
    variant,
    section: sectionOf(item),
    headline: item.headline,
    lines,
    boundary,
    why: whyLine(item),
    spoken: item.voice.length > 0 ? [...item.voice] : [item.headline, ...item.body].filter((line) => line.trim().length > 0),
    stateId: item.rendered_from_state,
    language: item.language,
    actions: gate ? GATE_ONLY : EVERY,
    action: variant === "gate" ? "keepGoing" : variant === "now" ? "toTablets" : null,
  };
}

/** The caregiver's list says what became of each card on his page, from the backend's own
 *  status; the patient's never does. Her gate — the duty card — is hers, not held from him. */
export type StatusLine = "statusHeld" | "statusSent" | "statusOpened" | "statusDismissed";

export function statusLine(item: Pick<FeedItemOut, "status" | "type">, audience: string): StatusLine | null {
  if (audience !== "caregiver" || item.type === "duty") return null;
  switch (item.status) {
    case "held":
      return "statusHeld";
    case "sent":
      return "statusSent";
    case "opened":
      return "statusOpened";
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
