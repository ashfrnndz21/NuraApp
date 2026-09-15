import { useEffect, useMemo, useState } from "preact/hooks";
import type { JSX } from "preact";
import * as nura from "../api/nura";
import type { AnswerOut, FeedItemOut, FindOut, FindWhere } from "../api/types";
import { answerView, askMode } from "../feed/ask";
import { feedFor } from "../feed/session";
import { go, openTab } from "../flow";
import { density, profile, token } from "../store/session";
import { fill, language, LOCALE, t } from "../strings";
import { dateLine } from "../today/model";
import { browserClipDeps, ClipPlayer } from "../visit/clip";
import { Field, Header, Hear, Notice, Pill, TabBar, Tile } from "../ui/components";

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
export function AskScreen({ item }: { item?: FeedItemOut }): JSX.Element {
  const s = t();
  const [question, setQuestion] = useState("");
  const [where, setWhere] = useState<Where>("records");
  const [answer, setAnswer] = useState<AnswerOut | null>(null);
  const [found, setFound] = useState<FindOut | null>(null);
  const [error, setError] = useState<unknown>(null);
  const [busy, setBusy] = useState(false);
  const mode = askMode(density());
  const filters = density() === "caregiver";
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
    setAnswer(null);
    setFound(null);
    try {
      if (where === "records") {
        setAnswer(await nura.ask(bearer, papers.profile_id, text, mode, language.value));
        // He asked more about this card: kept for the next connection (E11-08).
        if (item) {
          const events = feedFor(bearer, papers).events;
          if (papers.standing === "owner" || papers.scopes.includes("records")) void events.add(item.item_id, "asked_more").then(() => events.flush());
        }
      } else {
        setFound(await nura.find(bearer, papers.profile_id, text, where, language.value));
      }
    } catch (failure) {
      setError(failure);
    } finally {
      setBusy(false);
    }
  };

  const words: Record<Where, string> = { records: s.feed.filterRecords, web: s.feed.filterWeb, providers: s.feed.filterProviders, videos: s.feed.filterVideos };
  const view = answer ? answerView(answer) : null;
  const locale = LOCALE[language.value];
  return (
    <main class="screen" data-testid="ask-screen" data-mode={mode}>
      <Header title={s.feed.askTitle} />
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
      <Pill onClick={() => go({ name: item ? "feed" : "today" })} testId="back-to-cards">
        {item ? s.feed.back : s.day.backToday}
      </Pill>
      <TabBar current="today" onSelect={openTab} />
    </main>
  );
}
