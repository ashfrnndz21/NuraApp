import { useEffect, useMemo, useState } from "preact/hooks";
import type { JSX } from "preact";
import * as nura from "../api/nura";
import type { AnswerOut, FeedItemOut } from "../api/types";
import { whatToDoLines } from "../day/model";
import { askStartedTheRedPath, whenNotReached } from "../day/redPath";
import { keptCards } from "../day/offline";
import { bindingOf } from "../offline/todayCache";
import { answerView, askMode } from "../feed/ask";
import { go } from "../flow";
import { density, profile, token } from "../store/session";
import { fill, language, t } from "../strings";
import { browserClipDeps, ClipPlayer } from "../visit/clip";
import { Field, Header, Hear, Notice, Pill, Tile } from "../ui/components";
import { Shell } from "./Shell";

/** Ask about a card (E21-04), answered by E03's recall (`POST /profiles/{id}/ask`): voice
 *  mode in the patient's density, text in the caregiver's. He types his question — or says it
 *  into the phone's own keyboard microphone; the page does not listen, so no recording of his
 *  voice leaves the phone. The answer is the backend's: each cited line under its source line,
 *  the honest line when nothing on his papers answers, and the boundary last. Hear reads it
 *  out on tap, never by itself. A refusal is said in one plain sentence. */
export function AskScreen({ item, question: asked }: { item?: FeedItemOut; question?: string }): JSX.Element {
  const s = t();
  const [question, setQuestion] = useState(asked ?? "");
  const [answer, setAnswer] = useState<AnswerOut | null>(null);
  const [error, setError] = useState<unknown>(null);
  const [busy, setBusy] = useState(false);
  const mode = askMode(density());
  const clips = useMemo(
    () =>
      new ClipPlayer(
        browserClipDeps((artifactId, start, end) => nura.clip(token.value ?? "", profile.value?.profile_id ?? "", artifactId, start, end)),
      ),
    [],
  );
  useEffect(() => () => clips.forget(), [clips]);

  const send = async () => {
    const bearer = token.value;
    const papers = profile.value;
    const text = question.trim();
    if (!bearer || !papers || busy || !text) return;
    setBusy(true);
    setError(null);
    try {
      const found = await nura.ask(bearer, papers.profile_id, text, mode, language.value);
      // A red flag heard in the question went the red-flag path on the backend first: what to do
      // now, the backend's card, exactly as after a red word tapped on Today.
      if (found.red_flag?.red_flag) {
        const red = found.red_flag;
        return go({ name: "whatToDo", lines: red.card ? whatToDoLines(red.card) : red.lines, offline: null, refusal: null });
      }
      setAnswer(found);
    } catch (failure) {
      // A red word the backend heard but this key may not raise: the kept card and the refusal
      // named, as a refused red tap on the cloud gets — never nothing, never an answer instead.
      if (askStartedTheRedPath(failure)) {
        const kept = await keptCards(papers.profile_id, bindingOf(papers));
        return go({ name: "whatToDo", ...whenNotReached("red_flag", failure, kept?.cards ?? null, papers.region, s, language.value) });
      }
      setAnswer(null);
      setError(failure);
    } finally {
      setBusy(false);
    }
  };

  // A question typed into the ask bar is asked at once: the answer is what he came for.
  useEffect(() => {
    if (asked && asked.trim()) void send();
  }, []);

  const view = answer ? answerView(answer) : null;
  return (
    <Shell tab="today" testId="ask-screen" attrs={{ "data-mode": mode }} ask={false}>
      <Header title={s.feed.askTitle} onBack={item ? undefined : () => go({ name: "today" })} />
      {item && (
        <Tile paper>
          <p class="caption">{s.feed.askAbout}</p>
          <h2 class="title">{item.headline}</h2>
        </Tile>
      )}
      <Tile paper>
        <Field label={s.feed.askLabel} name="question" value={question} onInput={setQuestion} maxLength={300} />
        <p class="caption">{s.feed.askLead}</p>
        <Pill plum onClick={() => void send()} disabled={busy || question.trim().length === 0} testId="ask-send">
          {s.feed.ask}
        </Pill>
      </Tile>
      <Notice error={error} />
      {view && (
        <Tile paper testId="answer">
          <div class="lines" data-testid="answer-lines">
            {view.lines.map((line, at) => (
              <div key={at} data-testid="answer-line">
                <p>{line.text}</p>
                {line.source && (
                  <p class="provenance" data-testid="answer-source">
                    {s.feed[line.source]}
                  </p>
                )}
                {line.clip && (
                  <Pill quiet onClick={() => void clips.play(`${at}`, line.clip!).catch(setError)} testId="hear-clip">
                    {fill(s.visit.hearClip, { doctor: line.clip.doctor })}
                  </Pill>
                )}
              </div>
            ))}
            {view.honest.map((line, at) => (
              <p key={`h${at}`} data-testid="answer-honest">
                {line}
              </p>
            ))}
          </div>
          {view.withheld && <p class="caption">{s.feed.askWithheld}</p>}
          {view.boundary.length > 0 && (
            <div class="lines boundary" data-testid="boundary">
              {view.boundary.map((line, at) => (
                <p key={at}>{line}</p>
              ))}
            </div>
          )}
          <Hear lines={view.spoken} />
        </Tile>
      )}
      {item && (
        <Pill onClick={() => go({ name: "feed" })} testId="back-to-cards">
          {s.feed.back}
        </Pill>
      )}
    </Shell>
  );
}
