import { useEffect, useState } from "preact/hooks";
import type { JSX } from "preact";
import * as nura from "../api/nura";
import { Unreachable } from "../api/client";
import type { FeedItemOut } from "../api/types";
import { go } from "../flow";
import { hold, tapId } from "../offline/queue";
import { bindingOf, zoneOf } from "../offline/todayCache";
import { density, profile, token } from "../store/session";
import { fill, language, t } from "../strings";
import { clockWords, feedLines, whyLine } from "../today/model";
import { Card, Notice, Pill, Tile } from "../ui/components";

import { ClipCard, FeelingStrip, NudgeTile } from "./components";
import { cloudView, clipsOf, nudgeToShow, whatToDoLines, type CloudView, type NudgeShown } from "./model";
import { keepCards, keptCards, wantsCards } from "./offline";
import { whenNotReached } from "./redPath";

/** "I am not feeling well" (E13-02): on Today whatever else is or is not on the page — kept,
 *  offline, or blank — because it works with no network too (the offline card). */
export function NotWellButton(): JSX.Element {
  return (
    <Pill coral onClick={() => go({ name: "notWell" })} testId="not-well">
      {t().day.notWell}
    </Pill>
  );
}

/** What the day adds to Today when the page is live (W7): the feeling cloud after a change in
 *  State (E17-01), the day's nudge where the backend plans it (E11-07), the way to write down
 *  how he feels (E14-01), and — quietly, once a day — the offline cards kept for no network.
 *  The cloud and the nudge are his: they show on his own phone. `stateId` is the State Today
 *  last read; the cloud is read again whenever it changes. */
export function DayOnToday({ stateId, live }: { stateId: string | null; live: boolean }): JSX.Element {
  const s = t();
  const bearer = token.value;
  const papers = profile.value;
  const [cloud, setCloud] = useState<CloudView | null>(null);
  const [nudge, setNudge] = useState<NudgeShown | null>(null);
  const [said, setSaid] = useState<string[]>([]);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<unknown>(null);
  // A non-red word tapped with no network: held on the phone with the moment he tapped it,
  // in place of the note or question a live tap gets (#171).
  const [heldAt, setHeldAt] = useState<string | null>(null);
  const owner = papers?.standing === "owner";
  const records = papers?.scopes.includes("records") ?? false;

  const read = async () => {
    if (!bearer || !papers || !live) return;
    const id = papers.profile_id;
    if (owner && records) {
      try {
        setCloud(cloudView(await nura.feelingCloud(bearer, id, language.value)));
      } catch {
        setCloud(null);
      }
      try {
        const day = await nura.dayNudges(bearer, id);
        const plan = await nura.nudgePlan(bearer, id);
        setNudge(nudgeToShow(day, plan, new Date()));
      } catch {
        setNudge(null);
      }
    }
    // The offline cards, read once a day and in a new language; a failure keeps what was kept.
    try {
      const binding = bindingOf(papers);
      if (wantsCards(await keptCards(id, binding), language.value, new Date())) {
        await keepCards(id, await nura.offlineCards(bearer, id, language.value), binding, new Date(), zoneOf(papers.region));
      }
    } catch {
      /* the phone keeps the cards it had */
    }
  };
  useEffect(() => {
    void read();
  }, [bearer, papers?.profile_id, stateId, live, language.value]);

  /** A tap on a word. A red word goes first (the urgent lane) and its card is what he sees next;
   *  if the backend cannot be reached, the offline card — never nothing. */
  const tap = async (word: { word: string; red: boolean }) => {
    if (!bearer || !papers || busy) return;
    setBusy(true);
    setError(null);
    setHeldAt(null);
    try {
      const felt = await nura.tapFeeling(bearer, papers.profile_id, word.word, language.value);
      // A word on the cloud is the check-in's answer: the hidden check-in is answered with it.
      if (nudge?.from === "handed" && nudge.kind === "check_in") {
        void nura.answerNudge(bearer, papers.profile_id, nudge.nudgeId, "accepted").catch(() => undefined);
      }
      if (felt.red_flag) return go({ name: "whatToDo", lines: felt.card ? whatToDoLines(felt.card) : felt.lines, offline: null, refusal: null });
      if (felt.question) return go({ name: "feeling", tap: felt });
      setSaid(felt.lines);
      setCloud(null);
    } catch (failure) {
      if (word.red) {
        const kept = await keptCards(papers.profile_id, bindingOf(papers));
        return go({ name: "whatToDo", ...whenNotReached("red_flag", failure, kept?.cards ?? null, papers.region, s, language.value) });
      }
      if (failure instanceof Unreachable) {
        // No network: held on the phone with the moment he tapped, the same way Taken is
        // (W4, #171) — carrying its own time, so a replay after the phone's midnight is
        // dropped by the queue itself rather than written under the wrong day. Sent once,
        // in order, by `useToday`'s own replay, the next time the network is back.
        const at = new Date().toISOString();
        await hold(papers.profile_id, { id: tapId(), kind: "feeling", word: word.word, language: language.value, at }, bindingOf(papers), new Date(), zoneOf(papers.region));
        setCloud(null);
        setHeldAt(at);
        return;
      }
      setError(failure);
    } finally {
      setBusy(false);
    }
  };

  /** His answer to the nudge. One the planner has not handed over yet is handed over first — the
   *  planner's own write — so the answer rests on the nudge row delivery reads. */
  const answer = async (kind: "accepted" | "dismissed") => {
    if (!bearer || !papers || !nudge || busy) return;
    setBusy(true);
    setError(null);
    try {
      let id: string;
      if (nudge.from === "handed") id = nudge.nudgeId;
      else {
        id = (await nura.handOverNudge(bearer, papers.profile_id)).nudge.nudge_id;
        // Handed over now: a second try answers this one, and never hands over twice.
        setNudge({ ...nudge, from: "handed", nudgeId: id });
      }
      await nura.answerNudge(bearer, papers.profile_id, id, kind);
      setNudge(null);
    } catch (failure) {
      setError(failure);
    } finally {
      setBusy(false);
    }
  };

  return (
    <>
      <Notice error={error} />
      {live && cloud && <FeelingStrip view={cloud} busy={busy} onTap={(word) => void tap(word)} />}
      {said.length > 0 && (
        <Tile paper role="status" testId="feeling-said">
          <div class="lines">
            {said.map((line, at) => (
              <p key={at}>{line}</p>
            ))}
          </div>
        </Tile>
      )}
      {/* A word tapped with no network: held on the phone, with when he tapped (W4, #171). */}
      {heldAt && (
        <Tile paper role="status" testId="held-feeling">
          <p>{fill(s.held.tapped, { time: clockWords(new Date(heldAt), language.value, zoneOf(papers?.region)) })}</p>
          <p>{s.held.held}</p>
        </Tile>
      )}
      {/* A check-in nudge asks what the cloud asks, and a word on the cloud is its answer: while
          the cloud is on Today, the cloud is the check-in. */}
      {live && nudge && !(nudge.kind === "check_in" && cloud) && <NudgeTile shown={nudge} busy={busy} onAnswer={(kind) => void answer(kind)} />}
      {records && (
        <Pill onClick={() => go({ name: "symptoms" })} testId="open-symptoms">
          {s.day.symptomsOpen}
        </Pill>
      )}
    </>
  );
}

/** Today's top three (E11-02): the backend's ranking — alerts, then reminders, then insights —
 *  stacked in its order under "For you today" (docs/ui-mockup-v2.html), each under its why. */
export function TopThree({ items }: { items: FeedItemOut[] }): JSX.Element | null {
  if (items.length === 0) return null;
  return (
    <div class="top-three" data-testid="top-three" data-count={items.length}>
      {items.map((item) => {
        const clips = clipsOf(item);
        const paper = density() === "patient" || item.supply === "flag";
        return clips.size > 0 ? (
          <ClipCard key={item.item_id} item={item} clips={clips} paper={paper} testId="top-three-card" />
        ) : (
          <Card
            key={item.item_id}
            title={item.headline}
            lines={feedLines(item).lines}
            boundary={feedLines(item).boundary}
            spoken={item.voice.length > 0 ? item.voice : undefined}
            provenance={whyLine(item)}
            paper={paper}
            testId="top-three-card"
          />
        );
      })}
    </div>
  );
}
