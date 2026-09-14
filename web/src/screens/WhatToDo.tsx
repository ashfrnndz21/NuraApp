import type { JSX } from "preact";
import { go } from "../flow";
import { density } from "../store/session";
import { t } from "../strings";
import { Header, Hear, Pill, RefusalNotice, Tile } from "../ui/components";

/** What to do now (E13-02): the card's lines exactly as the backend sent them, in its order —
 *  the reassurance first, the calls, the boundary last — never re-ordered, never trimmed.
 *  With no network, or no answer, it is the backend's offline card, and the page says which. */
export function WhatToDoScreen({ lines, offline, refusal }: { lines: string[]; offline: "network" | "server" | null; refusal: string | null }): JSX.Element {
  const s = t();
  return (
    <main class="screen" data-density={density()} data-testid="what-to-do-screen" data-offline={offline ?? "no"}>
      <Header title={s.day.whatToDo} />
      {offline && (
        <Tile paper role="status" testId="offline-note">
          <p>{offline === "network" ? s.today.offline : s.today.cannotReach}</p>
        </Tile>
      )}
      <RefusalNotice refusal={refusal ?? undefined} />
      <Tile paper role="alert" testId="what-to-do">
        <div class="lines" data-testid="what-to-do-lines">
          {lines.map((line, at) => (
            <p key={at}>{line}</p>
          ))}
        </div>
        <Hear lines={lines} />
      </Tile>
      <Pill onClick={() => go({ name: "today" })} testId="back-today">
        {s.day.backToday}
      </Pill>
    </main>
  );
}
