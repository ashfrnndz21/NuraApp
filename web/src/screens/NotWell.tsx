import { useEffect, useMemo, useState } from "preact/hooks";
import type { JSX } from "preact";
import * as nura from "../api/nura";
import { holdBackground, releaseBackground } from "../api/client";
import type { Said } from "../api/types";
import { keptCards } from "../day/offline";
import { offlineLines, whatToDoLines } from "../day/model";
import { whenNotReached } from "../day/redPath";
import { canRecord, saidOf, voiceRecorder } from "../day/voice";
import { go } from "../flow";
import { bindingOf } from "../offline/todayCache";
import { profile, token } from "../store/session";
import { language, t } from "../strings";
import { Header } from "../ui/components";
import { PaperTile, PillButton, StepTrace, type TraceStep } from "../ui/kit";
import { Shell } from "./Shell";
import { timer } from "../visit/model";

/** "I am not feeling well" (E13-02): he says it or types it, and the backend does the rest —
 *  his words kept, read for a red flag first, the family told, the State checked — and answers
 *  with the card he is shown next. The phone decides nothing: with no network, or no answer,
 *  it shows the backend's offline card (`day/offline.ts`), never nothing. */
export function NotWellScreen(): JSX.Element {
  const s = t();
  const bearer = token.value;
  const papers = profile.value;
  const [words, setWords] = useState("");
  const [stage, setStage] = useState<"ask" | "listening" | "sending">("ask");
  const [noMic, setNoMic] = useState(false);
  const [steps, setSteps] = useState<TraceStep[]>([]);
  const recorder = useMemo(() => voiceRecorder(), []);
  useEffect(() => () => recorder.discard(), [recorder]);
  // He may say a red word on this screen (W7, E13-02): no background read is dispatched from
  // the moment it opens, so nothing of Today's own loading is still finishing on its own
  // schedule in the window between now and the tap that sends his words — the far likelier
  // gap than the one already caught at the moment of that tap itself (`api/client.ts`'s
  // urgent-arrival abort, `enqueue`). Released the moment he leaves, whether or not he sent.
  useEffect(() => {
    holdBackground();
    return releaseBackground;
  }, []);

  const send = async (said: Said) => {
    if (!bearer || !papers) {
      // No session on this phone: nothing can be sent, and he still gets the calls.
      return go({ name: "whatToDo", lines: offlineLines("unknown", null, papers?.region, s, language.value).lines, offline: null, refusal: "NoSession" });
    }
    setStage("sending");
    setSteps([]);
    try {
      // The whole button runs first, entirely unchanged, before a single step is streamed
      // back (`not_feeling_well_stream`'s own module docstring): a red word already reached
      // the flag and his family by the time this trace shows anything at all.
      const card = await nura.notFeelingWellStream(bearer, papers.profile_id, said, language.value, (key, text) => {
        setSteps((prior) => [...prior.map((step) => ({ ...step, done: true })), { key, text, done: false }]);
      });
      setSteps((prior) => prior.map((step) => ({ ...step, done: true })));
      go({ name: "whatToDo", lines: whatToDoLines(card), offline: null, refusal: null });
    } catch (failure) {
      const kept = await keptCards(papers.profile_id, bindingOf(papers));
      go({ name: "whatToDo", ...whenNotReached("unknown", failure, kept?.cards ?? null, papers.region, s, language.value) });
    }
  };

  const listen = async () => {
    setNoMic(false);
    try {
      await recorder.start();
      setStage("listening");
    } catch {
      setNoMic(true);
    }
  };

  const stopAndSend = async () => {
    const kept = await recorder.stop();
    if (kept) await send(await saidOf(kept));
    else setStage("ask");
  };

  // A hidden page stops listening; what he said so far is sent, as he pressed the button.
  useEffect(() => {
    const onHidden = () => {
      if (document.visibilityState === "hidden" && stage === "listening") void stopAndSend();
    };
    document.addEventListener("visibilitychange", onHidden);
    return () => document.removeEventListener("visibilitychange", onHidden);
  }, [stage]);

  return (
    <Shell tab="home" testId="not-well-screen" attrs={{ "data-stage": stage }} ask={false} bar={stage === "ask"}>
      <Header title={s.day.notWellTitle} onBack={stage === "ask" ? () => go({ name: "today" }) : undefined} />
      {stage === "ask" && (
        <PaperTile testId="not-well-ask">
          <p>{s.day.notWellLead}</p>
          <label class="by-hand-label">
            <span class="label">{s.day.wordsLabel}</span>
            <textarea
              class="field"
              name="words"
              maxLength={2000}
              value={words}
              onInput={(event) => setWords((event.target as HTMLTextAreaElement).value)}
              data-testid="not-well-words"
            />
          </label>
          <PillButton variant="primary" onClick={() => void send({ words: words.trim() })} disabled={!words.trim()} testId="not-well-send">
            {s.day.send}
          </PillButton>
          {canRecord() && (
            <PillButton onClick={() => void listen()} testId="not-well-say">
              {s.day.sayIt}
            </PillButton>
          )}
          {noMic && <p data-testid="no-mic">{s.visit.noMic}</p>}
        </PaperTile>
      )}
      {stage === "listening" && (
        <>
          <PaperTile role="status" testId="listening">
            <p class="recording">
              <span class="dot" aria-hidden="true" data-testid="red-dot" />
              <span class="timer" data-testid="timer">
                {timer(recorder.elapsed.value)}
              </span>
              <span>{s.visit.listening}</span>
            </p>
          </PaperTile>
          <PillButton variant="primary" onClick={() => void stopAndSend()} testId="not-well-stop">
            {s.day.stopAndSend}
          </PillButton>
        </>
      )}
      {stage === "sending" && (
        <PaperTile role="status" testId="sending">
          <StepTrace steps={steps} working={s.day.sending} testId="not-well-trace" />
        </PaperTile>
      )}
    </Shell>
  );
}
