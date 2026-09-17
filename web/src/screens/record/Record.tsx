import type { JSX } from "preact";
import { Icon, type IconName } from "../../ui/kit/icons";
import { hubEntries } from "../../record/model";
import type { HubEntry, RecordAt } from "../../record/places";
import { density, profile } from "../../store/session";
import { fill, t } from "../../strings";
import { Tile } from "../../ui/components";
import { ChangesScreen, EpisodeScreen, ProviderScreen, ProvidersScreen, TimelineScreen } from "./Timeline";
import { AddMedicineScreen, MedicinesScreen, MoreScreen, StoryScreen } from "./Medicines";
import { BuilderScreen, RoutineScreen, TrendsScreen } from "./Day";
import { LedgerScreen } from "./Ledger";
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
      return <ProvidersScreen category={at.category} />;
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
    case "ledger":
      return <LedgerScreen />;
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
  ledger: { name: "ledger" },
};

/** The Record's first screen: one big button a part. In his density his medicines, his
 *  papers and his day come first; a key sees only the parts it opens. */
/** Each place's icon, always beside its word. */
const PLACE_ICON: Partial<Record<string, IconName>> = {
  medicines: "medicines",
  papers: "records",
  routine: "today",
  timeline: "visits",
  trends: "records",
  providers: "visits",
  changes: "note",
  ledger: "ledger",
};

function Hub(): JSX.Element {
  const s = t();
  const papers = profile.value;
  const entries = hubEntries(density(), papers?.scopes ?? []);
  const title = papers?.standing === "owner" ? s.record.title : fill(s.record.titleOther, { name: papers?.display_name ?? "" });
  return (
    <RecordFrame title={title} testId="record-hub">
      <Tile paper testId="record-entries">
        <nav class="place-rows" aria-label={title}>
          {entries.map((entry) => (
            <button key={entry} type="button" class="place-row" onClick={() => toRecord(PLACE[entry])} data-testid={`record-${entry}`}>
              <Icon name={PLACE_ICON[entry] ?? "records"} />
              <span class="place-word">{s.record[entry]}</span>
              <Icon name="chevron" />
            </button>
          ))}
        </nav>
      </Tile>
    </RecordFrame>
  );
}
