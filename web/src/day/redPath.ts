import { Refused } from "../api/client";
import type { OfflineCardsOut, Region } from "../api/types";
import type { Strings } from "../strings";
import { offlineLines, type OfflineKind } from "./model";

/** What the what-to-do screen shows. `lines` are the backend's — its card, or its offline
 *  card as the phone kept it, or the catalogue's copy of that card — never nothing. */
export interface WhatToDo {
  lines: string[];
  /** Why the backend was not reached: no network (or no answer in time), or a server that could
   *  not answer. Null when it was reached. Either way nothing was written and nobody was told. */
  offline: "network" | "server" | null;
  /** The backend said no, by its refusal's name: its sentence is said above the card. */
  refusal: string | null;
}

/** When a red word or the button could not reach the backend — no network, no answer in time, a
 *  server that could not answer, or a no — the offline card: whatever else happened, he is never
 *  left with nothing, and never told the family knows when nobody was told. */
export function whenNotReached(
  kind: OfflineKind,
  failure: unknown,
  kept: OfflineCardsOut | null,
  region: Region | undefined,
  s: Strings,
  language: string,
): WhatToDo {
  const refusal = failure instanceof Refused && failure.status < 500 ? failure.refusal : null;
  const offline = refusal !== null ? null : failure instanceof Refused ? "server" : "network";
  return { lines: offlineLines(kind, kept, region, s, language).lines, offline, refusal };
}
