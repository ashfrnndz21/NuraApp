import { useState } from "preact/hooks";
import type { JSX } from "preact";
import * as family from "../../api/family";
import { digestView, startOfHisDay } from "../../family/model";
import { Notice, Pill, Tile } from "../../ui/components";
import { FamilyPage, Lines, NoticeAt, s, useAct, useHere, useRead } from "./common";

/** E12-02: the family thread as the caller's digest for his day — whole sentences the backend
 *  wrote, narrowed to the caller's key, with each family member's own words under their line —
 *  a day further back on a tap, and one short message to the family. Not a stream. */
export function ThreadPart(): JSX.Element | null {
  const here = useHere();
  const words = s();
  const a = useAct();
  const [back, setBack] = useState(0);
  const [text, setText] = useState("");
  const since = startOfHisDay(Date.now(), back);
  const read = useRead(here ? () => family.digest(here.bearer, here.papers.profile_id, since, here.lang) : null, [here?.papers.profile_id, here?.lang, back]);
  if (!here) return null;
  const view = read.value ? digestView(read.value) : null;
  const send = () =>
    a.act("post", async () => {
      await family.postMessage(here.bearer, here.papers.profile_id, text.trim());
      setText("");
      await read.reload();
    });
  return (
    <FamilyPage title={words.thread} part="thread">
      <Notice error={read.error} />
      {view && (
        <Tile paper testId="digest">
          <h2 class="title">{view.headline}</h2>
          {view.entries.map((entry, at) => (
            <div key={at} class="entry" data-testid="digest-entry">
              <Lines lines={entry.lines} />
              {entry.text && <blockquote class="family-words">{entry.text}</blockquote>}
            </div>
          ))}
          <Lines lines={view.closing} testId="digest-closing" />
        </Tile>
      )}
      {view && (
        <Pill quiet onClick={() => setBack(back + 1)} testId="thread-earlier">
          {words.threadEarlier}
        </Pill>
      )}
      <Tile paper testId="thread-post">
        <label class="by-hand-label">
          <span class="label">{words.messageLabel}</span>
          <textarea class="field" name="family-message" maxLength={280} rows={3} value={text} onInput={(event) => setText((event.target as HTMLTextAreaElement).value)} />
        </label>
        <Pill plum onClick={() => void send()} disabled={a.busy || !text.trim()} testId="send-message">
          {a.busy ? words.sendingMessage : words.sendMessage}
        </Pill>
        <p class="sr-only" aria-live="polite">
          {a.busy ? words.sendingMessage : ""}
        </p>
        <NoticeAt act={a} where="post" />
      </Tile>
    </FamilyPage>
  );
}
