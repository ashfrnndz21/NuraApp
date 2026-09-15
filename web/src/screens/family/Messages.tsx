import { useState } from "preact/hooks";
import type { JSX } from "preact";
import * as family from "../../api/family";
import type { PushCompose, PushPreviewOut } from "../../api/familyTypes";
import { fromWallInput, pushWindow, TEMPLATES, wallTime } from "../../family/model";
import { me } from "../../store/session";
import { fill, LANGUAGES, t, type Language } from "../../strings";
import { Field, Notice, Pill, Tile } from "../../ui/components";
import { FamilyPage, Lines, NoticeAt, s, useAct, useHere, useRead } from "./common";

/** E12-06: a message to him — one of the backend's templates with its slots, or the chief's
 *  own lines — previewed exactly as he will see it, in his language or another, then put on
 *  the calendar on her yes for exactly those lines. The delivery engine (E11) sends it at a
 *  moment his State allows between the two times; the list says what became of each, in the
 *  delivery log's word. Nothing here sends. */
export function MessagesPart(): JSX.Element | null {
  const here = useHere();
  const words = s();
  const a = useAct();
  const [kind, setKind] = useState<string>("pickup");
  const [slots, setSlots] = useState<Record<string, string>>({ who: me.value?.display_name ?? "" });
  const [memo, setMemo] = useState("");
  const [lang, setLang] = useState<Language>((here?.papers.language as Language) ?? "en");
  const [shown, setShown] = useState<PushPreviewOut | null>(null);
  const window0 = pushWindow(Date.now());
  const [sendAt, setSendAt] = useState(window0.sendAt);
  const [until, setUntil] = useState(window0.expiresAt);
  const [channel, setChannel] = useState<"app" | "whatsapp">("whatsapp");
  const list = useRead(here ? () => family.pushes(here.bearer, here.papers.profile_id) : null, [here?.papers.profile_id]);
  if (!here) return null;
  const template = TEMPLATES.find((each) => each.id === kind);
  const compose = (): PushCompose =>
    template
      ? { template_id: template.id, slots: Object.fromEntries(template.slots.map((slot) => [slot, slots[slot] ?? ""])), language: lang }
      : { memo_lines: memo.split("\n").map((line) => line.trim()).filter(Boolean), language: lang };
  // The yes binds to the lines shown: any change takes the preview away.
  const changed =
    <T,>(set: (value: T) => void) =>
    (value: T) => {
      set(value);
      setShown(null);
    };
  const preview = () => a.act("preview", async () => setShown(await family.previewPush(here.bearer, here.papers.profile_id, compose())));
  const schedule = () =>
    a.act("schedule", async () => {
      const send_at = fromWallInput(sendAt);
      const expires_at = fromWallInput(until);
      if (!send_at || !expires_at) return;
      const when = { send_at, expires_at, channel };
      const yes = await family.mintPush(here.bearer, here.papers.profile_id, compose(), when);
      await family.schedulePush(here.bearer, here.papers.profile_id, compose(), when, yes.confirmation_id);
      setShown(null);
      await list.reload();
    });
  const names: Record<Language, string> = { en: t().me.en, ms: t().me.ms, zh: t().me.zh };
  return (
    <FamilyPage title={fill(words.messagesTitle, { name: here.papers.display_name })} part="messages">
      <Tile paper testId="compose">
        <div class="choices" role="group" data-testid="message-kind">
          {TEMPLATES.map((each) => (
            <Pill key={each.id} chosen={kind === each.id} onClick={() => changed(setKind)(each.id)} testId={`template-${each.id}`}>
              {words.templates[each.id as keyof typeof words.templates]}
            </Pill>
          ))}
          <Pill chosen={kind === "memo"} onClick={() => changed(setKind)("memo")} testId="template-memo">
            {words.ownWords}
          </Pill>
        </div>
        {template?.slots.map((slot) => (
          <Field key={slot} name={`slot-${slot}`} label={words.slots[slot]} value={slots[slot] ?? ""} onInput={(value) => changed(setSlots)({ ...slots, [slot]: value })} />
        ))}
        {!template && (
          <label class="by-hand-label">
            <span class="label">{words.memoLabel}</span>
            <textarea class="field" name="memo" rows={4} value={memo} onInput={(event) => changed(setMemo)((event.target as HTMLTextAreaElement).value)} />
          </label>
        )}
        <p class="label">{words.languageLabel}</p>
        <div class="choices" role="group" aria-label={words.languageLabel}>
          {LANGUAGES.map((code) => (
            <Pill key={code} chosen={lang === code} onClick={() => changed(setLang)(code)} testId={`message-lang-${code}`}>
              {names[code]}
            </Pill>
          ))}
        </div>
        <Pill onClick={() => void preview()} disabled={a.busy} testId="preview-message">
          {words.preview}
        </Pill>
        <NoticeAt act={a} where="preview" />
      </Tile>
      {shown && (
        <Tile paper testId="message-preview">
          <Lines lines={shown.lines} testId="preview-lines" />
          <div class="row">
            <Field name="send-at" label={words.sendAt} value={sendAt} onInput={setSendAt} type="datetime-local" />
            <Field name="until" label={words.until} value={until} onInput={setUntil} type="datetime-local" />
          </div>
          <div class="choices" role="group">
            <Pill chosen={channel === "whatsapp"} onClick={() => setChannel("whatsapp")} testId="channel-whatsapp">
              {words.channelWhatsapp}
            </Pill>
            <Pill chosen={channel === "app"} onClick={() => setChannel("app")} testId="channel-app">
              {words.channelApp}
            </Pill>
          </div>
          <Pill plum onClick={() => void schedule()} disabled={a.busy} testId="schedule-message">
            {words.schedule}
          </Pill>
          <NoticeAt act={a} where="schedule" />
        </Tile>
      )}
      <Notice error={list.error} />
      {list.value?.map((push) => (
        <Tile paper key={push.push_id} testId="scheduled-message">
          <Lines lines={push.lines} />
          <p class="label" data-testid="message-state" data-state={push.state}>
            {words.states[push.state]} · {wallTime(push.sent_at ?? push.send_at, here.locale)}
          </p>
        </Tile>
      ))}
    </FamilyPage>
  );
}
