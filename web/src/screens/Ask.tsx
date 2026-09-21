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
import { LookedAt, MessageBubble, StepTrace } from "../ui/kit";
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

/** One earlier turn on this thread (W2), kept client-side for the screen to show above the
 *  live one — the backend keeps the real thread; this is only what has already been shown in
 *  this visit to the screen. */
interface PastTurn {
  question: string;
  lines: string[];
  honest: string[];
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
export function AskScreen({ item, question: asked, draft }: { item?: FeedItemOut; question?: string; draft?: boolean }): JSX.Element {
  const s = t();
  const [question, setQuestion] = useState(asked ?? "");
  const [where, setWhere] = useState<Where>("records");
  const [answer, setAnswer] = useState<AnswerOut | null>(null);
  const [found, setFound] = useState<FindOut | null>(null);
  const [error, setError] = useState<unknown>(null);
  const [busy, setBusy] = useState(false);
  const [sentQuestion, setSentQuestion] = useState<string | null>(null);
  const [steps, setSteps] = useState<Step[]>([]);
  // The agent asker's own answer (`NURA_ASKER=claude`), as its lines actually land — never
  // waited for whole: each is drawn the instant its `answer_delta` event arrives, no timer,
  // no typewriter. The rule-based asker never sends one, so this stays empty for it and the
  // screen behaves exactly as before (docs/design-direction.md "Conversation, waiting and
  // thinking").
  const [deltaLines, setDeltaLines] = useState<string[]>([]);
  // The one thing a screen reader hears while Nura works: that she started, and that the
  // answer is there — never a line per step (docs/design-direction.md "Conversation, waiting
  // and thinking").
  const [announce, setAnnounce] = useState("");
  // W2: Ask is a conversation. `conversationId` is set from the first answer's own
  // `conversation_id` (the backend already picked, or started, the thread); once set, every
  // later question on this screen is a turn on that same thread instead of a fresh ask.
  // `pastTurns` is only what this visit to the screen has already shown — the thread itself
  // lives on the backend, across days, whether or not the web client ever asks for it.
  const [conversationId, setConversationId] = useState<string | null>(null);
  const [pastTurns, setPastTurns] = useState<PastTurn[]>([]);
  const mode = askMode(density());
  const filters = density() === "caregiver";
  // Leaving Ask: a clip stops and its recording is let go.
  useEffect(() => () => voice.forget(), []);

  const send = async () => {
    const bearer = token.value;
    const papers = profile.value;
    const text = question.trim();
    if (!bearer || !papers || busy || !text) return;
    // W2: the turn about to be replaced on screen (if any) becomes the thread's own history —
    // never dropped just because a new question was asked. Only `records` turns join the
    // thread; a web/providers/videos search was never part of it.
    if (where === "records" && sentQuestion && answer) {
      const seen = answerView(answer);
      setPastTurns((was) => [...was, { question: sentQuestion, lines: seen.lines.map((line) => line.text), honest: seen.honest }]);
    }
    setBusy(true);
    setError(null);
    setAnswer(null);
    setFound(null);
    setSentQuestion(text);
    setSteps([]);
    setDeltaLines([]);
    setAnnounce(s.feed.askThinking);
    try {
      if (where === "records") {
        // Streamed (docs/design-direction.md "Conversation, waiting and thinking"): a step
        // the instant each real part of his record is read, the answer the instant it is
        // ready — never held back to make the trace look slower. A narrator's own rephrasing
        // of a step (`onStepLabel`) may follow well after that step, even after the answer;
        // it only ever replaces that step's label in place.
        //
        // The first question on this screen goes through `askStream`, which the backend
        // already writes onto his current conversation (`app.search.conversation.
        // current_conversation`) and names back in `conversation_id`; once known, every later
        // question here is a turn on that same thread (`turnStream`), so a follow-up like
        // "and the cost of that?" can be resolved against what was just asked and found.
        const onStep = (key: string, label: string, name: string) => setSteps((was) => [...was, { key, label, name }]);
        const onDelta = (chunk: string) => setDeltaLines((was) => [...was, chunk]);
        const onStepLabel = (key: string, label: string) => setSteps((was) => was.map((step) => (step.key === key ? { ...step, label } : step)));
        const heard = conversationId
          ? await nura.turnStream(bearer, papers.profile_id, conversationId, text, mode, language.value, onStep, onDelta, onStepLabel)
          : await nura.askStream(bearer, papers.profile_id, text, mode, language.value, onStep, onDelta, onStepLabel);
        // A red flag heard in the question went the red-flag path on the backend first: what to
        // do now, the backend's card, exactly as after a red word tapped on Today.
        if (heard.red_flag?.red_flag) {
          const red = heard.red_flag;
          return go({ name: "whatToDo", lines: red.card ? whatToDoLines(red.card) : red.lines, offline: null, refusal: null });
        }
        if (heard.conversation_id) setConversationId(heard.conversation_id);
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
          await nura.findStream(
            bearer,
            papers.profile_id,
            text,
            where,
            language.value,
            (key, label) => setSteps((was) => [...was, { key, label, name: label }]),
            (key, label) => setSteps((was) => was.map((step) => (step.key === key ? { ...step, label, name: label } : step))),
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

  // A question typed into the ask bar is asked at once: the answer is what he came for. A
  // draft (`draft`, "Ask about this paper" — library part B #3) only names the paper in the
  // box, in his own words to finish and send himself: never asked on its own.
  useEffect(() => {
    if (!draft && asked && asked.trim()) void send();
  }, []);

  // His own "New conversation" (W2): close the open thread on the backend and start clean —
  // nothing shown on this screen carries over.
  const startNewConversation = async () => {
    const bearer = token.value;
    const papers = profile.value;
    if (!bearer || !papers || busy) return;
    await nura.startConversation(bearer, papers.profile_id);
    setConversationId(null);
    setPastTurns([]);
    setAnswer(null);
    setSentQuestion(null);
    setSteps([]);
    setDeltaLines([]);
    setFound(null);
    setQuestion("");
  };

  const words: Record<Where, string> = { records: s.feed.filterRecords, web: s.feed.filterWeb, providers: s.feed.filterProviders, videos: s.feed.filterVideos };
  const view = answer ? answerView(answer) : null;
  const locale = LOCALE[language.value];
  // The shared trace's shape (`text`, `done`): every step but the one still streaming is done —
  // the same rule the old local stand-in used, now against `web/src/ui/kit/Conversation.tsx`.
  const traceSteps = steps.map((step, at) => ({ key: step.key, text: step.label, done: at < steps.length - 1 }));
  return (
    <Shell tab="home" testId="ask-screen" attrs={{ "data-mode": mode }} ask={false}>
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
        <div class="choices two">
          <Pill plum onClick={() => void send()} disabled={busy || question.trim().length === 0} testId="ask-send">
            {where === "records" ? s.feed.ask : s.feed.search}
          </Pill>
          {conversationId && (
            <Pill onClick={() => void startNewConversation()} disabled={busy} testId="new-conversation">
              {s.feed.newConversation}
            </Pill>
          )}
        </div>
      </Tile>
      <Notice error={error} />
      <p class="sr-only" aria-live="polite" data-testid="ask-live">
        {announce}
      </p>
      {pastTurns.length > 0 && (
        <div class="ask-thread" data-testid="ask-earlier-turns">
          <p class="caption">{s.feed.earlierInConversation}</p>
          {pastTurns.map((turn, at) => (
            <div key={at} data-testid="ask-earlier-turn">
              <MessageBubble from="person" label={s.talk.you} testId="ask-earlier-question">
                <p>{turn.question}</p>
              </MessageBubble>
              <div class="lines">
                {turn.lines.map((line, n) => (
                  <p key={n}>{line}</p>
                ))}
                {turn.honest.map((line, n) => (
                  <p key={`h${n}`}>{line}</p>
                ))}
              </div>
            </div>
          ))}
        </div>
      )}
      {sentQuestion && (busy || view || found) && (
        <div class="ask-thread">
          <MessageBubble from="person" label={s.talk.you} testId="ask-question">
            <p>{sentQuestion}</p>
          </MessageBubble>
          {busy && <StepTrace steps={traceSteps} working={s.feed.askThinking} testId="ask-trace" />}
          {/* The agent asker's own answer, drawn as it lands (`onDelta`): each line the
             instant its own event arrives, the pulsing dots (inside `StepTrace`, above)
             still showing until the final `answer` event replaces all of this with the
             finished, cited answer below. Never shown once the answer itself has arrived. */}
          {busy && deltaLines.length > 0 && (
            <div class="lines" data-testid="answer-delta-lines">
              {deltaLines.map((line, at) => (
                <p key={at} data-testid="answer-delta-line">
                  {line}
                </p>
              ))}
            </div>
          )}
        </div>
      )}
      {view && (
        <Tile paper testId="answer">
          {where === "records" && steps.length > 0 && (
            <LookedAt
              summary={fill(s.feed.askLookedAt, { parts: steps.map((step) => step.name).join(", ") })}
              steps={traceSteps}
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
          {/* Proposals (W2): a next step the agent asker offered, never taken by itself — the
             pill's own words, already past every check. Shown, not yet tappable: wiring one to
             the confirm flow that already exists for a visit, a message or a booking is the
             next step here, so the pill is disabled rather than a dead tap that looks live. */}
          {answer && answer.proposals && answer.proposals.length > 0 && (
            <div class="choices two" data-testid="ask-proposals">
              {answer.proposals.map((proposal, at) => (
                <Pill key={at} onClick={() => {}} disabled testId={`ask-proposal-${at}`}>
                  {proposal.label}
                </Pill>
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
