import { useState } from "preact/hooks";
import type { JSX } from "preact";
import * as nura from "../api/nura";
import type { JobKind, ProfileOut, SearchJobOut } from "../api/types";
import { statusLine } from "../feed/model";
import { feedLines } from "../today/model";
import { fill, language, t, type Strings } from "../strings";
import { Hear, Notice, Pill, Tile } from "../ui/components";
import { NoticeAt, useAct, useRead } from "./family/common";

/** How often a watch runs, in the backend's own cadence word ("daily", "weekly", …) turned into
 *  the caregiver's plain word — or the backend's own word verbatim when it names a cadence Nura
 *  has not given a translation for, so a new cadence never disappears silently. */
export function cadenceWord(cadence: string, s: Strings): string {
  const every: Record<string, string> = { on_change: s.chief.onChange, daily: s.chief.daily, weekly: s.chief.weekly, before_visits: s.chief.beforeVisits, once: s.chief.once };
  return every[cadence] ?? cadence;
}

/** A watch about his faith (the fasting month) is his yes or his no alone: she sees it on the
 *  list, and neither stops nor resumes it — Nura never guesses whether he fasts. */
export function isHisWatch(job: Pick<SearchJobOut, "kind" | "terms">): boolean {
  return job.kind === "seasonal" && job.terms.includes("fasting month");
}

/** The chief's panels on Home (docs/health-feed-spec.md §1, mockup v2 "Ash — Home"):
 *
 *  - **Sent to Pa this week** — every card made for him since Monday, newest first, each with
 *    what became of it (sent, opened, heard, held, not for him), where it came from, and what
 *    she can do: hear it, and pause the watch that found it. Never a count of anything.
 *  - **Watching for Pa** — every search the engine runs for him, in the backend's words, with
 *    its sources and how often; she pauses or starts one again, and adds a watch for dengue,
 *    haze, hot weather or festive food. Whether he fasts speaks of his faith, so the fasting
 *    month is his to add, on his own Me page (`FastingIsHisToSay` for anyone else); Nura never
 *    guesses it.
 *
 *  Every card line and every watch's words are the backend's; these name the panels. The
 *  backend decides who may read them (his chief, his steward, himself), and says so. */
export function ChiefPanels({ bearer, papers }: { bearer: string; papers: ProfileOut }): JSX.Element {
  const s = t();
  const name = papers.display_name;
  const id = papers.profile_id;
  const week = useRead(() => nura.feedWeek(bearer, id), [id, language.value]);
  const jobs = useRead(() => nura.searchJobs(bearer, id, language.value), [id, language.value]);
  const [adding, setAdding] = useState(false);
  const [added, setAdded] = useState(false);
  const a = useAct();
  const toggle = (job: SearchJobOut) =>
    a.act(job.job_id, async () => {
      await nura.pauseSearchJob(bearer, id, job.job_id, !job.enabled, language.value);
      await jobs.reload();
    });
  const pauseFor = (jobId: string, at: string) =>
    a.act(at, async () => {
      await nura.pauseSearchJob(bearer, id, jobId, false, language.value);
      await jobs.reload();
    });
  const add = (kind: JobKind, term: string) =>
    a.act("add", async () => {
      await nura.addSearchJob(bearer, id, kind, [term]);
      setAdding(false);
      setAdded(true);
      await jobs.reload();
    });
  const choices: [JobKind, string, string][] = [
    ["local", "dengue", s.chief.dengue],
    ["local", "haze", s.chief.haze],
    ["local", "heat", s.chief.heat],
    ["seasonal", "festive food", s.chief.festiveFood],
  ];
  // A watch about his faith (the fasting month) is his yes or his no alone: she sees it on the
  // list, and neither stops nor resumes it (`FastingIsHisToSay`, `isHisWatch` above).
  const paused = new Map((jobs.value ?? []).filter((job) => !isHisWatch(job)).map((job) => [job.job_id, !job.enabled]));
  return (
    <>
      <Tile glass testId="watching">
        <h2 class="title">{fill(s.chief.watchingTitle, { name })}</h2>
        {jobs.value?.length === 0 && <p>{s.chief.watchingNone}</p>}
        {jobs.value?.map((job) => (
          <div key={job.job_id} class="lines" data-testid="watch" data-kind={job.kind} data-enabled={job.enabled ? "true" : "false"}>
            <p data-testid="watch-label">{job.label}</p>
            <p class="provenance" data-testid="watch-meta">
              {[job.sources.join(", "), cadenceWord(job.cadence, s), job.enabled ? null : s.chief.paused].filter(Boolean).join(" · ")}
            </p>
            {!isHisWatch(job) && (
              <Pill quiet onClick={() => void toggle(job)} disabled={a.busy} testId="watch-toggle">
                {job.enabled ? s.chief.pause : s.chief.resume}
              </Pill>
            )}
            <NoticeAt act={a} where={job.job_id} />
          </div>
        ))}
        <p class="caption">{s.chief.sourcesNote}</p>
        {added && (
          <p role="status" data-testid="watch-added">
            {s.chief.added}
          </p>
        )}
        {adding ? (
          <div class="choices" role="group" aria-label={s.chief.addLead}>
            <p>{s.chief.addLead}</p>
            {choices.map(([kind, term, word]) => (
              <Pill key={term} onClick={() => void add(kind, term)} disabled={a.busy} testId={`watch-add-${term.replace(" ", "-")}`}>
                {word}
              </Pill>
            ))}
          </div>
        ) : (
          <Pill onClick={() => (setAdding(true), setAdded(false))} testId="watch-add">
            {s.chief.add}
          </Pill>
        )}
        <NoticeAt act={a} where="add" />
        <Notice error={jobs.error} />
      </Tile>
      <Tile glass testId="sent">
        <h2 class="title">{fill(s.chief.sentTitle, { name })}</h2>
        {week.value?.length === 0 && <p>{fill(s.chief.sentNone, { name })}</p>}
        {week.value?.map(({ item }) => {
          const said = statusLine(item, "caregiver");
          const publisher = typeof item.cite?.publisher === "string" ? item.cite.publisher : null;
          const shown = feedLines(item);
          const jobId = item.search_job_id ?? null;
          return (
            <div key={item.item_id} class="lines" data-testid="sent-item" data-type={item.type} data-status={item.status}>
              <p data-testid="sent-headline">{item.headline}</p>
              {said && (
                <p class="provenance" data-testid="sent-status">
                  {fill(s.feed[said], { name })}
                </p>
              )}
              {publisher && <p class="provenance">{fill(s.feed.fromPublisher, { publisher })}</p>}
              <Hear lines={item.voice.length > 0 ? item.voice : [item.headline, ...shown.lines, ...shown.boundary]} />
              {jobId && paused.get(jobId) === false && (
                <Pill quiet onClick={() => void pauseFor(jobId, item.item_id)} disabled={a.busy} testId="sent-pause">
                  {s.chief.pauseWatch}
                </Pill>
              )}
              <NoticeAt act={a} where={item.item_id} />
            </div>
          );
        })}
        <Notice error={week.error} />
      </Tile>
    </>
  );
}
