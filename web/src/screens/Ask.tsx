import { useEffect, useState } from "preact/hooks";
import type { JSX } from "preact";
import * as nura from "../api/nura";
import type { AnswerOut, FeedItemOut } from "../api/types";
import { answerView, askMode } from "../feed/ask";
import { go } from "../flow";
import { density, profile, token } from "../store/session";
import { fill, language, t } from "../strings";
import { voice } from "../player/voice";
import { Field, Header, Hear, Notice, Pill, TabBar, Tile } from "../ui/components";
import { HearClip } from "../ui/Player";

/** Ask about a card (E21-04), answered by E03's recall (`POST /profiles/{id}/ask`): voice
 *  mode in the patient's density, text in the caregiver's. He types his question — or says it
 *  into the phone's own keyboard microphone; the page does not listen, so no recording of his
 *  voice leaves the phone. The answer is the backend's: each cited line under its source line,
 *  the honest line when nothing on his papers answers, and the boundary last. Hear reads it
 *  out on tap, never by itself. A refusal is said in one plain sentence. */
export function AskScreen({ item }: { item: FeedItemOut }): JSX.Element {
  const s = t();
  const [question, setQuestion] = useState("");
  const [answer, setAnswer] = useState<AnswerOut | null>(null);
  const [error, setError] = useState<unknown>(null);
  const [busy, setBusy] = useState(false);
  const mode = askMode(density());
  // Leaving Ask: a clip stops and its recording is let go.
  useEffect(() => () => voice.forget(), []);

  const send = async () => {
    const bearer = token.value;
    const papers = profile.value;
    const text = question.trim();
    if (!bearer || !papers || busy || !text) return;
    setBusy(true);
    setError(null);
    try {
      setAnswer(await nura.ask(bearer, papers.profile_id, text, mode, language.value));
    } catch (failure) {
      setAnswer(null);
      setError(failure);
    } finally {
      setBusy(false);
    }
  };

  const view = answer ? answerView(answer) : null;
  return (
    <main class="screen" data-testid="ask-screen" data-mode={mode}>
      <Header title={s.feed.askTitle} />
      <Tile paper>
        <p class="caption">{s.feed.askAbout}</p>
        <h2 class="title">{item.headline}</h2>
      </Tile>
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
                  <HearClip name={`ask-clip:${at}`} clip={line.clip} line={line.text} label={fill(s.visit.hearClip, { doctor: line.clip.doctor })} onError={setError} />
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
      <Pill onClick={() => go({ name: "feed" })} testId="back-to-cards">
        {s.feed.back}
      </Pill>
      <TabBar current="today" onSelect={(tab) => go(tab === "me" ? { name: "me" } : { name: "today" })} />
    </main>
  );
}
