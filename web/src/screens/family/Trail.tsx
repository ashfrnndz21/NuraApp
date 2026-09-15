import { useState } from "preact/hooks";
import type { JSX } from "preact";
import * as family from "../../api/family";
import type { Scope } from "../../api/familyTypes";
import { markedParts, ONLY_ME_PARTS } from "../../family/model";
import { Notice, Pill, Tile } from "../../ui/components";
import { FamilyPage, Lines, NoticeAt, s, useAct, useHere, useRead, whose } from "./common";

/** E00-07, E12-04: who looked at what, by day, newest first, as he reads it — every sentence
 *  the backend's, a refused reach included. The owner's and his chief's. */
export function TrailPart(): JSX.Element | null {
  const here = useHere();
  const words = s();
  const days = useRead(here ? () => family.trail(here.bearer, here.papers.profile_id, here.lang) : null, [here?.papers.profile_id, here?.lang]);
  if (!here) return null;
  return (
    <FamilyPage title={whose(here, words.trailSelf, words.trailOther)} part="trail">
      <Notice error={days.error} />
      {days.value?.map((day) => (
        <Tile paper key={day.day} testId="trail-day">
          <h2 class="title">{day.day_words}</h2>
          {day.lines.map((line, at) => (
            <div key={at} class={line.outcome === "refused" ? "trail-line refused" : "trail-line"} data-testid="trail-line">
              <Lines lines={line.sentences} />
            </div>
          ))}
        </Tile>
      ))}
    </FamilyPage>
  );
}

/** E12-04: one part of his record kept to himself, on his yes; every key stops opening it at
 *  once. Opening it again is the same. Only the owner may, and the backend says so to anyone
 *  else, in its words. One part at a time: the list, or the one yes. */
export function OnlyMePart(): JSX.Element | null {
  const here = useHere();
  const words = s();
  const a = useAct();
  const [chosen, setChosen] = useState<Scope | null>(null);
  const marks = useRead(here ? () => family.privacy(here.bearer, here.papers.profile_id) : null, [here?.papers.profile_id]);
  if (!here) return null;
  const marked = markedParts(marks.value ?? []);
  const decide = (part: Scope) =>
    a.act("confirm", async () => {
      const pid = here.papers.profile_id;
      const keep = !marked.has(part);
      const yes = await family.mintOnlyMe(here.bearer, pid, part, keep);
      if (keep) await family.markOnlyMe(here.bearer, pid, part, yes.confirmation_id);
      else await family.liftOnlyMe(here.bearer, pid, part, yes.confirmation_id);
      setChosen(null);
      await marks.reload();
    });
  return (
    <FamilyPage title={words.onlyMe} part="onlyMe">
      <Notice error={marks.error} />
      {chosen ? (
        <Tile paper testId="only-me-confirm">
          <h2 class="title">{words.parts[chosen]}</h2>
          <Pill plum onClick={() => void decide(chosen)} disabled={a.busy} testId="only-me-yes">
            {marked.has(chosen) ? words.onlyMeLift : words.onlyMeYes}
          </Pill>
          <Pill quiet onClick={() => (setChosen(null), a.clear())} testId="only-me-cancel">
            {words.notNow}
          </Pill>
          <NoticeAt act={a} where="confirm" />
        </Tile>
      ) : (
        <Tile paper testId="only-me-parts">
          <p>{words.onlyMeLead}</p>
          <div class="choices" role="group" aria-label={words.onlyMe}>
            {ONLY_ME_PARTS.map((part) => (
              <Pill key={part} pressed={marked.has(part)} chosen={marked.has(part)} onClick={() => setChosen(part)} testId={`only-me-${part}`}>
                {words.parts[part]}
                {marked.has(part) && <span class="chip">{words.onlyMeMarked}</span>}
              </Pill>
            ))}
          </div>
        </Tile>
      )}
    </FamilyPage>
  );
}
