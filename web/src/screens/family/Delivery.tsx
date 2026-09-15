import { useEffect, useState } from "preact/hooks";
import type { JSX } from "preact";
import * as family from "../../api/family";
import type { DeliverySettingsOut } from "../../api/familyTypes";
import { hhmm, namesOf, wallTime } from "../../family/model";
import { fill } from "../../strings";
import { Field, Notice, Pill, Tile } from "../../ui/components";
import { FamilyPage, NoticeAt, s, useAct, useHere, useRead } from "./common";

const CHANNELS = ["app_push", "whatsapp", "caregiver"] as const;

/** The engine's reasons for a message the check-in and the family notice held (E11-01,
 *  `backend/app/delivery/triggers/day.py`), to the line the log says instead of the outcome. */
const HELD_BECAUSE: Record<string, "flagOpen" | "saidToday" | "nudgeAsked" | "questionOpen"> = {
  "a red flag is open": "flagOpen",
  "he said how he is today": "saidToday",
  "the check-in nudge asked it": "nudgeAsked",
  "a question of his is open": "questionOpen",
};

/** E00-05: every attempt to reach someone about him — to whom, when, by which channel, what
 *  became of it, and the rule that fired — newest first, from the delivery log (#121). Data,
 *  not sentences: the labels are the screen's, the rows the backend's. Owner and chief. */
export function DeliveriesPart(): JSX.Element | null {
  const here = useHere();
  const words = s();
  const pid = here?.papers.profile_id;
  const rows = useRead(here ? () => family.deliveries(here.bearer, here.papers.profile_id) : null, [pid]);
  const people = useRead(here ? () => family.grants(here.bearer, here.papers.profile_id, here.lang).catch(() => []) : null, [pid, here?.lang]);
  if (!here) return null;
  const names = namesOf(people.value ?? []);
  const who = (personId: string | null, standing: string | null) => (standing === "patient" ? here.papers.display_name : (personId && names.get(personId)) || "");
  const label = <T extends Record<string, string>>(table: T, key: string | null) => (key && (table as Record<string, string>)[key]) || key || "";
  // A message held for a reason other than a quiet day says why (E11-01): a red flag open, he
  // already said how he is, the day's small reminder asked it.
  const outcome = (row: { outcome: string; reason: string | null }) => {
    const held = row.outcome === "skipped" && row.reason ? HELD_BECAUSE[row.reason] : undefined;
    return held ? fill(words.skippedBecause[held], { name: here.papers.display_name }) : label(words.outcomes, row.outcome);
  };
  return (
    <FamilyPage title={words.deliveries} part="deliveries">
      <Notice error={rows.error} />
      {rows.value && rows.value.length > 0 && (
        <Tile paper testId="deliveries">
          {rows.value.map((row) => (
            <div key={row.delivery_id} class="entry" data-testid="delivery" data-outcome={row.outcome}>
              <p class="label">
                {wallTime(row.recorded_at, here.locale)} · {who(row.to_person_id, row.standing)} · {label(words.channels, row.channel)}
              </p>
              <p>
                {label(words.triggers, row.trigger_type)} · {outcome(row)}
              </p>
              <p class="caption">
                {words.rule}: {row.rule}
              </p>
            </div>
          ))}
        </Tile>
      )}
    </FamilyPage>
  );
}

/** E11-05: the quiet hours, whether a quiet day skips the morning card, and per kind of
 *  message the channels in the order they are tried and how many a day. An alert is never
 *  held; the backend refuses a cap on one, in its words. Anyone with a key reads; the owner
 *  and his chief change. */
export function SettingsPart(): JSX.Element | null {
  const here = useHere();
  const words = s();
  const a = useAct();
  const read = useRead(here ? () => family.deliverySettings(here.bearer, here.papers.profile_id) : null, [here?.papers.profile_id]);
  const [draft, setDraft] = useState<DeliverySettingsOut | null>(null);
  useEffect(() => {
    if (read.value) setDraft(read.value);
  }, [read.value]);
  if (!here) return null;
  const toggle = (type: string, channel: string) => {
    if (!draft) return;
    const now = draft.channels[type] ?? [];
    const next = now.includes(channel) ? now.filter((each) => each !== channel) : CHANNELS.filter((each) => each === channel || now.includes(each));
    setDraft({ ...draft, channels: { ...draft.channels, [type]: next } });
  };
  const save = () =>
    a.act("save", async () => {
      if (!draft) return;
      const caps = Object.fromEntries(Object.entries(draft.caps).filter((entry): entry is [string, number] => entry[1] !== null));
      setDraft(
        await family.changeDeliverySettings(here.bearer, here.papers.profile_id, {
          skip_quiet_days: draft.skip_quiet_days,
          quiet_from: `${hhmm(draft.quiet_from)}:00`,
          quiet_until: `${hhmm(draft.quiet_until)}:00`,
          channels: draft.channels,
          caps,
        }),
      );
    });
  return (
    <FamilyPage title={words.settings} part="settings">
      <Notice error={read.error} />
      {draft && (
        <>
          <Tile paper testId="quiet-hours">
            <div class="row">
              <Field name="quiet-from" label={words.quietFrom} value={hhmm(draft.quiet_from)} onInput={(value) => setDraft({ ...draft, quiet_from: value })} type="time" />
              <Field name="quiet-until" label={words.quietUntil} value={hhmm(draft.quiet_until)} onInput={(value) => setDraft({ ...draft, quiet_until: value })} type="time" />
            </div>
            <label class="check">
              <input type="checkbox" checked={draft.skip_quiet_days} onChange={(event) => setDraft({ ...draft, skip_quiet_days: (event.target as HTMLInputElement).checked })} />
              <span>{words.skipQuietDays}</span>
            </label>
          </Tile>
          {Object.keys(draft.channels).map((type) => (
            <Tile paper key={type} testId={`kind-${type}`}>
              <h2 class="title">{(words.triggers as Record<string, string>)[type] ?? type}</h2>
              <div class="choices" role="group">
                {CHANNELS.map((channel) => (
                  <Pill key={channel} chosen={(draft.channels[type] ?? []).includes(channel)} onClick={() => toggle(type, channel)} testId={`channel-${type}-${channel}`}>
                    {words.channels[channel]}
                  </Pill>
                ))}
              </div>
              {draft.caps[type] === null ? (
                <p class="label">{words.neverHeld}</p>
              ) : (
                <Field
                  name={`cap-${type}`}
                  label={words.cap}
                  value={String(draft.caps[type] ?? "")}
                  onInput={(value) => setDraft({ ...draft, caps: { ...draft.caps, [type]: Math.max(0, Number.parseInt(value, 10) || 0) } })}
                  type="number"
                  inputMode="numeric"
                />
              )}
            </Tile>
          ))}
          <Pill plum onClick={() => void save()} disabled={a.busy} testId="save-settings">
            {words.saveSettings}
          </Pill>
          <NoticeAt act={a} where="save" />
        </>
      )}
    </FamilyPage>
  );
}
