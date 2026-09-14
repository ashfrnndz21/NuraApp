import type { JSX } from "preact";
import * as family from "../../api/family";
import type { FamilyPart } from "../../flow";
import { go } from "../../flow";
import { Notice, Pill, Tile } from "../../ui/components";
import { CalendarPart } from "./Calendar";
import { FamilyPage, Lines, s, useHere, useRead, whose } from "./common";
import { ConsentsPart, RecordPart } from "./Consents";
import { KeysPart } from "./Keys";
import { MessagesPart } from "./Messages";
import { MetricsPart } from "./Metrics";
import { RosterPart } from "./Roster";
import { ThreadPart } from "./Thread";
import { OnlyMePart, TrailPart } from "./Trail";

/** Family (W6): the web half of E12, E00-02, E00-07, E17-05 and E18-02. */
export function FamilyScreen({ part }: { part: FamilyPart }): JSX.Element | null {
  switch (part) {
    case "home":
      return <FamilyHome />;
    case "keys":
      return <KeysPart />;
    case "trail":
      return <TrailPart />;
    case "onlyMe":
      return <OnlyMePart />;
    case "consents":
      return <ConsentsPart />;
    case "record":
      return <RecordPart />;
    case "thread":
      return <ThreadPart />;
    case "roster":
      return <RosterPart />;
    case "messages":
      return <MessagesPart />;
    case "metrics":
      return <MetricsPart />;
    case "calendar":
      return <CalendarPart />;
  }
}

/** Who is in his circle, in the backend's words, and then the way to each part. In the
 *  patient density that is his circle, his trail, what he keeps to himself, what he said yes
 *  to, the family's messages and a visit from a calendar; the chief's arrangements (the keys,
 *  the roster, messages to him, the week's numbers) are in the caregiver density. Whether a
 *  person may open a part is the backend's to say, in its words, when they open it. */
function FamilyHome(): JSX.Element | null {
  const here = useHere();
  const words = s();
  const circle = useRead(here ? () => family.grants(here.bearer, here.papers.profile_id, here.lang) : null, [here?.papers.profile_id, here?.lang]);
  if (!here) return null;
  const open = (part: FamilyPart) => () => go({ name: "family", part });
  const pill = (part: FamilyPart, label: string) => (
    <Pill key={part} onClick={open(part)} testId={`open-${part}`}>
      {label}
    </Pill>
  );
  const parts = here.patient
    ? [
        pill("trail", whose(here, words.trailSelf, words.trailOther)),
        pill("onlyMe", words.onlyMe),
        pill("consents", whose(here, words.consentsSelf, words.consentsOther)),
        pill("thread", words.thread),
        pill("calendar", words.calendar),
      ]
    : [
        pill("trail", whose(here, words.trailSelf, words.trailOther)),
        pill("keys", words.keys),
        pill("roster", words.roster),
        pill("thread", words.thread),
        pill("messages", whose(here, words.messagesTitle.replace("{name}", here.papers.display_name), words.messagesTitle)),
        pill("metrics", words.metrics),
        pill("calendar", words.calendar),
        pill("consents", whose(here, words.consentsSelf, words.consentsOther)),
        pill("onlyMe", words.onlyMe),
      ];
  return (
    <FamilyPage title={words.title} part="home">
      <Tile paper testId="circle">
        <h2 class="title">{whose(here, words.circleSelf, words.circleOther)}</h2>
        {circle.value?.map((grant) => (
          <Lines key={grant.key_id} lines={grant.lines} testId="grant-lines" />
        ))}
        <Notice error={circle.error} />
      </Tile>
      {parts}
    </FamilyPage>
  );
}
