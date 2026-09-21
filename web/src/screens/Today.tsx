import { useEffect, useState } from "preact/hooks";
import { EmergencyCard } from "./Emergency";
import type { KeptCard } from "../offline/emergencyCache";
import { zoneOf } from "../offline/todayCache";
import type { JSX } from "preact";
import * as family from "../api/family";
import * as nura from "../api/nura";
import type { AppointmentOut, ChangesOut, FeedItemOut, LineOut, LogisticsOut, VisitQuestionOut } from "../api/types";
import { batch } from "../capture/session";
import { ClipCard } from "../day/components";
import { clipsOf } from "../day/model";
import { DayOnToday, NotWellButton, TopThree } from "../day/TodayDay";
import { go, openTab } from "../flow";
import { speak } from "../speech/speak";
import { density, isSelf, me, profile, token } from "../store/session";
import { fill, language, LOCALE, t, type Strings } from "../strings";
import {
  clockWords,
  lineTitle,
  dateChip,
  dateLine,
  dueCards,
  feedLines,
  greeting,
  heroFurnitureAllowed,
  homeHeadline,
  homeHero,
  homeState,
  nearestToRunOut,
  readingLead,
  stateLines,
  systolics,
  timeLine,
  todayList,
  topOfDay,
  weekdayOf,
  whyLine,
} from "../today/model";
import { useToday, type TodayView } from "../today/useToday";
import { Card, Hear, Notice, Tile } from "../ui/components";
import { Avatar, Chip, ChipRow, FeedCard, Glass, GlassTile, Icon, IconBadge, Orb, PanelList, PillButton, SectionLabel, SoftText, Sparkline, TintCard, toneOf } from "../ui/kit";
import { AddReport, CheckInCard, DoGrid, HomeSkeleton, Upcoming } from "./HomeParts";
import { Shell } from "./Shell";
import { ChiefPanels } from "./ChiefPanels";

/** Home (cp3-home, the living orb): his own Home in the patient's density, the chief's Home in
 *  the caregiver's — both read the same page (`useToday`) and both draw through `HomeHero`
 *  below, which is the one place that decides whose voice Home speaks in (`isSelf()`, never
 *  `density()`: a "Look" chosen for size or simplicity must never put the wrong voice in
 *  either mouth — the bug the owner found, "Ask about Tan" on Tan's own phone, was `density()`
 *  doing that job). Every line is the backend's or the catalogue's; nothing is drawn over a
 *  line; the safety line appears once (`SafetyNote` below, or the State card's own boundary
 *  when a State card is already on the page — never both). */
export function TodayScreen({ saved }: { saved?: boolean }): JSX.Element {
  return density() === "patient" ? <DadToday saved={saved ?? false} /> : <ChiefHome saved={saved ?? false} />;
}

/** His Home: the orb-led hero, "Now" for a dose due with its pill and a full-width Taken, the
 *  day's check-in, "For you today" in the card grammar, the next visit with what to bring, a
 *  note from the family, and the coral "Not well?" pill in the header, always there. */
function DadToday({ saved }: { saved: boolean }): JSX.Element {
  const v = useToday();
  const { s, page, blank, feed, fromPhone, unreached, top, useFeed, stateAt, nextVisit, papers } = v;
  const name = papers?.display_name || me.value?.display_name || "";
  // Safety check 5: while a red-flag card is on the page, nothing of the State may sit above
  // it — not even the hero's question or the daily check-in (today/model.ts:260-269).
  const flagged = feed.flags.length > 0;
  const furniture = heroFurnitureAllowed({ flagged });
  const showsBoundary = stateAt === "top" || stateAt === "now" || stateAt === "forYou";
  return (
    <Shell tab="home" testId="today-screen" topBar={{ variant: "home" }} ask={false} bottomBar={<HomeAskBar patientName={name} />}>
      <HomeHero v={v} patientName={name} />
      {page && <span data-testid="today-ready" hidden />}
      <Notices v={v} saved={saved} />
      <Held v={v} />
      {!page && !blank && !v.error && <HomeSkeleton />}
      {blank ? (
        <Blank s={s} card={v.card} />
      ) : (
        page && (
          <>
            {feed.flags.map((item) => (
              <FeedItemCard key={item.item_id} item={item} v={v} testId="flag-card" />
            ))}
            {stateAt === "top" && <StateCard v={v} />}
            {furniture && <CheckInCard papers={papers} />}
            <DoGrid papers={papers} />
            <AddReport papers={papers} />
            {nextVisit && !fromPhone && (
              <Upcoming papers={papers}>
                <VisitTile visit={nextVisit} />
              </Upcoming>
            )}
            {/* His doses now, under what the approved board puts first. */}
            <DoseSection v={v} />
            <SectionLabel>{s.today.forYou}</SectionLabel>
            {!fromPhone && top.length > 0 ? (
              <TopThree items={top} />
            ) : (
              useFeed && feed.forYou.map((item) => <FeedItemCard key={item.item_id} item={item} v={v} testId="feed-card" />)
            )}
            {stateAt === "forYou" && <StateCard v={v} />}
            {!fromPhone && (
              <Card
                title={s.today.readingTitle}
                lines={[readingLead(v.now.getHours(), s)]}
                testId="reading-prompt"
                action={
                  <PillButton onClick={() => go({ name: "reading" })} testId="write-reading">
                    {s.today.readingButton}
                  </PillButton>
                }
              />
            )}
            <PillButton onClick={() => go({ name: "feed" })} testId="open-feed">
              {s.feed.open}
            </PillButton>
            <DayOnToday stateId={page.stateId} live={!fromPhone && unreached === null} />
            {!fromPhone && <FamilyNote />}
            {/* The emergency card, one tap from Home, with no network too (W4). */}
            <PillButton onClick={() => go({ name: "emergency" })} testId="open-emergency">
              {s.today.emergencyOpen}
            </PillButton>
            {!showsBoundary && <SafetyNote boundary={page.boundary} />}
          </>
        )
      )}
    </Shell>
  );
}

/** The chief's Home: the same orb-led hero speaking of him by name, the State's drivers and his
 *  blood pressures as a sparkline once there is a State card to carry them, what changed since
 *  she last looked, the next visit and what to buy side by side, what the papers are missing,
 *  then the doses she may tap for him, and today's cards. */
function ChiefHome({ saved }: { saved: boolean }): JSX.Element {
  const v = useToday();
  const { s, page, blank, feed, fromPhone, unreached, top, useFeed, nextVisit, stateAt, papers } = v;
  const bearer = token.value;
  const drivers = page?.drivers ?? [];
  const flagged = feed.flags.length > 0;
  const furniture = heroFurnitureAllowed({ flagged });
  const hero = page ? homeHero(page, { flagged, kept: fromPhone }, s) : null;
  const state = page !== null && page.stateId !== null && Boolean(page.word) && hero !== null;
  const showsBoundary = stateAt === "top" || stateAt === "forYou";
  const patientName = papers?.display_name || "";
  return (
    <Shell tab="home" testId="home-screen" topBar={{ variant: "home" }} ask={false} bottomBar={<HomeAskBar patientName={patientName} />}>
      {page && <span data-testid="today-ready" hidden />}
      <HomeHero v={v} patientName={patientName} />
      {/* Her Home's State word (docs/design/full-experience.html): shown whenever there is a
          current State to show (`homeHero`'s own flagged/kept rule — unchanged from before
          cp3-home), never gated on `stateAt`, which decides only where the *State card itself*
          lands among today's cards, not whether the word is reachable at all. Its provenance
          line is here, as it always was; the safety/boundary sentences themselves are not —
          those stay exactly once, on the State card when `stateAt` puts one on the page, else
          in `SafetyNote` at the foot (below). */}
      {state && page && hero && (
        <div class="panel-stack" data-testid="home-state">
          {hero.word && (
            <p class="home-state-word">
              <strong>{hero.word}</strong>
              {hero.line && <span> — {hero.line}</span>}
            </p>
          )}
          <Readings />
          {hero.drivers && drivers.length > 0 && (
            <ChipRow testId="drivers" label={s.home.mostLikely}>
              {drivers.map((driver) => (
                <Chip key={driver.key} tone={toneOf(driver.tone)}>
                  {driver.text}
                </Chip>
              ))}
            </ChipRow>
          )}
          {hero.word && (
            <p class="hero-sub" data-testid="home-from">
              {fill(s.today.fromState, { date: dateLine(new Date(page.computedAt ?? page.fetchedAt), LOCALE[language.value]) })}
            </p>
          )}
        </div>
      )}
      <Notices v={v} saved={saved} />
      <Held v={v} />
      {!page && !blank && !v.error && <HomeSkeleton />}
      {blank ? (
        <Blank s={s} card={v.card} />
      ) : (
        page && (
          <>
            {feed.flags.map((item) => (
              <FeedItemCard key={item.item_id} item={item} v={v} testId="flag-card" />
            ))}
            {(stateAt === "top" || stateAt === "forYou") && <StateCard v={v} />}
            {/* The reference's own order for her Home (docs/design/full-experience.html, the
                Mei persona): under the State, what changed since she last looked, his next
                visit and what to buy side by side, the gap in his papers, then what Nura is
                watching for him and what was sent to him this week — before the warm grid
                everyone's Home shares. */}
            {/* "What changed since you last looked" (docs/design-system.md §3): a peek, not a
                look (#207) — `GET /changes` is the looking, and a tile that draws itself on
                every Home render is not her choosing to look, so it reads with `peek=true`
                and marks nothing. The Record's own "what changed" screen is the one place
                that marks a look, because reading it is what she came there to do. */}
            <WhatChanged />
            <NextVisitAndReorder visit={!fromPhone ? nextVisit : null} lines={page.lines} />
            {nextVisit && !fromPhone && <GapsTile visit={nextVisit} />}
            {/* The chief's Home (F1, #177): what was sent to him this week, and what Nura is
                watching for him. Her key's and his steward's; nobody else's. */}
            {!fromPhone && bearer && v.papers && (v.papers.role === "chief" || v.papers.standing === "steward") && <ChiefPanels bearer={bearer} papers={v.papers} />}
            {furniture && <CheckInCard papers={papers} />}
            <DoGrid papers={papers} />
            <AddReport papers={papers} />
            {/* His doses, only for a key that may tap Taken for him (one that opens the medicines). */}
            {v.papers?.scopes.includes("medicines") && <DoseSection v={v} />}
            <SectionLabel>{s.today.forYou}</SectionLabel>
            {!fromPhone && top.length > 0 ? (
              <TopThree items={top} />
            ) : (
              useFeed && feed.forYou.map((item) => <FeedItemCard key={item.item_id} item={item} v={v} testId="feed-card" />)
            )}
            <PillButton onClick={() => go({ name: "feed" })} testId="open-feed">
              {s.feed.open}
            </PillButton>
            {/* His emergency card, one tap from Home — hers as much as his (W4). */}
            <PillButton onClick={() => go({ name: "emergency" })} testId="open-emergency">
              {s.today.emergencyOpen}
            </PillButton>
            <DayOnToday stateId={page.stateId} live={!fromPhone && unreached === null} />
            {!showsBoundary && <SafetyNote boundary={page.boundary} />}
          </>
        )
      )}
    </Shell>
  );
}

/** Home's header, hero and docked ask bar (cp3-home): the one block both densities share, and
 *  the one place whose-voice is decided — `isSelf()` (store/session.ts), never `density()`.
 *  Either a patient-density screen or a caregiver-density one can be open for either standing
 *  (Me's own "Look" pills are not gated by who owns the papers), so both `DadToday` and
 *  `ChiefHome` read this the same way rather than each assuming which voice it is. */
function HomeHero({ v, patientName }: { v: TodayView; patientName: string }): JSX.Element {
  const { s, page, feed, act, top, now, nextVisit, papers, dose, busy, take } = v;
  const self = isSelf();
  const locale = LOCALE[language.value];
  // His own greeting names him; hers names her — the person the greeting is *from* is always
  // whoever is signed in, never the papers' name on a caregiver's own Home.
  const greetName = self ? patientName || me.value?.display_name || "" : me.value?.display_name || "";
  const question = self ? s.hub.howFeeling : fill(s.hub.howFeelingOther, { patient: patientName });
  const flagged = feed.flags.length > 0;
  const topItem = page ? topOfDay(top, feed.forYou) : null;
  const state = homeState({ flagged, act, topItem });
  const dueNow = dose?.kind === "due" ? dose : null;
  const forYouItem = feed.forYou.find((item) => item.item_id !== topItem?.item_id) ?? null;
  return (
    <>
      <div class="home-head" data-testid="home-head">
        <Avatar name={greetName} />
        <div class="home-head-text">
          <p class="home-head-hello" data-testid="home-head-hello">{greeting(now.getHours(), greetName, s)}</p>
          <h1 class="home-head-question">{question}</h1>
          <p class="home-head-date" data-testid="home-head-date">{dateLine(now, locale)}</p>
        </div>
        {/* The way in when he feels unwell comes before anything ranked (red flags escalate
            first): unchanged behaviour, unchanged test id, no animation on the red path. */}
        <NotWellButton />
      </div>
      {page && state === "busy" && topItem && (
        <div data-testid={self ? "today-hero" : "home-hero"}>
          <span class="home-kick">{s.home.todayKicker}</span>
          <SoftText as="h2" pace="headline" className="home-headline" text={homeHeadline(topItem)} testId="home-headline" />
          <Glass className="home-insight" testId="insight-card">
            <h3>{self ? s.home.insightTitle : fill(s.home.insightTitleOther, { patient: patientName })}</h3>
            <div class="home-insight-body">
              <div class="home-date-chip" aria-hidden="true">
                <b>{dateChip(new Date(topItem.created_at), locale).day}</b>
                <small>{dateChip(new Date(topItem.created_at), locale).month}</small>
              </div>
              <div class="home-insight-lines">
                {feedLines(topItem).lines.slice(0, 2).map((line, at) => (
                  <p key={at}>{line}</p>
                ))}
              </div>
            </div>
            {/* Not `variant="primary"`: the daily check-in's own "Tell Nura" (`HomeParts.tsx`)
                is already the screen's one Plum-filled button when it is on the page too, and
                the design rule (`design.spec.ts`) is at most one. */}
            <PillButton variant="secondary" onClick={() => go({ name: "feed" })} testId="insight-open">
              {s.home.insightOpen}
            </PillButton>
          </Glass>
          {dueNow && (
            <button type="button" class="home-row" onClick={() => void take(dueNow.lineId, dueNow.anchor)} disabled={busy} data-testid="home-row-dose">
              <span>{dueNow.sentence}</span>
              <Icon name="chevron" />
            </button>
          )}
          {forYouItem && (
            <button type="button" class="home-row" onClick={() => go({ name: "feed" })} data-testid="home-row-for-you">
              <span>{forYouItem.headline}</span>
              <Icon name="chevron" />
            </button>
          )}
        </div>
      )}
      {page && state === "quiet" && (
        <div class="home-quiet" data-testid={self ? "today-hero" : "home-hero"}>
          <Orb size="lg" testId="home-orb-lg" />
          <SoftText as="h2" pace="headline" className="home-quiet-greeting" text={greeting(now.getHours(), greetName, s)} testId="quiet-greeting" />
          <SoftText
            as="p"
            pace="body"
            className="home-quiet-prompt"
            text={self ? s.home.quietPrompt : fill(s.home.quietPromptOther, { patient: patientName })}
          />
          <div class="chip-row quiet-chips" data-testid="quiet-chips">
            <ReportChip label={s.home.chipReport} />
            {papers && (papers.standing === "owner" || papers.scopes.includes("medicines")) && (
              <button type="button" class="glass-chip chip-button" onClick={() => go({ name: "record", at: { name: "medicines" } })} data-testid="chip-medicines">
                {self ? s.home.chipMedicines : fill(s.home.chipMedicinesOther, { patient: patientName })}
              </button>
            )}
            {nextVisit && (
              <button
                type="button"
                class="glass-chip chip-button"
                onClick={() => go({ name: "visit", appointmentId: nextVisit.appointment_id })}
                data-testid="chip-visit"
              >
                {self ? s.home.chipVisit : fill(s.home.chipVisitOther, { patient: patientName })}
              </button>
            )}
            <button type="button" class="glass-chip chip-button" onClick={() => openTab("health")} data-testid="chip-week">
              {self ? s.home.chipWeek : fill(s.home.chipWeekOther, { patient: patientName })}
            </button>
          </div>
        </div>
      )}
    </>
  );
}

/** "Read a report", the quiet day's own chip: the same picker `AddReport` (HomeParts.tsx)
 *  opens, styled as a chip rather than a row — one file, straight to its own review card,
 *  never sent until he says so there (reviewer #237 item 6). */
function ReportChip({ label }: { label: string }): JSX.Element {
  const chosen = (event: Event) => {
    const input = event.currentTarget as HTMLInputElement;
    const file = input.files?.[0];
    input.value = "";
    if (!file) return;
    batch.forget();
    batch.pick([file]);
    go({ name: "papers", report: true });
  };
  return (
    <label class="glass-chip chip-button" data-testid="chip-report">
      {label}
      <input type="file" accept="application/pdf,image/*" onChange={chosen} />
    </label>
  );
}

/** Home's own ask bar (cp3-home), docked above the tab bar (`Shell`'s `bottomBar`): the small
 *  living orb, "Ask Nura anything" (caregiver: "Ask about Pa" — `shell.askAbout`, the same
 *  template the header's old ask bar used), and Speak, unchanged in behaviour from `AskField`'s
 *  own voice button. Two buttons, never one nested in another. */
function HomeAskBar({ patientName }: { patientName: string }): JSX.Element {
  const s = t();
  const self = isSelf();
  const word = self ? s.home.askNura : fill(s.shell.askAbout, { name: patientName });
  return (
    <div class="home-ask" data-testid="home-ask-bar">
      <Orb testId="home-ask-orb" />
      <button type="button" class="home-ask-word" onClick={() => go({ name: "ask" })} data-testid="home-ask-open">
        {word}
      </button>
      <button
        type="button"
        class="home-ask-speak"
        onClick={() => {
          speak({ lines: [s.shell.voiceSaid1, s.shell.voiceSaid2], language: language.value });
          go({ name: "ask" });
        }}
        data-testid="home-ask-speak"
      >
        <Icon name="mic" />
        <span>{s.shell.voice}</span>
      </button>
    </div>
  );
}

/** The safety line, once (cp3-home): the State's own boundary — never invented here — shown at
 *  the foot of the scroll when no State card already carries it (`showsBoundary` above). A
 *  State card that is on the page always carries its own boundary already; this is never drawn
 *  beside one, only in its place. */
function SafetyNote({ boundary }: { boundary: readonly string[] }): JSX.Element | null {
  if (boundary.length === 0) return null;
  return (
    <p class="home-safety-note" data-testid="home-safety-note">
      {boundary.join(" ")}
    </p>
  );
}

// --- the pieces both read ------------------------------------------------------------------

/** What happened to the taps held while offline (W4): a no said in the backend's words, the
 *  held taps sent, or still held when no dose on screen shows it. */
function Held({ v }: { v: TodayView }): JSX.Element | null {
  const { s, held, sent, heldRefused, heldSlots } = v;
  return (
    <>
      {heldRefused.length > 0 && (
        <div data-testid="held-refused">
          {heldRefused.map((failure, at) => (
            <Notice key={at} error={failure} />
          ))}
        </div>
      )}
      {sent && held.length === 0 && (
        <Tile paper role="status" testId="held-sent">
          <p>{s.held.sent}</p>
        </Tile>
      )}
      {held.length > 0 && heldSlots.length === 0 && (
        <Tile paper role="status" testId="held">
          <p>{s.held.held}</p>
        </Tile>
      )}
    </>
  );
}

function Notices({ v, saved }: { v: TodayView; saved: boolean }): JSX.Element {
  const { s, kept, unreached, page, error } = v;
  const locale = LOCALE[language.value];
  return (
    <>
      {unreached && kept && page && (
        <Tile glass testId="offline">
          <p>{unreached === "network" ? s.today.offline : s.today.cannotReach}</p>
          <p>{s.today.offlineSub}</p>
          <p class="caption">{fill(s.today.asOf, { date: dateLine(new Date(kept.fetchedAt), locale), time: timeLine(new Date(kept.fetchedAt), locale) })}</p>
        </Tile>
      )}
      {saved && (
        <Tile paper>
          <p>{s.reading.saved}</p>
        </Tile>
      )}
      <Notice error={error} />
    </>
  );
}

/** Past midnight with no network: one line, and where the emergency card is. */
function Blank({ s, card }: { s: Strings; card: KeptCard | null }): JSX.Element {
  return (
    <>
      <Card lines={[s.today.cannotReach]} testId="cannot-reach" />
      {card ? <EmergencyCard kept={card} /> : <Card title={s.today.emergencyTitle} lines={[s.today.emergencySoon]} testId="emergency-placeholder" />}
    </>
  );
}

/** One of the feed's cards in the card grammar: its headline, its lines, its boundary, why it
 *  is here, and its spoken twin. A card with a consult clip keeps its player under its line. */
function FeedItemCard({ item, v, testId }: { item: FeedItemOut; v: TodayView; testId: string }): JSX.Element {
  const clips = clipsOf(item);
  const paper = density() === "patient" || item.supply === "flag";
  if (clips.size > 0) return <ClipCard item={item} clips={clips} paper={paper} testId={testId} />;
  const shown = feedLines(item);
  return (
    <FeedCard
      title={item.headline}
      lines={shown.lines}
      boundary={shown.boundary}
      why={whyLine(item)}
      paper={paper}
      testId={testId}
      hear={<Hear lines={item.voice.length > 0 ? item.voice : [item.headline, ...shown.lines, ...shown.boundary].filter(Boolean)} />}
    />
  );
}

function StateCard({ v }: { v: TodayView }): JSX.Element | null {
  const { s, page, feed, fromPhone, act } = v;
  if (!page) return null;
  const locale = LOCALE[language.value];
  return (
    <Card
      lines={stateLines(page, s, { flagAbove: feed.flags.length > 0, kept: fromPhone })}
      boundary={page.boundary ?? []}
      provenance={fill(s.today.fromState, { date: dateLine(new Date(page.computedAt ?? page.fetchedAt), locale) })}
      paper={density() === "patient" || act}
      testId="state-card"
    />
  );
}

/** "Now": a tile for each dose the backend marks due, each with its pill, its sentence, its
 *  source and a full-width Taken; else what the day says instead (earlier today, all taken,
 *  nothing right now). A kept page lists the day and offers no Taken. */
export function DoseSection({ v }: { v: TodayView }): JSX.Element | null {
  const { s, page, fromPhone, stateAt, dose, doseSource, justTook, busy, take } = v;
  if (!page) return null;
  // A dose he tapped with no network has its own held card (below) and must not also stand here
  // as still due — the same slots `dose` is worked out from (`useToday`), less the held ones.
  const due = dose?.kind === "due" ? dueCards(page.slots.filter((slot) => v.heldTapOf(slot) === undefined), page.lines, s) : [];
  return (
    <>
      <SectionLabel>{s.today.now}</SectionLabel>
      {fromPhone &&
        (page.slots.length > 0 ? (
          <Card title={s.today.todayList} lines={todayList(page.slots)} provenance={s.today.fromToday} testId="today-list" />
        ) : (
          <Card title={s.today.noMedicines} lines={[s.today.noMedicinesSub]} testId="no-medicines" />
        ))}
      {stateAt === "now" && <StateCard v={v} />}
      {/* A dose tapped with no network: held on the phone, with when he tapped (W4). */}
      {v.heldSlots.map((slot) => (
        <Card
          key={`${slot.line_id}:${slot.anchor}`}
          title={lineTitle(page.lines.find((line) => line.line_id === slot.line_id), s)}
          lines={[slot.card]}
          provenance={slot.source}
          testId="held-card"
          action={
            <div class="lines" role="status" data-testid="held">
              <p>{fill(s.held.tapped, { time: clockWords(new Date(v.heldTapOf(slot)!.at), language.value, zoneOf(v.papers?.region)) })}</p>
              <p>{s.held.held}</p>
            </div>
          }
        />
      ))}
      {due.map((one) => (
        <FeedCard
          key={`${one.lineId}:${one.anchor}`}
          icon="pill"
          title={one.title}
          lines={[one.sentence]}
          source={one.provenance}
          testId="now-card"
          action={
            <PillButton onClick={() => void take(one.lineId, one.anchor)} disabled={busy} testId="taken">
              {v.papers?.standing === "owner" ? s.today.taken : one.takenLabel || s.today.taken}
            </PillButton>
          }
          hear={<Hear lines={[one.title, one.sentence]} />}
        />
      ))}
      {dose?.kind === "missed" && (
        <>
          <SectionLabel>{s.today.earlierTitle}</SectionLabel>
          <Card title={dose.title} lines={dose.lines} provenance={dose.provenance} testId="missed-card" />
        </>
      )}
      {dose?.kind === "allTaken" && <Card title={s.today.allTaken} lines={[justTook ?? s.today.allTakenSub]} provenance={doseSource} settled testId="all-taken" />}
      {dose?.kind === "nothingNow" && <Card lines={[justTook ?? s.today.nothingNow]} provenance={doseSource} testId="nothing-now" />}
      {dose?.kind === "none" && <Card title={s.today.noMedicines} lines={[s.today.noMedicinesSub]} testId="no-medicines" />}
      {justTook && (dose?.kind === "due" || dose?.kind === "missed") && (
        <Tile paper settled>
          <p>{justTook}</p>
        </Tile>
      )}
    </>
  );
}

/** The next visit's logistics card, as the backend wrote it (E05-03), or null. */
function useLogistics(visit: AppointmentOut): LogisticsOut | null {
  const bearer = token.value;
  const papers = profile.value;
  const [card, setCard] = useState<LogisticsOut | null>(null);
  useEffect(() => {
    if (!bearer || !papers) return;
    nura.logistics(bearer, papers.profile_id, visit.appointment_id).then(setCard, () => setCard(null));
  }, [bearer, papers?.profile_id, visit.appointment_id, language.value]);
  return card;
}

// --- his Today ---------------------------------------------------------------------------

/** The next visit on his Today: when, where and who drives him, as the logistics card says,
 *  what to bring as chips, and the way into the visit. Paper: a date and an action are on it. */
function VisitTile({ visit }: { visit: AppointmentOut }): JSX.Element {
  const s = t();
  const card = useLogistics(visit);
  const when = card?.lines.find((line) => line.section === "when");
  const about = card?.lines.filter((line) => line.section === "place" || line.section === "driver") ?? [];
  const bring = card?.lines.filter((line) => line.section === "bring") ?? [];
  const spoken = card?.lines.map((line) => line.spoken).filter(Boolean) ?? [];
  return (
    <TintCard tint="peach" testId="visit-tile" extra="visit-card">
      <div class="card-row">
        <IconBadge icon="calendar" tint="paper" />
        <h3 class="card-title grow">{when?.text ?? s.visit.title}</h3>
      </div>
      {about.length > 0 && (
        <div class="lines visit-lines">
          {about.map((line, at) => (
            <p key={at}>{line.text}</p>
          ))}
        </div>
      )}
      {bring.length > 0 && (
        <ChipRow testId="bring">
          {bring.map((line, at) => (
            <Chip key={at}>{line.text}</Chip>
          ))}
        </ChipRow>
      )}
      <PillButton onClick={() => go({ name: "visit", appointmentId: visit.appointment_id })} testId="open-visit">
        {s.visit.open}
      </PillButton>
      {spoken.length > 0 && (
        <div class="card-foot">
          <Hear lines={spoken} />
        </div>
      )}
    </TintCard>
  );
}

/** "From Mei": the newest thing someone in his family wrote to the thread, in their words, under
 *  their name — presence, not a report. His own phone only; nothing when there is nothing. */
function FamilyNote(): JSX.Element | null {
  const s = t();
  const bearer = token.value;
  const papers = profile.value;
  const [note, setNote] = useState<{ name: string; text: string } | null>(null);
  useEffect(() => {
    if (!bearer || !papers || papers.standing !== "owner") return setNote(null);
    const read = async () => {
      const found = await family.thread(bearer, papers.profile_id, 10);
      const mine = me.value?.person_id;
      const entry = found.entries.find((each) => each.text && each.author_person_id !== mine);
      if (!entry?.text) return setNote(null);
      const held = await nura.keys(bearer, papers.profile_id);
      const name = held.find((key) => key.holder_person_id === entry.author_person_id)?.holder_display_name;
      setNote(name ? { name, text: entry.text } : null);
    };
    read().catch(() => setNote(null));
  }, [bearer, papers?.profile_id]);
  if (!note) return null;
  const title = fill(s.home.fromName, { name: note.name });
  return (
    <GlassTile testId="family-note">
      <div class="note-head">
        <Avatar name={note.name} />
        <h2 class="title">{title}</h2>
      </div>
      <p>{note.text}</p>
      <div class="card-foot">
        <Hear lines={[title, note.text]} />
      </div>
    </GlassTile>
  );
}

// --- the chief's Home --------------------------------------------------------------------

/** His blood pressures (the top number), oldest first, as the backend holds them. */
function Readings(): JSX.Element | null {
  const s = t();
  const bearer = token.value;
  const papers = profile.value;
  const [values, setValues] = useState<number[]>([]);
  useEffect(() => {
    if (!bearer || !papers || !papers.scopes.includes("readings")) return setValues([]);
    nura.facts(bearer, papers.profile_id, "blood_pressure").then(
      (found) => setValues(systolics(found)),
      () => setValues([]),
    );
  }, [bearer, papers?.profile_id]);
  if (values.length < 2) return null;
  return <Sparkline values={values} label={fill(s.home.bpLast, { number: String(values[values.length - 1]) })} caption={s.home.bpLabel} />;
}

/** How many of what changed Home shows before "See all": the mockup's three, and one more. */
const CHANGES_SHOWN = 4;

/** What changed since she last looked (reading it is looking): each line the backend's, with the
 *  dot of its tone — Act, Watch, Good, or none. Read once each time Home opens. */
function WhatChanged(): JSX.Element | null {
  const s = t();
  const bearer = token.value;
  const papers = profile.value;
  const [found, setFound] = useState<ChangesOut | null>(null);
  const [all, setAll] = useState(false);
  useEffect(() => {
    if (!bearer || !papers) return;
    // A peek (#207): the same words `GET /changes` always says, but Home draws this tile on
    // every render, and a glance she did not choose is not a look — it marks nothing and
    // leaves no entry on his trail. The Record's own "what changed" screen is the one place
    // that marks a look, because reading it is what she came there to do.
    nura.changes(bearer, papers.profile_id, language.value, true).then(setFound, () => setFound(null));
  }, [bearer, papers?.profile_id]);
  if (!found) return null;
  const rows = [...found.lines, ...found.waiting].map((line, at) => ({ key: `${line.section}:${line.key}:${at}`, text: line.text, tone: toneOf(line.tone ?? null), dotted: true }));
  if (rows.length === 0) return null;
  const hidden = rows.length - CHANGES_SHOWN;
  return (
    <div class="panel-stack">
      <PanelList title={s.home.whatChanged} rows={all || hidden <= 0 ? rows : rows.slice(0, CHANGES_SHOWN)} paper testId="what-changed" />
      {hidden > 0 && (
        <PillButton variant="quiet" compact onClick={() => setAll(!all)} pressed={all} testId="what-changed-all">
          {all ? s.home.showFewer : fill(s.home.showAll, { count: String(rows.length) })}
        </PillButton>
      )}
    </div>
  );
}

/** "Ask about Pa" at the foot of her Home (docs/ui-mockup.html): the ask screen, empty, for a
 *  question of her own. The bar on top asks too; this is the one her thumb reaches. */
function AskAboutPill(): JSX.Element | null {
  const s = t();
  const papers = profile.value;
  if (!papers) return null;
  return (
    <PillButton icon="search" onClick={() => go({ name: "ask" })} testId="ask-about">
      {fill(s.shell.askAbout, { name: papers.display_name })}
    </PillButton>
  );
}

/** The next visit as a figure — its day and time — and where, as the logistics card says. Its
 *  date and its time are two lines, never one joined by a symbol to decode (plain words): the
 *  date a whole line on its own, the time under it in `home.atTime`. */
export function NextVisitTile({ visit }: { visit: AppointmentOut }): JSX.Element {
  const s = t();
  const locale = LOCALE[language.value];
  const at = new Date(visit.scheduled_at);
  // One row, as the board draws "Coming up": who and where, then the day and the time; the whole
  // card is the way into the visit. The weekday is said once (never twice).
  return (
    <TintCard tint="peach" testId="next-visit-tile" extra="visit-card">
      <button type="button" class="card-row card-button" onClick={() => go({ name: "visit", appointmentId: visit.appointment_id })} data-testid="open-visit">
        <IconBadge icon="calendar" tint="paper" />
        <span class="grow">
          <span class="card-title">{visit.doctor || weekdayOf(at, locale)}</span>
          <span class="card-line" data-testid="next-visit-date">{dateLine(at, locale)}</span>
          <span class="card-line">{fill(s.home.atTime, { time: timeLine(at, locale) })}</span>
        </span>
        <Icon name="chevron" />
      </button>
      {visit.purpose && <p class="card-line">{visit.purpose}</p>}
    </TintCard>
  );
}

/** The reference's row of two on her Home (docs/design/full-experience.html, the Mei persona):
 *  his next visit and what to buy, side by side, neither under "Coming up" — each a small card
 *  of its own. Either may be missing (no visit booked, nothing near running out); with only one,
 *  it takes the row alone rather than leaving an empty column beside it. */
export function NextVisitAndReorder({ visit, lines }: { visit: AppointmentOut | null; lines: readonly LineOut[] }): JSX.Element | null {
  const showSupply = Boolean(nearestToRunOut(lines)?.count);
  if (!visit && !showSupply) return null;
  return (
    <div class={visit && showSupply ? "two-up" : undefined} data-testid="next-visit-and-reorder">
      {visit && <NextVisitTile visit={visit} />}
      {showSupply && <SupplyTile lines={lines} />}
    </div>
  );
}

/** What to buy: the medicine nearest to running out, its count as the figure (Watch when it is
 *  time to buy more), and the backend's sentence under it. */
function SupplyTile({ lines }: { lines: readonly LineOut[] }): JSX.Element | null {
  const s = t();
  const nearest = nearestToRunOut(lines);
  const count = nearest?.count;
  if (!count) return null;
  return (
    <TintCard tint="sage" testId="supply-tile">
      <button type="button" class="tile-link" onClick={() => go({ name: "record", at: { name: "medicines" } })} data-testid="open-medicines">
        <span class="tile-title">{s.home.buyMore}</span>
        <Icon name="chevron" />
      </button>
      <p class="card-figure" data-tone={count.reorder_due ? "watch" : undefined}>
        <span class="number">{count.remaining}</span>
      </p>
      <div class="lines">
        {count.lines.map((line, at) => (
          <p key={at} class="source-line">
            {line}
          </p>
        ))}
      </div>
    </TintCard>
  );
}

/** What the papers are missing, as the questions Nura already added for the next visit. */
function GapsTile({ visit }: { visit: AppointmentOut }): JSX.Element | null {
  const s = t();
  const bearer = token.value;
  const papers = profile.value;
  const [gaps, setGaps] = useState<VisitQuestionOut[]>([]);
  useEffect(() => {
    if (!bearer || !papers) return;
    nura.visitQuestions(bearer, papers.profile_id, visit.appointment_id).then(
      (found) => setGaps(found.questions.filter((question) => !question.removed && question.source === "gap")),
      () => setGaps([]),
    );
  }, [bearer, papers?.profile_id, visit.appointment_id, language.value]);
  if (gaps.length === 0) return null;
  const day = dateLine(new Date(visit.scheduled_at), LOCALE[language.value]);
  return <PanelList title={s.home.missing} rows={gaps.map((gap) => ({ key: gap.question_id, text: gap.text }))} note={visit.doctor ? fill(s.home.missingSub, { doctor: visit.doctor, date: day }) : fill(s.home.missingSubDay, { date: day })} testId="gaps" />;
}
