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

/** The Services tab's Care services section (D1): the local alerts the feed already made for
 *  him — dengue, haze, heat, a season — never a fresh call, and never fiction. `app.delivery.
 *  feed.local` decides whether one exists at all; here we only pick the ones already in his
 *  page. */
export function careCards(items: readonly FeedItemOut[]): FeedItemOut[] {
  return items.filter((item) => variantOf(item) === "local");
}

/** The Services tab's Guides section: the same evergreen explainers and clips Home's learning
 *  section shows, filtered to those two kinds — nothing seasonal or food-specific, which stay
 *  on Home. */
export function guideCards(items: readonly FeedItemOut[]): FeedItemOut[] {
  return items.filter((item) => variantOf(item) === "learning" || variantOf(item) === "clip");
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
  /** The recommendation broker's own "did you know" pick (`app.delivery.recommend.rules.
   *  did_you_know`, RE-07's `why.rule` on the backend's card): the eyebrow says "Did you
   *  know", not the plain "In simple words" every other learning card carries. */
  didYouKnow: boolean;
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

/** One caption of a Nura-made clip, timed from the clip's start (`app.delivery.feed.
 *  clipmaker.ClipScript.captions`, milliseconds) — never recomputed on the client, so a
 *  caregiver's Why sheet and the player agree on when a line was said. */
export interface ClipCaption {
  atMs: number;
  text: string;
}

/** What a clip card plays, from the backend's card and its cite — never guessed. A publisher
 *  clip's still is always from Nura's own server, the excerpt only where the publisher's
 *  licence let the server keep one, and the whole video is a link to the publisher's own
 *  site. A Nura-made clip (`kind: "nura_made"`, RE-07 item 1) has no still and no excerpt to
 *  fetch: it is his own words over one of the kit's warm scenes, its captions carried on the
 *  card itself. */
export interface ClipView {
  kind: "publisher" | "nura_made";
  /** The server kept an excerpt (the licence allows reuse): it plays under the narration.
   *  Always false for a Nura-made clip — there is no video to excerpt. */
  excerpt: boolean;
  /** The whole video on the publisher's site, https only; null for the recap and for a
   *  Nura-made clip, which links to nothing off this app. */
  fullUrl: string | null;
  publisher: string | null;
  /** The warm scene a Nura-made clip plays over (`app.delivery.feed.clipmaker.SCENES`); null
   *  for a publisher clip, which shows the still instead. */
  scene: string | null;
  /** A Nura-made clip's own captions, already timed; empty for a publisher clip, whose
   *  captions are fetched from `GET …/feed/{item}/clip/captions` instead. */
  captions: readonly ClipCaption[];
  durationMs: number | null;
}

export function clipOf(item: Pick<FeedItemOut, "format" | "cite">): ClipView | null {
  if (item.format !== "clip") return null;
  const cite = (item.cite ?? {}) as {
    excerpt?: unknown;
    full_url?: unknown;
    publisher?: unknown;
    media?: unknown;
    kind?: unknown;
    scene?: unknown;
    source?: unknown;
    duration_ms?: unknown;
    captions?: unknown;
  };
  if (cite.kind === "nura_made") {
    const scene = typeof cite.scene === "string" && cite.scene.trim() !== "" ? cite.scene : "morning";
    const captions = Array.isArray(cite.captions)
      ? cite.captions
          .filter(
            (one): one is { at_ms: unknown; text: unknown } =>
              typeof one === "object" && one !== null
          )
          .filter((one) => typeof one.at_ms === "number" && typeof one.text === "string" && one.text.trim() !== "")
          .map((one) => ({ atMs: one.at_ms as number, text: one.text as string }))
      : [];
    const durationMs = typeof cite.duration_ms === "number" ? cite.duration_ms : null;
    return { kind: "nura_made", excerpt: false, fullUrl: null, publisher: null, scene, captions, durationMs };
  }
  const video = cite.media === "video";
  const fullUrl = video && typeof cite.full_url === "string" && cite.full_url.startsWith("https://") ? cite.full_url : null;
  const publisher = typeof cite.publisher === "string" && cite.publisher.trim() !== "" ? cite.publisher : null;
  return {
    kind: "publisher",
    excerpt: video && cite.excerpt === true,
    fullUrl: fullUrl && publisher ? fullUrl : null,
    publisher,
    scene: null,
    captions: [],
    durationMs: null,
  };
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
    didYouKnow: item.why.rule === "did_you_know",
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
