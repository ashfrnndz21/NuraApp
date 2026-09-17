import { useEffect, useState } from "preact/hooks";
import type { JSX } from "preact";
import * as nura from "../api/nura";
import type { AnswerOut, FeedItemOut, FindOut, FindWhere } from "../api/types";
import { whatToDoLines } from "../day/model";
import { askStartedTheRedPath, whenNotReached } from "../day/redPath";
import { keptCards } from "../day/offline";
import { bindingOf } from "../offline/todayCache";
import { answerView, askMode } from "../feed/ask";
import { feedFor } from "../feed/session";
import { go } from "../flow";
import { density, profile, token } from "../store/session";
import { fill, language, LOCALE, t } from "../strings";
import { dateLine } from "../today/model";
import { voice } from "../player/voice";
import { Field, Header, Hear, Notice, Pill, Tile } from "../ui/components";
import { LookedAt, MessageBubble, ThinkingTrace } from "../ui/kit";
import { HearClip } from "../ui/Player";
import { Shell } from "./Shell";

/** One step of the trace, as the screen keeps it while an answer streams in: the backend's
 *  key and label (`app.search.ask.STEP_KEYS`), and for Ask's own records the bare noun
 *  (`ASK_STEP_NAMES`) the collapsed "What Nura looked at" line joins together. */
interface Step {
  key: string;
  label: string;
  name: string;
}

/** Where the ask bar looks (spec §0, mockup v2): his records — Ask, E03's recall — or the web,
 *  his providers, or videos. The web and videos are the allowlisted sources only, each page said
 *  in his language by the backend with the boundary last; providers is his own directory. */
export type Where = "records" | FindWhere;
const WHERES: readonly Where[] = ["records", "web", "providers", "videos"];

/** Ask about a card (E21-04), or ask or search from Today, answered by E03's recall
 *  (`POST /profiles/{id}/ask`): voice mode in the patient's density, text in the caregiver's.
 *  He types his question — or says it into the phone's own keyboard microphone; the page does
 *  not listen, so no recording of his voice leaves the phone. The answer is the backend's: each
 *  cited line under its source line, the honest line when nothing on his papers answers, and
 *  the boundary last. Hear reads it out on tap, never by itself. A refusal is said in one plain
 *  sentence. In the caregiver's density the ask bar has its filters: Records, Web, Providers,
 *  Videos. The patient's has one thing: his records. */
export function AskScreen({ item, question: asked }: { item?: FeedItemOut; question?: string }): JSX.Element {
  const s = t();
  const [question, setQuestion] = useState(asked ?? "");
  const [where, setWhere] = useState<Where>("records");
  const [answer, setAnswer] = useState<AnswerOut | null>(null);
  const [found, setFound] = useState<FindOut | null>(null);
  const [error, setError] = useState<unknown>(null);
  const [busy, setBusy] = useState(false);
  const [sentQuestion, setSentQuestion] = useState<string | null>(null);
  const [steps, setSteps] = useState<Step[]>([]);
  // The one thing a screen reader hears while Nura works: that she started, and that the
  // answer is there — never a line per step (docs/design-direction.md "Conversation, waiting
  // and thinking").
  const [announce, setAnnounce] = useState("");
  const mode = askMode(density());
  const filters = density() === "caregiver";
  // Leaving Ask: a clip stops and its recording is let go.
  useEffect(() => () => voice.forget(), []);

  const send = async () => {
    const bearer = token.value;
    const papers = profile.value;
    const text = question.trim();
    if (!bearer || !papers || busy || !text) return;
    setBusy(true);
    setError(null);
    setAnswer(null);
    setFound(null);
    setSentQuestion(text);
    setSteps([]);
    setAnnounce(s.feed.askThinking);
    try {
      if (where === "records") {
        // Streamed (docs/design-direction.md "Conversation, waiting and thinking"): a step
        // the instant each real part of his record is read, the answer the instant it is
        // ready — never held back to make the trace look slower.
        const heard = await nura.askStream(bearer, papers.profile_id, text, mode, language.value, (key, label, name) =>
          setSteps((was) => [...was, { key, label, name }]),
        );
        // A red flag heard in the question went the red-flag path on the backend first: what to
        // do now, the backend's card, exactly as after a red word tapped on Today.
        if (heard.red_flag?.red_flag) {
          const red = heard.red_flag;
          return go({ name: "whatToDo", lines: red.card ? whatToDoLines(red.card) : red.lines, offline: null, refusal: null });
        }
        setAnswer(heard);
        setAnnounce(s.feed.askAnswered);
        // He asked more about this card: kept for the next connection (E11-08).
        if (item) {
          const events = feedFor(bearer, papers).events;
          if (papers.standing === "owner" || papers.scopes.includes("records")) void events.add(item.item_id, "asked_more").then(() => events.flush());
        }
      } else if (where === "providers") {
        // A directory read: nothing real to trace before the results.
        setFound(await nura.find(bearer, papers.profile_id, text, where, language.value));
        setAnnounce(s.feed.askAnswered);
      } else {
        setFound(
          await nura.findStream(bearer, papers.profile_id, text, where, language.value, (key, label) =>
            setSteps((was) => [...was, { key, label, name: label }]),
          ),
        );
        setAnnounce(s.feed.askAnswered);
      }
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

  const words: Record<Where, string> = { records: s.feed.filterRecords, web: s.feed.filterWeb, providers: s.feed.filterProviders, videos: s.feed.filterVideos };
  const view = answer ? answerView(answer) : null;
  const locale = LOCALE[language.value];
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
        {filters && (
          <div class="choices two" role="group" aria-label={s.feed.filterLabel} data-testid="ask-filters">
            {WHERES.map((each) => (
              <Pill key={each} chosen={where === each} onClick={() => setWhere(each)} testId={`filter-${each}`}>
                {words[each]}
              </Pill>
            ))}
          </div>
        )}
        <p class="caption">{s.feed.askLead}</p>
        <Pill plum onClick={() => void send()} disabled={busy || question.trim().length === 0} testId="ask-send">
          {where === "records" ? s.feed.ask : s.feed.search}
        </Pill>
      </Tile>
      <Notice error={error} />
      <p class="sr-only" aria-live="polite" data-testid="ask-live">
        {announce}
      </p>
      {sentQuestion && (busy || view || found) && (
        <div class="ask-thread">
          <MessageBubble from="me" testId="ask-question">
            <p>{sentQuestion}</p>
          </MessageBubble>
          {busy && <ThinkingTrace heading={s.feed.askThinking} steps={steps} testId="ask-trace" />}
        </div>
      )}
      {view && (
        <Tile paper testId="answer">
          {where === "records" && steps.length > 0 && (
            <LookedAt
              label={fill(s.feed.askLookedAt, { parts: steps.map((step) => step.name).join(", ") })}
              testId="ask-looked-at"
            />
          )}
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
      {found && found.results.length === 0 && (
        <Tile paper testId="found-nothing">
          <p>{s.feed.foundNothing}</p>
        </Tile>
      )}
      {found?.results.map((result, at) => {
        const boundary = (result.boundary ?? "").split("\n").filter((line) => line.trim() !== "");
        return (
          <Tile paper key={at} testId="found">
            <h2 class="title">{result.title}</h2>
            {result.lines.length > 0 && (
              <div class="lines">
                {result.lines.map((line, n) => (
                  <p key={n}>{line}</p>
                ))}
              </div>
            )}
            {boundary.length > 0 && (
              <div class="lines boundary" data-testid="boundary">
                {boundary.map((line, n) => (
                  <p key={n}>{line}</p>
                ))}
              </div>
            )}
            {result.next_visit_at && <p class="provenance">{fill(s.feed.nextVisit, { date: dateLine(new Date(result.next_visit_at), locale) })}</p>}
            {result.url && result.url.startsWith("https://") && result.publisher && (
              <p class="provenance source">
                <a href={result.url} target="_blank" rel="noopener noreferrer" data-testid="found-link">
                  {fill(result.media === "video" ? s.feed.watchWhole : s.feed.readPage, { publisher: result.publisher })}
                </a>
              </p>
            )}
            {result.lines.length > 0 && <Hear lines={[result.title, ...result.lines, ...boundary]} />}
          </Tile>
        );
      })}
      {item && (
        <Pill onClick={() => go({ name: "feed" })} testId="back-to-cards">
          {s.feed.back}
        </Pill>
      )}
    </Shell>
  );
}
