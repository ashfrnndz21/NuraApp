import { Refused } from "../api/client";
import type { OfflineCardsOut, Region } from "../api/types";
import type { Strings } from "../strings";
import { offlineLines, type OfflineKind } from "./model";

/** What the what-to-do screen shows. `lines` are the backend's — its card, or its offline
 *  card as the phone kept it, or the catalogue's copy of that card — never nothing. */
export interface WhatToDo {
  lines: string[];
  /** The phone could not reach Nura: nothing was written and nobody was told. */
  offline: boolean;
  /** The backend said no, by its refusal's name: its sentence is said above the card. */
  refusal: string | null;
}

/** When a red word, the button or his words could not reach the backend — no network, a server
 *  that could not answer, or a no — the offline card: whatever else happened, he is never left
 *  with nothing, and never told the family knows when nobody was told. */
export function whenNotReached(kind: OfflineKind, failure: unknown, kept: OfflineCardsOut | null, region: Region | undefined, s: Strings): WhatToDo {
  const said = failure instanceof Refused && failure.status < 500 ? failure.refusal : null;
  return { lines: offlineLines(kind, kept, region, s).lines, offline: said === null, refusal: said };
}
