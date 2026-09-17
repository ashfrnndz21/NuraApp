import { useState } from "preact/hooks";
import type { JSX } from "preact";
import * as family from "../../api/family";
import type { FamilyPart } from "../../flow";
import { go } from "../../flow";
import { fill, t } from "../../strings";
import { Notice, Pill, Tile } from "../../ui/components";
import { Icon, type IconName, PaperTile, PillButton } from "../../ui/kit";
import { CalendarPart } from "./Calendar";
import { CallsPart } from "./Calls";
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
    case "calls":
      return <CallsPart />;
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
  const callsWord = t().connect.callsTitle;
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
  // Each part as a row: an icon, the word, the way in. One tap from the Family tab, which is
  // two from anywhere — the most any feature is allowed to be.
  const row = (part: FamilyPart, label: string, icon: IconName) => (
    <button key={part} type="button" class="place-row" onClick={open(part)} data-testid={`open-${part}`}>
      <Icon name={icon} />
      <span class="place-word">{label}</span>
      <Icon name="chevron" />
    </button>
  );
  // Gated on who he is (standing), not how dense his screen reads (density, his own toggle,
  // Me.tsx): the roster names his medicines by their box, so an owner who switches to the
  // caregiver density for the bigger-print layout must not thereby unlock it (#166 review).
  const parts = here.owner
    ? [
        row("trail", whose(here, words.trailSelf, words.trailOther), "note"),
        row("onlyMe", words.onlyMe, "records"),
        row("consents", whose(here, words.consentsSelf, words.consentsOther), "note"),
        row("thread", words.thread, "family"),
        row("calendar", words.calendar, "visits"),
        row("calls", callsWord, "phone"),
      ]
    : [
        row("trail", whose(here, words.trailSelf, words.trailOther), "note"),
        row("roster", words.roster, "family"),
        row("thread", words.thread, "family"),
        row("messages", fill(words.messagesTitle, { name: here.papers.display_name }), "speaker"),
        row("metrics", words.metrics, "records"),
        row("calendar", words.calendar, "visits"),
        row("calls", callsWord, "phone"),
        row("deliveries", words.deliveries, "note"),
        row("settings", words.settings, "plan"),
        row("documents", words.documents, "records"),
        row("consents", whose(here, words.consentsSelf, words.consentsOther), "note"),
        row("onlyMe", words.onlyMe, "records"),
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
      <PaperTile testId="circle">
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
        {/* Letting someone in is what this screen is for, so it is the one Plum button on it and
            it sits with the circle it changes, rather than a row in a list of settings. Both the
            owner and his chief reach it; what differs is inside, where `KeysPart` shows the
            owner the sharing words to agree to first, because that yes is his alone
            (`may_invite`, #166 review). The moment a key is cut, that person's app reaches these
            papers and can ask about them, within what the key opens. */}
        <PillButton variant="primary" onClick={open("keys")} testId="open-keys">
          {words.newKey}
        </PillButton>
      </PaperTile>
      <nav class="place-rows" aria-label={words.title}>
        {parts}
      </nav>
    </FamilyPage>
  );
}
