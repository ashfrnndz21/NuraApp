import type { JSX } from "preact";
import { hubEntries } from "../../record/model";
import type { HubEntry, RecordAt } from "../../record/places";
import { density, profile } from "../../store/session";
import { fill, t } from "../../strings";
import { Pill, Tile } from "../../ui/components";
import { ChangesScreen, EpisodeScreen, ProviderScreen, ProvidersScreen, TimelineScreen } from "./Timeline";
import { AddMedicineScreen, MedicinesScreen, MoreScreen, StoryScreen } from "./Medicines";
import { BuilderScreen, RoutineScreen, TrendsScreen } from "./Day";
import { PaperScreen, PapersScreen } from "./Papers";
import { RecordFrame, toRecord } from "./parts";

/** The Record (W5): his medicines, his papers, his day, his visits, his blood tests, his
 *  doctors, what changed and the family's papers — one screen each, over the backend's
 *  routes. Every card's words are the backend's; the catalogue names the screens and buttons. */
export function RecordScreen({ at }: { at: RecordAt }): JSX.Element {
  switch (at.name) {
    case "hub":
      return <Hub />;
    case "medicines":
      return <MedicinesScreen start={at.index ?? 0} />;
    case "story":
      return <StoryScreen lineId={at.lineId} />;
    case "add":
      return <AddMedicineScreen />;
    case "more":
      return <MoreScreen lineId={at.lineId} />;
    case "papers":
      return <PapersScreen />;
    case "paper":
      return <PaperScreen card={at.card} />;
    case "timeline":
      return <TimelineScreen />;
    case "episode":
      return <EpisodeScreen episodeId={at.episodeId} />;
    case "providers":
      return <ProvidersScreen />;
    case "provider":
      return <ProviderScreen providerId={at.providerId} />;
    case "changes":
      return <ChangesScreen />;
    case "trends":
      return <TrendsScreen analyte={at.analyte ?? null} />;
    case "routine":
      return <RoutineScreen />;
    case "builder":
      return <BuilderScreen />;
  }
}

const PLACE: Record<HubEntry, RecordAt> = {
  medicines: { name: "medicines" },
  papers: { name: "papers" },
  routine: { name: "routine" },
  timeline: { name: "timeline" },
  trends: { name: "trends" },
  providers: { name: "providers" },
  changes: { name: "changes" },
};

/** The Record's first screen: one big button a part. In his density his medicines, his
 *  papers and his day come first; a key sees only the parts it opens. */
function Hub(): JSX.Element {
  const s = t();
  const papers = profile.value;
  const entries = hubEntries(density(), papers?.scopes ?? []);
  const title = papers?.standing === "owner" ? s.record.title : fill(s.record.titleOther, { name: papers?.display_name ?? "" });
  return (
    <RecordFrame title={title} testId="record-hub">
      <Tile paper testId="record-entries">
        {entries.map((entry, index) => (
          <Pill key={entry} plum={index === 0 && density() === "patient"} onClick={() => toRecord(PLACE[entry])} testId={`record-${entry}`}>
            {s.record[entry]}
          </Pill>
        ))}
      </Tile>
    </RecordFrame>
  );
}
