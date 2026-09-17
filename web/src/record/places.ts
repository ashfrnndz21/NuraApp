import type { HomeCareCategory, ReviewCardOut } from "../api/types";

/** Where in the Record he is: one place a screen. The Record is one nav entry (`go({ name:
 *  "record", at })`), so every screen under it is named here and nowhere in `flow.ts`. */
export type RecordAt =
  | { name: "hub" }
  /** His medicines; `index` is the one on screen in the patient density. */
  | { name: "medicines"; index?: number }
  | { name: "story"; lineId: string }
  | { name: "add" }
  /** "I have more at home." for one line (E04-05). */
  | { name: "more"; lineId: string }
  | { name: "papers" }
  | { name: "paper"; card: ReviewCardOut }
  | { name: "timeline" }
  | { name: "episode"; episodeId: string }
  /** `category`: Services' "Help at home" grid opens the same directory filtered to one of
   *  its four tiles (board-fidelity-round-2); left off, this is his doctors and clinics. */
  | { name: "providers"; category?: HomeCareCategory }
  | { name: "provider"; providerId: string }
  | { name: "changes" }
  | { name: "trends"; analyte?: string }
  | { name: "routine" }
  | { name: "builder" }
  | { name: "ledger" };

/** The Record's entries, each one screen. */
export type HubEntry = "medicines" | "papers" | "routine" | "timeline" | "trends" | "providers" | "changes" | "ledger";
