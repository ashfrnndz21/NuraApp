import { useEffect, useState } from "preact/hooks";
import type { JSX } from "preact";
import { Refused } from "../api/client";
import * as nura from "../api/nura";
import type { StoryOut } from "../api/types";
import { SPEEDS, type ClipRef, type Speed } from "../player/player";
import { storyParts } from "../player/story";
import { voice } from "../player/voice";
import { profile, token } from "../store/session";
import { fill, language, refusalLines, t } from "../strings";
import { Notice, Pill } from "./components";

/** The player's controls (E15-07), under whatever is being heard: one big Play / Pause, his
 *  speed as three plain choices, and the transcript — the line being said — in his body size.
 *  Shown only for the source that is open (`voice.key`); nothing here starts by itself. */
export function PlayerControls(): JSX.Element {
  const s = t().player;
  const status = voice.status.value;
  const going = status === "playing" || status === "loading";
  const words: Record<Speed, string> = { 0.75: s.slower, 1: s.usual, 1.25: s.faster };
  return (
    <div class="player" data-testid="player" data-status={status}>
      <button type="button" class="pill player-toggle" onClick={() => voice.toggle()} disabled={status === "loading"} data-testid="player-toggle">
        <svg viewBox="0 0 24 24" aria-hidden="true">
          {going ? <path d="M7 5h3.5v14H7zM13.5 5H17v14h-3.5z" /> : <path d="M7 4.5v15l12-7.5z" />}
        </svg>
        {going ? s.pause : s.play}
      </button>
      <div class="player-speeds" role="group" aria-label={s.speed}>
        {SPEEDS.map((speed) => (
          <button
            key={speed}
            type="button"
            class={voice.rate.value === speed ? "pill chosen" : "pill"}
            aria-pressed={voice.rate.value === speed}
            onClick={() => voice.setRate(speed)}
            data-testid={`speed-${speed}`}
          >
            {words[speed]}
          </button>
        ))}
      </div>
      {voice.line.value && (
        <p class="player-line" data-testid="player-line">
          {voice.line.value}
        </p>
      )}
      {voice.more.value && status !== "playing" && status !== "loading" && (
        <Pill onClick={() => void voice.nextPart().catch(() => undefined)} testId="player-next">
          {s.nextPart}
        </Pill>
      )}
    </div>
  );
}

/** A medicine's story, said in parts (E04-06), on a tap: the parts in order, each stopping at
 *  its end, *Next part* for the next — never the next by itself. The story and each part's voice
 *  note are fetched (never played) when this is shown, so the tap plays at once; a part with no
 *  voice note is said by the phone's own voice. The hook for the medicines screen (W5). */
export function HearStory({ lineId }: { lineId: string }): JSX.Element | null {
  const s = t();
  const key = `story:${lineId}`;
  const [story, setStory] = useState<StoryOut | null>(null);
  const [audio, setAudio] = useState<ReadonlyMap<string, Blob | null>>(new Map());
  const [failed, setFailed] = useState<unknown>(null);
  const bearer = token.value;
  const papers = profile.value;
  useEffect(() => {
    if (!bearer || !papers) return;
    let live = true;
    void (async () => {
      try {
        const told = await nura.story(bearer, papers.profile_id, lineId, language.value);
        if (!live) return;
        setStory(told);
        const found = new Map<string, Blob | null>();
        for (const part of told.voice_parts) {
          try {
            found.set(part, await nura.storyVoice(bearer, papers.profile_id, lineId, part, language.value));
          } catch (failure) {
            if (!(failure instanceof Refused && failure.status === 404)) throw failure;
            found.set(part, null); // no voice note for this part: the phone says its words
          }
        }
        if (live) setAudio(found);
      } catch (failure) {
        if (live) setFailed(failure);
      }
    })();
    return () => {
      live = false;
      voice.leave(key);
    };
  }, [bearer, papers?.profile_id, lineId, language.value]);
  if (!story) return <Notice error={failed} />;
  return (
    <>
      <Pill quiet onClick={() => void voice.playParts(key, storyParts(story, language.value, audio)).catch(setFailed)} testId="hear-story">
        {fill(s.player.hearStory, { name: story.name })}
      </Pill>
      {voice.key.value === key && <PlayerControls />}
      <Notice error={failed} />
    </>
  );
}

interface HearClipProps {
  /** Where this clip's controls belong: unique on the screen. */
  name: string;
  clip: ClipRef;
  /** The line the clip is the words of: the transcript under the controls. */
  line: string;
  label: string;
  onError: (failure: unknown) => void;
}

/** "Hear what Dr Tan said" under a line that cites a visit's recording, and the player under
 *  it once tapped. A recording this key may not hear (`OnlyTheFamilyHears`) shows the refusal's
 *  sentence instead, and no player. */
export function HearClip({ name, clip, line, label, onError }: HearClipProps): JSX.Element {
  const refusal = voice.refused.value.get(clip.artifact_id);
  if (refusal) {
    return (
      <div class="lines" role="alert" data-testid="clip-refused">
        {refusalLines(refusal).map((each, at) => (
          <p key={at}>{each}</p>
        ))}
      </div>
    );
  }
  return (
    <>
      <Pill quiet onClick={() => void voice.play({ kind: "clip", key: name, clip, lines: [line] }).catch(onError)} testId="hear-clip">
        {label}
      </Pill>
      {voice.key.value === name && <PlayerControls />}
    </>
  );
}
