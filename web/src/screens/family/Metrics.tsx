import type { JSX } from "preact";
import * as family from "../../api/family";
import { weekRows } from "../../family/model";
import { fill } from "../../strings";
import { Notice, Tile } from "../../ui/components";
import { FamilyPage, s, useHere, useRead } from "./common";

/** E17-05: the week in numbers — taps, "Fine today" and its share, and each kind of nudge
 *  given, taken up and put aside. Counts only: never his words, never a line from his record.
 *  The owner's and his chief's; the read is on his trail (the backend writes it). */
export function MetricsPart(): JSX.Element | null {
  const here = useHere();
  const words = s();
  const read = useRead(here ? () => family.nudgeMetrics(here.bearer, here.papers.profile_id, 4) : null, [here?.papers.profile_id]);
  if (!here) return null;
  const day = new Intl.DateTimeFormat(here.locale, { day: "numeric", month: "long", timeZone: "UTC" });
  return (
    <FamilyPage title={words.metrics} part="metrics">
      <Notice error={read.error} />
      {read.value &&
        weekRows(read.value).map((week) => (
          <Tile paper key={week.week} testId="metrics-week">
            <h2 class="title">{fill(words.weekOf, { date: day.format(new Date(`${week.startsOn}T00:00:00Z`)) })}</h2>
            <table class="data">
              <tbody>
                <tr>
                  <th>{words.taps}</th>
                  <td data-testid="taps">{week.taps}</td>
                </tr>
                <tr>
                  <th>{words.fineToday}</th>
                  <td data-testid="fine-today">{week.fineToday}</td>
                </tr>
                <tr>
                  <th>{words.fineShare}</th>
                  <td data-testid="fine-share">{week.finePercent ?? "–"}</td>
                </tr>
              </tbody>
            </table>
            {week.kinds.length > 0 && (
              <table class="data" data-testid="nudge-kinds">
                <thead>
                  <tr>
                    <th>{words.kind}</th>
                    <th>{words.handedOver}</th>
                    <th>{words.accepted}</th>
                    <th>{words.dismissed}</th>
                  </tr>
                </thead>
                <tbody>
                  {week.kinds.map((kind) => (
                    <tr key={kind.kind}>
                      <td>{(words.kinds as Record<string, string>)[kind.kind] ?? kind.kind}</td>
                      <td>{kind.handedOver}</td>
                      <td>{kind.accepted}</td>
                      <td>{kind.dismissed}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}
          </Tile>
        ))}
    </FamilyPage>
  );
}
