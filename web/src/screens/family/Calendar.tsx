import { useState } from "preact/hooks";
import type { JSX } from "preact";
import { Refused } from "../../api/client";
import * as family from "../../api/family";
import type { ProposalOut } from "../../api/familyTypes";
import type { WordingOut } from "../../api/types";
import { base64OfBytes, waiting } from "../../family/model";
import { Notice, Pill, Tile } from "../../ui/components";
import { FamilyPage, Lines, NoticeAt, s, useAct, useHere, useRead, type Here } from "./common";

/** E18-02: a calendar file read once, never kept, never written to; what looks like a visit
 *  becomes a proposal in his words, and only a yes books it — a no books nothing. The owner
 *  agrees to the calendar in the same step, in the backend's words; anyone else is told the
 *  owner has not, in its words. In the patient density, one proposal at a time. */
export function CalendarPart(): JSX.Element | null {
  const here = useHere();
  const words = s();
  const a = useAct();
  const [held, setHeld] = useState<string | null>(null);
  const [agreeTo, setAgreeTo] = useState<WordingOut | null>(null);
  const list = useRead(here ? () => family.proposals(here.bearer, here.papers.profile_id, here.lang) : null, [here?.papers.profile_id, here?.lang]);
  if (!here) return null;
  const pid = here.papers.profile_id;
  const pending = waiting(list.value ?? []);
  const scan = async (connectorId: string, ics: string) => {
    await family.scanCalendar(here.bearer, pid, connectorId, ics, here.lang);
    await list.reload();
  };
  const upload = (file: File) =>
    a.act("file", async () => {
      const ics = base64OfBytes(await file.arrayBuffer());
      let connectorId = list.value?.[0]?.connector_id;
      if (!connectorId) {
        try {
          connectorId = (await family.connectCalendar(here.bearer, pid)).connector_id;
        } catch (failure) {
          // No agreement yet: the owner reads the words and agrees here; anyone else is told.
          if (failure instanceof Refused && failure.refusal === "ConsentWithheld" && here.owner) {
            setHeld(ics);
            setAgreeTo(await family.calendarWording(here.lang));
            return;
          }
          throw failure;
        }
      }
      await scan(connectorId, ics);
    });
  const agree = () =>
    a.act("agree", async () => {
      if (!agreeTo || !held) return;
      const connector = await family.connectCalendar(here.bearer, pid, { wording_version: agreeTo.version, language: agreeTo.language });
      setAgreeTo(null);
      await scan(connector.connector_id, held);
      setHeld(null);
    });
  const shown = here.patient ? pending.slice(0, 1) : pending;
  const chooser = (
    <Tile paper testId="calendar-file">
      <label class="pill" data-testid="choose-ics">
        {words.chooseFile}
        <input
          type="file"
          accept=".ics,text/calendar"
          onChange={(event) => {
            const input = event.target as HTMLInputElement;
            const file = input.files?.[0];
            if (file) void upload(file);
            input.value = "";
          }}
        />
      </label>
      <NoticeAt act={a} where="file" />
    </Tile>
  );
  return (
    <FamilyPage title={words.calendar} part="calendar">
      <Notice error={list.error} />
      {agreeTo ? (
        <Tile paper testId="calendar-consent">
          <Lines lines={agreeTo.lines} />
          <Pill plum onClick={() => void agree()} disabled={a.busy} testId="calendar-agree">
            {words.agree}
          </Pill>
          <Pill quiet onClick={() => (setAgreeTo(null), setHeld(null))} testId="calendar-cancel">
            {words.notNow}
          </Pill>
          <NoticeAt act={a} where="agree" />
        </Tile>
      ) : (
        <>
          {shown.map((proposal) => (
            <ProposalTile key={proposal.proposal_id} proposal={proposal} here={here} act={a} reload={list.reload} />
          ))}
          {(!here.patient || shown.length === 0) && chooser}
        </>
      )}
    </FamilyPage>
  );
}

function ProposalTile({ proposal, here, act, reload }: { proposal: ProposalOut; here: Here; act: ReturnType<typeof useAct>; reload: () => Promise<void> }): JSX.Element {
  const words = s();
  const pid = here.papers.profile_id;
  const yes = () =>
    act.act(proposal.proposal_id, async () => {
      const minted = await family.mintProposal(here.bearer, pid, proposal.proposal_id);
      await family.acceptProposal(here.bearer, pid, proposal.proposal_id, minted.confirmation_id, here.lang);
      await reload();
    });
  const no = () =>
    act.act(proposal.proposal_id, async () => {
      await family.dismissProposal(here.bearer, pid, proposal.proposal_id, here.lang);
      await reload();
    });
  return (
    <Tile paper testId="proposal">
      <Lines lines={proposal.lines} testId="proposal-lines" />
      <Pill plum onClick={() => void yes()} disabled={act.busy} testId="proposal-yes">
        {words.bookYes}
      </Pill>
      <Pill onClick={() => void no()} disabled={act.busy} testId="proposal-no">
        {words.notThis}
      </Pill>
      <NoticeAt act={act} where={proposal.proposal_id} />
    </Tile>
  );
}
