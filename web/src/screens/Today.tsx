import { useEffect, useRef, useState } from "preact/hooks";
import { focusHeading } from "../ui/focus";
import { EmergencyCard } from "./Emergency";
import type { KeptCard } from "../offline/emergencyCache";
import { emergencyOnly } from "../offline/emergencyCache";
import { zoneOf } from "../offline/todayCache";
import type { JSX } from "preact";
import * as family from "../api/family";
import * as nura from "../api/nura";
import type { AppointmentOut, ChangesOut, FeedItemOut, LineOut, LogisticsOut, VisitQuestionOut } from "../api/types";
import { batch } from "../capture/session";
import { ClipCard } from "../day/components";
import { clipsOf } from "../day/model";
import { DayOnToday, NotWellButton, TopThree } from "../day/TodayDay";
import { go, openMe, openTab } from "../flow";
import { speak } from "../speech/speak";
import { density, isSelf, me, profile, token } from "../store/session";
import { fill, language, LOCALE, t, type Strings } from "../strings";
import { rangeStatus } from "../onboarding/review";
import {
  clockWords,
  lineTitle,
  dateChip,
  dateLine,
  dayKey,
  dueCards,
  feedLines,
  greeting,
  heroFurnitureAllowed,
  homeHeadlineFor,
  homeHero,
  insightExtraLines,
  homeState,
  homeTopItem,
  homeTopItemDate,
  nearestToRunOut,
  readingLead,
  stateLines,
  systolics,
  timeLine,
  todayList,
  weekdayOf,
  whyLine,
  type HomeTopItem,
  type PaperSummary,
} from "../today/model";
import { useToday, type TodayView } from "../today/useToday";
import { Card, Hear, Notice, Tile } from "../ui/components";
import { Avatar, Chip, ChipRow, FeedCard, Glass, GlassTile, Icon, IconBadge, Orb, PanelList, PillButton, SectionLabel, SoftText, Sparkline, TintCard, toneOf } from "../ui/kit";
import { AddReport, CheckInCard, DoGrid, HomeSkeleton, Upcoming } from "./HomeParts";
import { BellButton, Shell } from "./Shell";
import { ProfileSwitcher } from "./Switcher";
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
  const voice = homeVoice(v, name);
  const hero = useHomeHero(v, name, voice);
  return (
    <Shell
      tab="home"
      testId="today-screen"
      header={<HomeTopBar voice={voice} quiet={hero.ready && hero.state === "quiet"} />}
      ask={false}
      bottomBar={<HomeAskBar patientName={name} />}
    >
      <HomeHero v={v} patientName={name} voice={voice} hero={hero} />
      {page && <span data-testid="today-ready" hidden />}
      <Notices v={v} saved={saved} />
      <Held v={v} />
      {/* Fix #1 (owner review round 3): the calm skeleton stays until Home's own busy/quiet
          decision is actually ready, not only until `page` lands — the flash the owner found
          was the quiet state painting first, as a placeholder, while a slower input (the
          visits read, today's own reading, a confirmed paper's range summary) was still on
          its way. Header and ask bar need none of this (`Shell`'s own props, above) and never
          wait for it. */}
      {(!page || !hero.ready) && !blank && !v.error && <HomeSkeleton />}
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
  const stateHero = page ? homeHero(page, { flagged, kept: fromPhone }, s) : null;
  const state = page !== null && page.stateId !== null && Boolean(page.word) && stateHero !== null;
  const showsBoundary = stateAt === "top" || stateAt === "forYou";
  const patientName = papers?.display_name || "";
  const voice = homeVoice(v, patientName);
  const hero = useHomeHero(v, patientName, voice);
  return (
    <Shell
      tab="home"
      testId="home-screen"
      header={<HomeTopBar voice={voice} quiet={hero.ready && hero.state === "quiet"} />}
      ask={false}
      bottomBar={<HomeAskBar patientName={patientName} />}
    >
      {page && <span data-testid="today-ready" hidden />}
      <HomeHero v={v} patientName={patientName} voice={voice} hero={hero} />
      {/* Her Home's State word (docs/design/full-experience.html): shown whenever there is a
          current State to show (`homeHero`'s own flagged/kept rule — unchanged from before
          cp3-home), never gated on `stateAt`, which decides only where the *State card itself*
          lands among today's cards, not whether the word is reachable at all. Its provenance
          line is here, as it always was; the safety/boundary sentences themselves are not —
          those stay exactly once, on the State card when `stateAt` puts one on the page, else
          in `SafetyNote` at the foot (below). */}
      {state && page && stateHero && (
        <div class="panel-stack" data-testid="home-state">
          {/* The state's own word and its provenance line (owner review round 3, fix #4): shown
              only while a posture actually leads (act or watch — "unchanged" per the owner) —
              stable's own "Steady — nothing needs doing" was the leftover boilerplate the owner
              found on the first screen, in both the busy and the quiet state. The word and its
              provenance are still reachable through the existing State card route
              (`stateAt === "top"`, below) and the why sheet; the drivers and the sparkline are
              real data, not boilerplate, and stay exactly as they were. */}
          {stateHero.word && (page.posture === "act" || page.posture === "watch") && (
            <p class="home-state-word">
              <strong>{stateHero.word}</strong>
              {stateHero.line && <span> — {stateHero.line}</span>}
            </p>
          )}
          <Readings />
          {stateHero.drivers && drivers.length > 0 && (
            <ChipRow testId="drivers" label={s.home.mostLikely}>
              {drivers.map((driver) => (
                <Chip key={driver.key} tone={toneOf(driver.tone)}>
                  {driver.text}
                </Chip>
              ))}
            </ChipRow>
          )}
          {stateHero.word && (page.posture === "act" || page.posture === "watch") && (
            <p class="hero-sub" data-testid="home-from">
              {fill(s.today.fromState, { date: dateLine(new Date(page.computedAt ?? page.fetchedAt), LOCALE[language.value]) })}
            </p>
          )}
        </div>
      )}
      <Notices v={v} saved={saved} />
      <Held v={v} />
      {/* Fix #1 (owner review round 3): see DadToday's own copy of this comment above. */}
      {(!page || !hero.ready) && !blank && !v.error && <HomeSkeleton />}
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

/** Whose voice Home speaks in, and the greeting itself — computed once and shared by the
 *  header (`HomeTopBar`) and the hero (`HomeHero`) below it, so the two can never drift apart.
 *  `isSelf()` (store/session.ts) decides it, never `density()`. His own greeting names him;
 *  hers names her — the person the greeting is *from* is always whoever is signed in, never
 *  the papers' name on a caregiver's own Home. */
export interface HomeVoice {
  self: boolean;
  greetName: string;
  question: string;
  hello: string;
  date: string;
}

function homeVoice(v: TodayView, patientName: string): HomeVoice {
  const { s, now } = v;
  const self = isSelf();
  const locale = LOCALE[language.value];
  const greetName = self ? patientName || me.value?.display_name || "" : me.value?.display_name || "";
  return {
    self,
    greetName,
    question: self ? s.hub.howFeeling : fill(s.hub.howFeelingOther, { patient: patientName }),
    hello: greeting(now.getHours(), greetName, s),
    date: dateLine(now, locale),
  };
}

/** Home's own header (cp3-home, owner review round 2): one row, and only one, at 390px — the
 *  avatar IS the papers switcher (`whose`, its existing behaviour and test id, unchanged), the
 *  greeting beside it (hello over the question, no date line — the date moved to sit under
 *  "Today" in the hero below it, `HomeHero`'s own kicker, so the row never needs a second one to
 *  fit), the bell, "Not well?" (its short pill, `NotWellButton`'s own compact label, the full
 *  phrase still its accessible name), and the menu (`open-me`, the same sheet every other
 *  screen's header opens it from) — trailing, not its own leading slot, so the row reads avatar
 *  first, the way the eye already goes. Replaces both the old global `ShellHeader` and the
 *  board's own "home" topbar for this screen — neither drew whose-papers and the greeting in the
 *  same row, so his own initial used to appear twice. */
/** `quiet`: true once Home's own decision (`useHomeHero`) is ready and is the quiet state — the
 *  greeting and the question drop out of the header row entirely then (owner review round 3,
 *  fix #5, the defect the owner found: "Good afternoon, Tan." twice, small in the header and
 *  large again under the orb, which already carries the greeting on a quiet day). The header
 *  still shows the avatar/switcher, the bell, "Not well?" and the menu — every control that
 *  needs no data — whatever the decision is, or before it is even made. */
function HomeTopBar({ voice, quiet }: { voice: HomeVoice; quiet: boolean }): JSX.Element {
  const s = t();
  const papers = profile.value;
  const bell = papers !== null && !emergencyOnly(papers);
  return (
    <header class="shell-head home-top-bar" data-testid="home-head">
      {papers && <ProfileSwitcher compact />}
      {!quiet && (
        <div class="home-head-text">
          <p class="home-head-hello" data-testid="home-head-hello">{voice.hello}</p>
          <h1 class="home-head-question" tabIndex={-1}>{voice.question}</h1>
        </div>
      )}
      <span class="home-head-end">
        {bell && <BellButton />}
        {/* The way in when he feels unwell comes before anything ranked (red flags escalate
            first): unchanged behaviour, unchanged test id, no animation on the red path — a
            small pill here now, never the full-width rose button (that is the not-feeling-well
            screen's own call button, `NotWell.tsx`). */}
        <NotWellButton compact />
        <button type="button" class="head-button head-button-small" aria-label={s.tabs.me} aria-haspopup="dialog" onClick={openMe} data-testid="open-me">
          <Icon name="menu" />
        </button>
      </span>
    </header>
  );
}

/** Today's own reading, read fresh (the same call `Readings()` below already makes, kept
 *  separate so a stale or an old reading never drives the headline — "today's" means today) —
 *  and, beside it, the most recent reading from an *earlier* day, if there is one: the insight
 *  card's own extra fact for a "reading" headline (owner review round 2) is how today's compares
 *  to that, never the systolic/diastolic the headline already gave in full. Both come from the
 *  one fetch; no second call. */
function useTodayReading(now: Date): { systolic: number; diastolic: number } | null;
function useTodayReading(
  now: Date,
  withTrend: true,
): { reading: { systolic: number; diastolic: number } | null; priorSystolic: number | null; ready: boolean };
function useTodayReading(now: Date, withTrend?: true) {
  const bearer = token.value;
  const papers = profile.value;
  const [state, setState] = useState<{ reading: { systolic: number; diastolic: number } | null; priorSystolic: number | null; ready: boolean }>({
    reading: null,
    priorSystolic: null,
    ready: false,
  });
  useEffect(() => {
    setState({ reading: null, priorSystolic: null, ready: false });
    // No `readings` scope: nothing to wait for — ready at once (owner review round 3, the
    // busy/quiet decision below waits on this the same way it waits on `page`).
    if (!bearer || !papers || !papers.scopes.includes("readings")) return setState({ reading: null, priorSystolic: null, ready: true });
    nura.facts(bearer, papers.profile_id, "blood_pressure").then((found) => {
      const today = dayKey(now);
      const readings = found
        .filter((fact) => fact.subject === "blood_pressure" && fact.attribute === "reading")
        .sort((a, b) => Date.parse(b.valid_from) - Date.parse(a.valid_from));
      const todaysOwn = readings.find((fact) => dayKey(new Date(fact.valid_from)) === today);
      const value = todaysOwn?.value as { systolic?: unknown; diastolic?: unknown } | null;
      const reading = typeof value?.systolic === "number" && typeof value?.diastolic === "number" ? { systolic: value.systolic, diastolic: value.diastolic } : null;
      const earlier = readings.find((fact) => dayKey(new Date(fact.valid_from)) !== today);
      const earlierValue = earlier?.value as { systolic?: unknown } | null;
      const priorSystolic = typeof earlierValue?.systolic === "number" ? earlierValue.systolic : null;
      setState({ reading, priorSystolic, ready: true });
    }, () => setState({ reading: null, priorSystolic: null, ready: true }));
    // `dayKey(now)`, not `now.getTime()` (owner review round 3): this hook now runs inside
    // `useHomeHero`, called directly from `DadToday`/`ChiefHome` rather than a child
    // component — its own `setState` above re-renders them, which builds a fresh `now = new
    // Date()` (`useToday.ts`) on every pass; keyed on the exact millisecond, that re-triggered
    // this same effect forever (the request storm on `/facts` the owner would have hit at
    // once). The calendar day is the only thing "today's own reading" ever actually depends on.
  }, [bearer, papers?.profile_id, dayKey(now)]);
  return withTrend ? state : state.reading;
}

/** The next visit's own place and driver lines (`useLogistics`, below — the same fetch
 *  `VisitTile` already makes for the full visit tile): the insight card's own extra fact for a
 *  "visit" headline (owner review round 2), never the doctor/weekday the headline already gave.
 *  Null with no visit, or while its logistics card is still loading — a visit headline with
 *  nothing more to say yet renders its rows without the card, same as any other empty case. */
function useVisitAbout(visit: AppointmentOut | null): string[] {
  const bearer = token.value;
  const papers = profile.value;
  const [about, setAbout] = useState<string[]>([]);
  useEffect(() => {
    if (!bearer || !papers || !visit) return setAbout([]);
    nura.logistics(bearer, papers.profile_id, visit.appointment_id).then(
      (card) => setAbout(card.lines.filter((line) => line.section === "place" || line.section === "driver").map((line) => line.text)),
      () => setAbout([]),
    );
  }, [bearer, papers?.profile_id, visit?.appointment_id, language.value]);
  return about;
}

/** The ranked feed's own flagged insight, if it raised one today — never a plain "today"/"now"
 *  listing card, which is not an insight about anything in particular. */
function insightOf(top: readonly FeedItemOut[], forYou: readonly FeedItemOut[]): FeedItemOut | null {
  return [...top, ...forYou].find((item) => item.category === "insight") ?? null;
}

/** A newly confirmed paper's own range summary, read from the review cards (owner review round
 *  3, fix #2): `ready` false until the read has come back at least once — Home's own busy/quiet
 *  decision waits for it the same way it waits for `page` (fix #1, the flash the owner found:
 *  a confirmed paper is exactly the case that used to decide quiet first, busy a second later,
 *  because this read had not landed yet). `null` with no insight-category card at all, or with
 *  one whose card is not (yet, or ever) among the review cards this key can read — never a bare
 *  title standing in for a card type with no template (nothing here trusts `item.headline`). */
function usePaperInsight(item: FeedItemOut | null): { ready: boolean; summary: PaperSummary | null } {
  const bearer = token.value;
  const papers = profile.value;
  const artifactId = typeof (item?.why as { artifact_id?: unknown } | undefined)?.artifact_id === "string" ? ((item!.why as { artifact_id: string }).artifact_id) : null;
  const [state, setState] = useState<{ ready: boolean; summary: PaperSummary | null }>({ ready: false, summary: null });
  useEffect(() => {
    // No paper on this card at all: nothing to wait for — ready at once.
    if (!artifactId || !item) return setState({ ready: true, summary: null });
    if (!bearer || !papers) return setState({ ready: true, summary: null });
    setState({ ready: false, summary: null });
    nura.reviewCards(bearer, papers.profile_id, false).then(
      (cards) => {
        const card = cards.find((each) => each.artifact_id === artifactId) ?? null;
        if (!card) return setState({ ready: true, summary: null });
        const known = card.fields.map((field) => rangeStatus(field.value, field.range)).filter((each) => each !== "unknown");
        const outside = known.filter((each) => each === "above" || each === "below").length;
        setState({
          ready: true,
          summary: {
            item,
            documentKind: card.document_kind,
            date: card.document_date ? new Date(card.document_date) : new Date(card.created_at),
            outside: known.length > 0 ? outside : null,
            total: known.length > 0 ? known.length : null,
          },
        });
      },
      () => setState({ ready: true, summary: null }),
    );
  }, [artifactId, bearer, papers?.profile_id]);
  return state;
}

/** Home's hero (cp3-home, the living orb) and its own busy/quiet decision, made once — never
 *  while an input it needs (`page`, the visits read, today's own reading, a confirmed paper's
 *  range summary) is still on the way (owner review round 3, fix #1: the flash the owner found,
 *  the quiet state painted first as a placeholder and the busy one a second later, once every
 *  input had actually arrived — an empty value that has simply not answered yet must never be
 *  read as "nothing here"). `ready` false holds the header's own greeting/question blank and the
 *  hero at the calm skeleton (`DadToday`/`ChiefHome`, below) rather than guessing. */
function useHomeHero(v: TodayView, patientName: string, voice: HomeVoice) {
  const { s, page, feed, act, top, now, nextVisit, dose, visitsReady } = v;
  const { self } = voice;
  const flagged = feed.flags.length > 0;
  const { reading, priorSystolic, ready: readingReady } = useTodayReading(now, true);
  const visitAbout = useVisitAbout(nextVisit);
  const insightItem = insightOf(top, feed.forYou);
  const { ready: paperReady, summary: paperSummary } = usePaperInsight(insightItem);
  const ready = page !== null && visitsReady && readingReady && paperReady;
  const topItem: HomeTopItem | null = ready
    ? homeTopItem(
        {
          dose: dose ?? null,
          reading,
          nextVisit: nextVisit ? { scheduled_at: nextVisit.scheduled_at, doctor: nextVisit.doctor ?? null } : null,
          lines: page!.lines,
          paper: paperSummary,
        },
        now,
        s,
      )
    : null;
  const state = homeState({ flagged, act, topItem });
  // E15-04: a new screen starts at its heading. Home's heading only settles once the decision
  // is made — the header's question when busy, the large greeting when quiet — and the header
  // is redrawn as it does, so the focus `app.tsx` gave the first one is lost. Give it again —
  // ONCE, the first time Home is ready, and never after he has moved focus himself: a refresh
  // that changes the state while he is tabbing through the page must not throw him back to
  // the top (the a11y walk caught exactly that: "Your emergency card → How are you today?").
  const headingGiven = useRef(false);
  useEffect(() => {
    if (!ready || headingGiven.current) return;
    headingGiven.current = true;
    const active = document.activeElement;
    const untouched = !active || active === document.body || active.closest("main h1, main h2") !== null;
    if (untouched) focusHeading();
  }, [ready, state]);
  // The two rows under the insight card are a different, always-actionable fact each — never
  // the same fact the headline already gave: the dose row only when the headline is not
  // already that dose, the "for you" row only for a feed item the headline is not already
  // showing as its own insight — and never the backend's own "A quiet day" placeholder card
  // (`app/delivery/strings.py`'s "now_quiet"), a leftover from a day this key's own dose data
  // has already decided is not quiet (fix #4: no structural flag marks that card, so it is
  // read off its own known, stable headline text in every language the catalogue ships).
  const dueNow = dose?.kind === "due" && topItem?.kind !== "doseDue" ? dose : null;
  const shownInsightId = topItem?.kind === "paper" ? topItem.item.item_id : null;
  const forYouItem = feed.forYou.find((item) => item.item_id !== shownInsightId && !QUIET_PLACEHOLDER_HEADLINES.has(item.headline)) ?? null;
  // The insight card's own extra fact (owner review round 2): a real thing the headline did not
  // already say, from that same item's own fields — never the headline's sentence again. `null`
  // with nothing more to say yet, in which case the card itself does not render at all; the
  // rows below still do (`insightExtraLines`, today/model.ts).
  const extra = topItem
    ? insightExtraLines(
        topItem,
        {
          doseProvenance: dose?.kind === "due" ? dose.provenance : null,
          slotsTotal: page?.slots.length ?? 0,
          slotsDone: page?.slots.filter((slot) => slot.taken).length ?? 0,
          priorSystolic,
          visitAbout,
          reorderLine: page ? nearestToRunOut(page.lines)?.count?.lines[0] ?? null : null,
        },
        s,
        self,
        patientName,
      )
    : null;
  return { ready, state, topItem, dueNow, forYouItem, extra };
}

/** The backend's own "A quiet day"/"There is nothing new..." placeholder headline, in every
 *  language the catalogue ships (`app/delivery/strings.py`'s `HEADLINES["now_quiet"]`) — no
 *  `_THEIRS` twin exists for it, so it reads the same in both voices. There is no structural
 *  flag on the card itself to filter by; this is the only signal there is (fix #4). */
const QUIET_PLACEHOLDER_HEADLINES = new Set(["A quiet day", "Hari yang tenang", "平静的一天"]);

type HomeHeroState = ReturnType<typeof useHomeHero>;

/** Home's hero (cp3-home, the living orb): a busy day's one real headline and insight card, or
 *  a quiet day's large orb and chips — never a generic feed card's own title standing in for
 *  either (`homeTopItem`, today/model.ts), and never painted before its own decision is ready
 *  (fix #1 — `DadToday`/`ChiefHome` hold the calm skeleton until then). An act posture or a red
 *  flag pre-empts both entirely (`homeState`); the header above (`HomeTopBar`) is unconditional
 *  and always there. */
function HomeHero({ v, patientName, voice, hero }: { v: TodayView; patientName: string; voice: HomeVoice; hero: HomeHeroState }): JSX.Element {
  const { s, page, now, papers, busy, take, nextVisit } = v;
  const { self } = voice;
  const locale = LOCALE[language.value];
  const { ready, state, topItem, dueNow, forYouItem, extra } = hero;
  return (
    <>
      {/* The date, moved here from the header (owner review round 2, fix #1: the header row had
          no room left for a third line) — unconditional, the way it always was as part of the
          header itself: every page state shows it (busy, quiet, or a red flag/act state, which
          draws nothing else here at all), never only the busy day's own kicker. Same test id it
          always had (`home-head-date`): moved, never renamed. */}
      {ready && page && (
        <p class="home-kick-date" data-testid="home-head-date">
          {voice.date}
        </p>
      )}
      {ready && page && state === "busy" && topItem && (
        <div data-testid={self ? "today-hero" : "home-hero"}>
          <span class="home-kick">{s.home.todayKicker}</span>
          <SoftText as="h2" pace="headline" className="home-headline" text={homeHeadlineFor(topItem, s, locale, self, patientName)} testId="home-headline" />
          {extra && (
            <Glass className="home-insight" testId="insight-card">
              <h3>{self ? s.home.insightTitle : fill(s.home.insightTitleOther, { patient: patientName })}</h3>
              <div class="home-insight-body">
                <div class="home-date-chip" aria-hidden="true">
                  <b>{dateChip(homeTopItemDate(topItem, now), locale).day}</b>
                  <small>{dateChip(homeTopItemDate(topItem, now), locale).month}</small>
                </div>
                <div class="home-insight-lines">
                  {extra.map((line, at) => (
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
          )}
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
      {ready && page && state === "quiet" && (
        <div class="home-quiet" data-testid={self ? "today-hero" : "home-hero"}>
          <Orb size="lg" testId="home-orb-lg" />
          <SoftText as="h1" pace="headline" className="home-quiet-greeting" text={voice.hello} testId="quiet-greeting" />
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
