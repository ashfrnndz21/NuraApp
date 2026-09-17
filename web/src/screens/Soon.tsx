import type { JSX } from "preact";
import { go, type SoonPlace } from "../flow";
import { t } from "../strings";
import { SeedlingIllustration } from "../ui/illustrations";
import { PillButton, TintCard } from "../ui/kit";
import { Shell } from "./Shell";

/** A place Home's grid offers that Nura has not built yet (Things to do, Help at home, In simple words).
 *  Said plainly — Nura cannot do this yet — with the way back, so a tile is never a dead tap and
 *  never pretends there is something behind it. */
export function SoonScreen({ place }: { place: SoonPlace }): JSX.Element {
  const s = t();
  const title = { activities: s.hub.activities, care: s.hub.care, resources: s.hub.resources }[place];
  return (
    <Shell tab="home" testId="soon-screen" attrs={{ "data-place": place }}>
      <TintCard tint="paper" extra="soon-card">
        <SeedlingIllustration class="soon-illo" />
        <h1 class="display-title">{title}</h1>
        <div class="lines">
          <p>{s.hub.soonLine1}</p>
          <p>{s.hub.soonLine2}</p>
        </div>
        <PillButton onClick={() => go({ name: "today" })} testId="soon-back">
          {s.hub.backHome}
        </PillButton>
      </TintCard>
    </Shell>
  );
}
