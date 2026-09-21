import { useEffect, useState } from "preact/hooks";
import type { JSX } from "preact";
import * as nura from "../api/nura";
import type { AnswerLineOut, AnswerOut, ClipOut, FeedItemOut, FindOut, FindWhere } from "../api/types";
import { whatToDoLines } from "../day/model";
import { askStartedTheRedPath, whenNotReached } from "../day/redPath";
import { keptCards } from "../day/offline";
import { bindingOf } from "../offline/todayCache";
import { answerView, askMode } from "../feed/ask";
import { appendSentence, shownSentences, type StreamedSentence } from "../feed/askStream";
import { feedFor } from "../feed/session";
import { go } from "../flow";
import { density, profile, token } from "../store/session";
import { fill, language, LOCALE, t } from "../strings";
import { dateLine } from "../today/model";
import { voice } from "../player/voice";
import { Field, Header, Hear, Notice, Pill, Tile } from "../ui/components";
import { LookedAt, MessageBubble, Orb, SoftText, StatusLine } from "../ui/kit";
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
  // The answer, sentence by sentence, as it actually lands (P1, docs/design-direction.md "the
  // answer streams sentence by sentence") — never waited for whole: each `answer_sentence`
  // event is appended the instant it arrives, no timer, no typewriter, for BOTH askers (the
  // rule-based one replays its own already-composed lines the same way the agent asker streams
  // its own — `app.search.asker`). `SoftText` (below) draws only the newest sentence's words as
  // new; nothing already shown ever replays.
  const [sentences, setSentences] = useState<StreamedSentence[]>([]);
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
    setSentences([]);
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
        const onSentence = (sentenceText: string, cites: AnswerLineOut["cites"]) => setSentences((was) => appendSentence(was, sentenceText, cites));
        const onStepLabel = (key: string, label: string) => setSteps((was) => was.map((step) => (step.key === key ? { ...step, label } : step)));
        const heard = conversationId
          ? await nura.turnStream(bearer, papers.profile_id, conversationId, text, mode, language.value, onStep, onSentence, onStepLabel)
          : await nura.askStream(bearer, papers.profile_id, text, mode, language.value, onStep, onSentence, onStepLabel);
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

  // A question typed into the ask bar is asked at once: the answer is what he came for.
  useEffect(() => {
    if (asked && asked.trim()) void send();
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
    setSentences([]);
    setFound(null);
    setQuestion("");
  };

  const words: Record<Where, string> = { records: s.feed.filterRecords, web: s.feed.filterWeb, providers: s.feed.filterProviders, videos: s.feed.filterVideos };
  const view = answer ? answerView(answer) : null;
  const locale = LOCALE[language.value];
  // The shared trace's shape (`text`, `done`): every step but the one still streaming is done —
  // the same rule the old local stand-in used, now against `web/src/ui/kit/Conversation.tsx`.
  const traceSteps = steps.map((step, at) => ({ key: step.key, text: step.label, done: at < steps.length - 1 }));
  // ONE status line while Nura works: the newest real step's own label, or the generic
  // "Nura is looking" before the first one lands — never a checklist
  // (docs/design/experience-blueprint.html `think()`).
  const statusText = traceSteps.length > 0 ? traceSteps[traceSteps.length - 1]!.text : s.feed.askThinking;
  // The answer, sentence by sentence: the finished answer's own lines (with a clip, when one
  // is there) once they arrive — otherwise the sentences streamed so far, text only. Never
  // both (`shownSentences`), so nothing is ever shown twice once the final `answer` lands.
  const finalLines = view ? view.lines.map((line) => ({ text: line.text, clip: line.clip })) : null;
  const streamedAsLines = sentences.map((sentence) => ({ text: sentence.text, clip: null as ClipOut | null }));
  const displayedLines = shownSentences(streamedAsLines, finalLines);
  // "Looked at": the backend's own structured `looked_at` once the answer has landed (P1);
  // while still streaming, the bare nouns of the real steps sent so far — never invented.
  const lookedAtParts = (answer?.looked_at && answer.looked_at.length > 0 ? answer.looked_at.map((each) => each.label) : steps.map((step) => step.name)).join(", ");
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
      {/* Nura's own turn (P1, docs/design/experience-blueprint.html `nura()`): his question as
         a bubble, then the living orb beside ONE status line while she really works — no
         checklist — then, once real steps and real sentences exist, "Looked at" once and the
         answer as flowing paragraphs, each new sentence's words the only ones that animate
         in. Everything here is real: a status line is the newest step the backend actually
         reported, a sentence is one the plain-words gate already passed, and this box simply
         never renders until `sentQuestion` names a question actually sent. */}
      {sentQuestion && (busy || view || found) && (
        <div class="ask-thread">
          <MessageBubble from="person" label={s.talk.you} testId="ask-question">
            <p>{sentQuestion}</p>
          </MessageBubble>
          {(busy || (where === "records" && view)) && (
            <div class="ask-turn" data-testid={view ? "answer" : undefined}>
              <Orb thinking={busy} testId="ask-orb" />
              <div class="ask-turn-body">
                {busy && where === "records" && displayedLines.length === 0 && !view && <StatusLine text={statusText} testId="ask-trace" />}
                {busy && where !== "records" && <StatusLine text={statusText} testId="ask-trace" />}
                {where === "records" && steps.length > 0 && (displayedLines.length > 0 || view) && (
                  <LookedAt summary={fill(s.feed.askLookedAt, { parts: lookedAtParts })} steps={traceSteps} testId="ask-looked-at" />
                )}
                {where === "records" && displayedLines.length > 0 && (
                  <div aria-live="polite" data-testid="answer-lines">
                    {displayedLines.map((line, at) => (
                      <div key={at} data-testid="answer-line">
                        <SoftText as="p" pace="body" className="answer-flow" text={line.text} testId="answer-line-text" />
                        {line.clip && (
                          <HearClip name={`ask-clip:${at}`} clip={line.clip} line={line.text} label={fill(s.visit.hearClip, { doctor: line.clip.doctor })} onError={setError} />
                        )}
                      </div>
                    ))}
                  </div>
                )}
                {view?.honest.map((line, at) => (
                  <p key={`h${at}`} data-testid="answer-honest">
                    {line}
                  </p>
                ))}
                {view?.withheld && <p class="caption">{s.feed.askWithheld}</p>}
                {/* The safety line, once, at the foot of this turn (never a diagnosis, never
                   what to do about it) — the same words `boundary_lines` always gave, read as
                   one line instead of stacked as separate captions. */}
                {view && view.boundary.length > 0 && (
                  <p class="answer-boundary" data-testid="boundary">
                    {view.boundary.join(" ")}
                  </p>
                )}
                {/* Proposals (W2): a next step the agent asker offered, never taken by itself —
                   the pill's own words, already past every check. Shown, not yet tappable:
                   wiring one to the confirm flow that already exists for a visit, a message or
                   a booking is the next step here, so the pill is disabled rather than a dead
                   tap that looks live. */}
                {answer && answer.proposals && answer.proposals.length > 0 && (
                  <div class="choices two" data-testid="ask-proposals">
                    {answer.proposals.map((proposal, at) => (
                      <Pill key={at} onClick={() => {}} disabled testId={`ask-proposal-${at}`}>
                        {proposal.label}
                      </Pill>
                    ))}
                  </div>
                )}
                {view && <Hear lines={view.spoken} />}
              </div>
            </div>
          )}
        </div>
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
