import { useState } from "preact/hooks";
import type { JSX } from "preact";
import * as family from "../../api/family";
import type { FamilyPart } from "../../flow";
import { go } from "../../flow";
import { fill } from "../../strings";
import { Notice, Pill, Tile } from "../../ui/components";
import { CalendarPart } from "./Calendar";
import { FamilyPage, Lines, NoticeAt, s, useAct, useHere, useRead, whose } from "./common";
import { ConsentsPart, RecordPart } from "./Consents";
import { DeliveriesPart, SettingsPart } from "./Delivery";
import { DocumentsPart } from "./Documents";
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
    case "deliveries":
      return <DeliveriesPart />;
    case "settings":
      return <SettingsPart />;
    case "documents":
      return <DocumentsPart />;
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
  // A red flag still climbing that reached this person (E11-06). A key without the emergency
  // card reaches no ladder, so there is nothing to show it: the read's no is not a screen.
  const asks = useRead(here ? () => family.ladders(here.bearer, here.papers.profile_id, here.lang).catch(() => []) : null, [here?.papers.profile_id, here?.lang]);
  // Who Nura cannot message on WhatsApp (#163): the owner's and his chief's to see. Anyone
  // else is refused it, and that no is not a screen either.
  const reach = useRead(here && !here.patient ? () => family.reach(here.bearer, here.papers.profile_id, here.lang).catch(() => []) : null, [here?.papers.profile_id, here?.lang, here?.patient]);
  const [answered, setAnswered] = useState<string[] | null>(null);
  const a = useAct();
  if (!here) return null;
  const onIt = (ladderId: string) =>
    a.act(ladderId, async () => {
      const done = await family.acknowledge(here.bearer, here.papers.profile_id, ladderId, here.lang);
      setAnswered(done.lines);
      await asks.reload();
    });
  const open = (part: FamilyPart) => () => go({ name: "family", part });
  const pill = (part: FamilyPart, label: string) => (
    <Pill key={part} onClick={open(part)} testId={`open-${part}`}>
      {label}
    </Pill>
  );
  const parts = here.patient
    ? [
        pill("trail", whose(here, words.trailSelf, words.trailOther)),
        // The owner's own selection to add and grant access to someone (E12): letting
        // someone in at all is his own yes (`may_invite`), so only he — never his chief —
        // sees it here; `KeysPart` reads `here.owner` to show him the words first.
        pill("keys", words.keys),
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
        pill("messages", fill(words.messagesTitle, { name: here.papers.display_name })),
        pill("metrics", words.metrics),
        pill("calendar", words.calendar),
        pill("deliveries", words.deliveries),
        pill("settings", words.settings),
        pill("documents", words.documents),
        pill("consents", whose(here, words.consentsSelf, words.consentsOther)),
        pill("onlyMe", words.onlyMe),
      ];
  return (
    <FamilyPage title={words.title} part="home">
      {asks.value?.map((ladder) => (
        <Tile paper key={ladder.ladder_id} testId="ladder">
          <Lines lines={ladder.lines} testId="ladder-lines" />
          {(ladder.not_reached ?? []).length > 0 && <Lines lines={ladder.not_reached ?? []} testId="ladder-not-reached" />}
          <Pill plum onClick={() => void onIt(ladder.ladder_id)} disabled={a.busy} testId="on-it">
            {words.ladderYes}
          </Pill>
          <NoticeAt act={a} where={ladder.ladder_id} />
        </Tile>
      ))}
      {answered && (
        <Tile paper role="status" testId="ladder-answered">
          <Lines lines={answered} />
        </Tile>
      )}
      <Tile paper testId="circle">
        <h2 class="title">{whose(here, words.circleSelf, words.circleOther)}</h2>
        {circle.value?.map((grant) => (
          <Lines key={grant.key_id} lines={grant.lines} testId="grant-lines" />
        ))}
        {reach.value
          ?.filter((one) => one.lines.length > 0)
          .map((one) => (
            <Lines key={one.person_id} lines={one.lines} testId="reach-lines" />
          ))}
        <Notice error={circle.error} />
      </Tile>
      {parts}
    </FamilyPage>
  );
}
