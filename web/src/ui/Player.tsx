import type { JSX } from "preact";
import { SPEEDS, type ClipRef, type Speed } from "../player/player";
import { voice } from "../player/voice";
import { refusalLines, t } from "../strings";
import { Pill } from "./components";

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
    </div>
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
