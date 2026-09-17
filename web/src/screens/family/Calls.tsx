import { useState } from "preact/hooks";
import type { JSX } from "preact";
import * as family from "../../api/family";
import type { CallOut, GrantOut } from "../../api/familyTypes";
import { fromWallInput, toWallInput } from "../../family/model";
import { t } from "../../strings";
import { dateLine, timeLine } from "../../today/model";
import { Field, Notice, Pill, Tile } from "../../ui/components";
import { FamilyPage, NoticeAt, useAct, useHere, useRead, type Here } from "./common";

/** Connect's "Change" (docs/design/nura-concept-board.html, the Connect screen's "Next call"):
 *  every call still ahead of now, from #235's calendar (`family.upcomingCalls`), each with a
 *  way to take it off the calendar; and, for the owner or his chief — the same footing
 *  scheduling a call already stands on (`app.family.calls.call_draft_for`) — a way to put a
 *  new one on it. */
export function CallsPart(): JSX.Element | null {
  const here = useHere();
  const s = t();
  const a = useAct();
  const calls = useRead(here ? () => family.upcomingCalls(here.bearer, here.papers.profile_id, here.lang) : null, [here?.papers.profile_id, here?.lang]);
  const people = useRead(here ? () => family.grants(here.bearer, here.papers.profile_id, here.lang) : null, [here?.papers.profile_id, here?.lang]);
  if (!here) return null;
  const canArrange = here.owner || here.papers.role === "chief";
  const cancel = (call: CallOut) =>
    a.act(call.call_id, async () => {
      await family.cancelCall(here.bearer, here.papers.profile_id, call.call_id, here.lang);
      await calls.reload();
    });
  return (
    <FamilyPage title={s.connect.callsTitle} part="calls">
      <Notice error={calls.error} />
      {(calls.value ?? []).map((call) => (
        <Tile paper key={call.call_id} testId="call-row">
          <h2 class="title">{call.label ?? call.with_person_name}</h2>
          <p class="source-line">
            {dateLine(new Date(call.scheduled_at), here.locale)} · {timeLine(new Date(call.scheduled_at), here.locale)}
          </p>
          {canArrange && (
            <Pill onClick={() => void cancel(call)} disabled={a.busy} testId="cancel-call">
              {s.connect.cancelCallButton}
            </Pill>
          )}
          <NoticeAt act={a} where={call.call_id} />
        </Tile>
      ))}
      {(calls.value ?? []).length === 0 && <Tile paper testId="no-calls">{s.connect.noCall}</Tile>}
      {canArrange && people.value && <NewCall here={here} people={people.value} act={a} reload={calls.reload} />}
    </FamilyPage>
  );
}

type Act = ReturnType<typeof useAct>;

/** Putting a call on the calendar (`app.drafts.CallDraft`): the chief's or his own yes,
 *  recomputed from who, when and the link, exactly as the backend mints it — so a yes cannot
 *  be minted for a stranger or a link nobody was shown. */
function NewCall({ here, people, act, reload }: { here: Here; people: GrantOut[]; act: Act; reload: () => Promise<void> }): JSX.Element {
  const s = t();
  const [who, setWho] = useState<GrantOut | null>(null);
  const [when, setWhen] = useState(toWallInput(Date.now() + 24 * 3_600_000));
  const [link, setLink] = useState("");
  const [callLabel, setCallLabel] = useState("");
  const schedule = () =>
    act.act("new-call", async () => {
      const scheduledAt = fromWallInput(when);
      if (!who || !scheduledAt) return;
      const callLink = link.trim() || null;
      const yes = await family.mintCall(here.bearer, here.papers.profile_id, { with_person_id: who.holder_person_id, scheduled_at: scheduledAt, call_link: callLink });
      await family.scheduleCall(
        here.bearer,
        here.papers.profile_id,
        { with_person_id: who.holder_person_id, scheduled_at: scheduledAt, call_link: callLink, label: callLabel.trim() || null },
        yes.confirmation_id,
        here.lang,
      );
      setWho(null);
      setLink("");
      setCallLabel("");
      await reload();
    });
  return (
    <Tile paper testId="new-call">
      <h2 class="title">{s.connect.scheduleCall}</h2>
      <div class="choices" role="group" aria-label={s.connect.personLabel} data-testid="new-call-who">
        {people.map((grant) => (
          <Pill key={grant.key_id} chosen={who?.holder_person_id === grant.holder_person_id} onClick={() => setWho(grant)} testId={`new-call-who-${grant.holder_name}`}>
            {grant.holder_name}
          </Pill>
        ))}
      </div>
      <Field label={s.connect.whenLabel} type="datetime-local" value={when} onInput={setWhen} name="call-when" />
      <Field label={s.connect.callLabelLabel} value={callLabel} onInput={setCallLabel} name="call-label" maxLength={80} />
      <Field label={s.connect.linkLabel} value={link} onInput={setLink} name="call-link" maxLength={300} />
      <Pill plum onClick={() => void schedule()} disabled={act.busy || !who} testId="schedule-call">
        {s.connect.scheduleCall}
      </Pill>
      <NoticeAt act={act} where="new-call" />
    </Tile>
  );
}
