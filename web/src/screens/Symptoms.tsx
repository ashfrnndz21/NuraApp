import { useEffect, useMemo, useState } from "preact/hooks";
import type { JSX } from "preact";
import * as nura from "../api/nura";
import type { Said, SymptomEntryOut, SymptomLogOut } from "../api/types";
import { canRecord, saidOf, voiceRecorder } from "../day/voice";
import { go } from "../flow";
import { density, profile, token } from "../store/session";
import { fill, language, t } from "../strings";
import { Header, Hear, Notice, Pill, Tile } from "../ui/components";
import { timer } from "../visit/model";

/** How he has felt (E14-01): the week's symptoms in the backend's plain words — what, how bad,
 *  since when, and whether he said it or typed it — and one more, said or typed in his own
 *  words. A red flag in it escalates on the backend exactly as the button does; the phone then
 *  goes back to Today, where the flag's card is first. */
export function SymptomsScreen(): JSX.Element {
  const s = t();
  const bearer = token.value;
  const papers = profile.value;
  const [log, setLog] = useState<SymptomLogOut | null>(null);
  const [saved, setSaved] = useState<SymptomEntryOut | null>(null);
  const [words, setWords] = useState("");
  const [stage, setStage] = useState<"ask" | "listening" | "sending">("ask");
  const [error, setError] = useState<unknown>(null);
  // What he said that did not reach Nura, kept on the page for one more try.
  const [unsent, setUnsent] = useState<Said | null>(null);
  const recorder = useMemo(() => voiceRecorder(), []);
  useEffect(() => () => recorder.discard(), [recorder]);

  const read = async () => {
    if (!bearer || !papers) return;
    try {
      setLog(await nura.symptomLog(bearer, papers.profile_id, language.value));
    } catch (failure) {
      setError(failure);
    }
  };
  useEffect(() => {
    void read();
  }, [bearer, papers?.profile_id, language.value]);

  const send = async (said: Said) => {
    if (!bearer || !papers) return;
    setStage("sending");
    setError(null);
    try {
      const logged = await nura.logSymptom(bearer, papers.profile_id, said, language.value);
      setUnsent(null);
      // A red flag in what he said: the backend escalated, and its urgent card is what he sees.
      if (logged.card && logged.card.length > 0) return go({ name: "whatToDo", lines: logged.card.map((line) => line.text), offline: null, refusal: null });
      if (logged.flag_id) return go({ name: "today" });
      setSaved(logged.entry);
      setWords("");
      setStage("ask");
      await read();
    } catch (failure) {
      // Not kept: said in one sentence, his words still here, and one tap sends them again.
      setError(failure);
      setUnsent(said);
      setStage("ask");
    }
  };

  const listen = async () => {
    try {
      await recorder.start();
      setStage("listening");
    } catch {
      setError(null);
    }
  };
  const stopAndSend = async () => {
    const kept = await recorder.stop();
    if (kept) await send(await saidOf(kept));
    else setStage("ask");
  };

  const own = papers?.standing === "owner";
  const title = own ? s.day.symptomsTitleSelf : fill(s.day.symptomsTitleOther, { name: papers?.display_name ?? "" });
  const lines = log?.lines.map((line) => line.text) ?? [];
  return (
    <main class="screen" data-density={density()} data-testid="symptoms-screen" data-stage={stage}>
      <Header title={title} onBack={stage === "ask" ? () => go({ name: "today" }) : undefined} />
      <Notice error={error} />
      {saved && (
        <Tile paper role="status" testId="symptom-saved">
          <p>{s.day.symptomsSaved}</p>
          <div class="lines">
            {saved.lines.map((line) => (
              <p key={line.id}>{line.text}</p>
            ))}
          </div>
        </Tile>
      )}
      {stage === "ask" && (
        <Tile paper testId="symptom-ask">
          <p>{s.day.symptomsLead}</p>
          <label class="by-hand-label">
            <span class="label">{s.day.wordsLabel}</span>
            <textarea
              class="field"
              name="symptom"
              maxLength={2000}
              value={words}
              onInput={(event) => setWords((event.target as HTMLTextAreaElement).value)}
              data-testid="symptom-words"
            />
          </label>
          <Pill plum onClick={() => void send({ words: words.trim() })} disabled={!words.trim()} testId="symptom-keep">
            {s.day.symptomsKeep}
          </Pill>
          {unsent?.audio && (
            <Pill onClick={() => void send(unsent)} testId="symptom-again">
              {s.day.sendAgain}
            </Pill>
          )}
          {canRecord() && (
            <Pill onClick={() => void listen()} testId="symptom-say">
              {s.day.sayIt}
            </Pill>
          )}
        </Tile>
      )}
      {stage === "listening" && (
        <>
          <Tile paper role="status" testId="listening">
            <p class="recording">
              <span class="dot" aria-hidden="true" />
              <span class="timer">{timer(recorder.elapsed.value)}</span>
              <span>{s.visit.listening}</span>
            </p>
          </Tile>
          <Pill plum onClick={() => void stopAndSend()} testId="symptom-stop">
            {s.day.stopAndSend}
          </Pill>
        </>
      )}
      {stage === "sending" && (
        <Tile paper role="status" testId="sending">
          <p>{s.day.sending}</p>
        </Tile>
      )}
      {lines.length > 0 && (
        <Tile paper testId="symptom-log">
          <div class="lines" data-testid="symptom-log-lines">
            {lines.map((line, at) => (
              <p key={at}>{line}</p>
            ))}
          </div>
          <Hear lines={lines} />
        </Tile>
      )}
    </main>
  );
}
