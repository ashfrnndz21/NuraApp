import type { JSX } from "preact";
import { go } from "../flow";
import { t } from "../strings";
import { Header, Hear, RefusalNotice } from "../ui/components";
import { PaperTile, PillButton } from "../ui/kit";
import { Shell } from "./Shell";

/** What to do now (E13-02): the card's lines exactly as the backend sent them, in its order —
 *  the reassurance first, the calls, the boundary last — never re-ordered, never trimmed.
 *  With no network, or no answer, it is the backend's offline card, and the page says which. */
export function WhatToDoScreen({ lines, offline, refusal }: { lines: string[]; offline: "network" | "server" | null; refusal: string | null }): JSX.Element {
  const s = t();
  return (
    <Shell tab="today" testId="what-to-do-screen" attrs={{ "data-offline": offline ?? "no" }} ask={false}>
      <Header title={s.day.whatToDo} />
      {offline && (
        <PaperTile role="status" testId="offline-note">
          <p>{offline === "network" ? s.today.offline : s.today.cannotReach}</p>
        </PaperTile>
      )}
      <RefusalNotice refusal={refusal ?? undefined} />
      <PaperTile role="alert" testId="what-to-do">
        <div class="lines" data-testid="what-to-do-lines">
          {lines.map((line, at) => (
            <p key={at}>{line}</p>
          ))}
        </div>
        <Hear lines={lines} />
      </PaperTile>
      <PillButton onClick={() => go({ name: "today" })} testId="back-today">
        {s.day.backToday}
      </PillButton>
    </Shell>
  );
}
