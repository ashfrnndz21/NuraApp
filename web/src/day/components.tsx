import { useState } from "preact/hooks";
import type { JSX } from "preact";
import type { CardClipOut, FeedItemOut } from "../api/types";
import { fill, t } from "../strings";
import { feedLines, whyLine } from "../today/model";
import { Hear, Notice, Pill, Tile } from "../ui/components";
import { HearClip } from "../ui/Player";
import { clipRef, type CloudView, type NudgeShown } from "./model";

/** The feeling cloud on Today (E17-01): the backend's question, then its words, biggest first.
 *  A tap is the whole action; nothing moves and nothing is read out until he taps Hear. */
export function FeelingStrip({ view, busy, onTap }: { view: CloudView; busy: boolean; onTap: (word: { word: string; red: boolean }) => void }): JSX.Element {
  return (
    <Tile paper testId="feeling-cloud">
      <div class="lines" data-testid="cloud-prompt">
        {view.prompt.map((line, at) => (
          <p key={at}>{line}</p>
        ))}
      </div>
      <div class="cloud feelings" role="group" aria-label={view.prompt[view.prompt.length - 1] ?? ""}>
        {view.words.map((one) => (
          <button
            key={one.word}
            type="button"
            class={`word s${one.size}`}
            data-testid="feeling-word"
            data-word={one.word}
            disabled={busy}
            onClick={() => onTap(one)}
          >
            {one.label}
          </button>
        ))}
      </div>
      <Hear lines={view.prompt} />
    </Tile>
  );
}

/** The day's nudge (E11-07, E17-03) where the backend plans it: its lines, its why under them,
 *  the one action and "Not today" beside it — two visible buttons, never a swipe. */
export function NudgeTile({ shown, busy, onAnswer }: { shown: NudgeShown; busy: boolean; onAnswer: (kind: "accepted" | "dismissed") => void }): JSX.Element {
  const s = t();
  const accept = shown.kind === "commitment" ? s.day.nudgeWentWell : s.day.nudgeOk;
  return (
    <Tile paper testId="nudge">
      <div class="lines" data-testid="nudge-lines">
        {shown.lines.map((line, at) => (
          <p key={at}>{line}</p>
        ))}
      </div>
      <p class="provenance" data-testid="nudge-why">
        {shown.why}
      </p>
      <Pill plum onClick={() => onAnswer("accepted")} disabled={busy} testId="nudge-accept">
        {accept}
      </Pill>
      <Pill onClick={() => onAnswer("dismissed")} disabled={busy} testId="nudge-dismiss">
        {s.day.nudgeNotToday}
      </Pill>
      <Hear lines={shown.spoken} />
    </Tile>
  );
}

/** "Hear what Dr Tan said" under one line of a card (E21-03, E03-05): that stretch alone, on a
 *  tap, through the one player (E15-07, `ui/Player.tsx`'s `HearClip`) — its controls and the
 *  card's own line as the transcript while it plays. A recording this key may not hear
 *  (`OnlyTheFamilyHears`, 403) shows the refusal's sentence in place of the button, never an
 *  empty player; any other failure is said under it. */
export function ClipButton({ clip, playKey }: { clip: CardClipOut; playKey: string }): JSX.Element {
  const s = t();
  const [failed, setFailed] = useState<unknown>(null);
  return (
    <div class="clip" data-testid="clip">
      <HearClip name={playKey} clip={clipRef(clip)} line={clip.line} label={fill(s.visit.hearClip, { doctor: clip.doctor })} onError={setFailed} />
      <Notice error={failed} />
    </div>
  );
}

/** A feed card whose lines were said at a recorded visit (the memo card): each line, and under
 *  it the stretch it was said in; the boundary last; its why; its spoken twin. */
export function ClipCard({ item, clips, paper, testId }: { item: FeedItemOut; clips: Map<string, CardClipOut>; paper: boolean; testId: string }): JSX.Element {
  const shown = feedLines(item);
  const why = whyLine(item);
  return (
    <Tile paper={paper} glass={!paper} testId={testId}>
      {item.headline && <h2 class="title">{item.headline}</h2>}
      <div class="lines">
        {shown.lines.map((line, at) => {
          const clip = clips.get(line);
          return (
            <div key={at} class="clip-line" data-testid="card-line">
              <p>{line}</p>
              {clip && <ClipButton clip={clip} playKey={`${item.item_id}:${at}`} />}
            </div>
          );
        })}
      </div>
      {shown.boundary.length > 0 && (
        <div class="lines boundary" data-testid="boundary">
          {shown.boundary.map((line, at) => (
            <p key={at}>{line}</p>
          ))}
        </div>
      )}
      {why && <p class="provenance">{why}</p>}
      <Hear lines={item.voice.length > 0 ? item.voice : [item.headline, ...shown.lines, ...shown.boundary].filter(Boolean)} />
    </Tile>
  );
}
