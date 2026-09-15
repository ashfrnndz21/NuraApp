import { useEffect, useState } from "preact/hooks";
import type { JSX } from "preact";
import * as family from "../api/family";
import * as nura from "../api/nura";
import type { AppointmentOut, ChangesOut, FeedItemOut, LineOut, LogisticsOut, VisitQuestionOut } from "../api/types";
import { ClipCard } from "../day/components";
import { clipsOf } from "../day/model";
import { DayOnToday, NotWellButton, TopThree } from "../day/TodayDay";
import { go, openTab } from "../flow";
import { density, me, profile, token } from "../store/session";
import { fill, language, LOCALE, t, type Strings } from "../strings";
import {
  dateLine,
  dayMonthLine,
  dueCards,
  feedLines,
  greeting,
  homeHero,
  nearestToRunOut,
  readingLead,
  stateLines,
  systolics,
  timeLine,
  todayList,
  weekdayOf,
  whyLine,
} from "../today/model";
import { useToday, type TodayView } from "../today/useToday";
import { Card, Hear, Notice, Tile } from "../ui/components";
import { Avatar, Chip, ChipRow, FeedCard, GlassTile, Hero, Icon, PanelList, PaperTile, PillButton, SectionLabel, Sparkline, toneOf } from "../ui/kit";
import { AskField, Shell } from "./Shell";

/** Today (D1, docs/ui-mockup.html and docs/ui-mockup-v2.html): his Today in the patient's
 *  density, the chief's Home in the caregiver's. Both read the same page (`useToday`); every
 *  line on either is the backend's or the catalogue's, every card has its source and its
 *  spoken twin, and nothing is drawn over a line. */
export function TodayScreen({ saved }: { saved?: boolean }): JSX.Element {
  return density() === "patient" ? <DadToday saved={saved ?? false} /> : <ChiefHome saved={saved ?? false} />;
}

/** His Today: ask or search; the one big number on the wash; "Now", a tile for each dose due
 *  with its pill and a full-width Taken; the day's check-in; "For you today" in the card
 *  grammar; the next visit with what to bring; a note from the family; and the coral pill,
 *  always last, always there — offline too. */
function DadToday({ saved }: { saved: boolean }): JSX.Element {
  const v = useToday();
  const { s, page, blank, feed, fromPhone, unreached, top, useFeed, stateAt, now, nextVisit, papers } = v;
  const locale = LOCALE[language.value];
  const name = papers?.display_name || me.value?.display_name || "";
  const hero = page?.hero ?? null;
  return (
    <Shell tab="today" testId="today-screen">
      <AskField placeholder={s.shell.askNura} />
      <Hero
        greeting={greeting(now.getHours(), name, s)}
        sub={dateLine(now, locale)}
        figure={fromPhone ? null : (hero?.count ?? null)}
        words={!fromPhone && hero?.count !== null && hero?.count !== undefined ? hero.words : null}
        testId="today-hero"
      />
      {/* The way in when he feels unwell comes before anything ranked (red flags escalate first). */}
      <NotWellButton />
      {page && <span data-testid="today-ready" hidden />}
      <Notices v={v} saved={saved} />
      {blank ? (
        <Blank s={s} />
      ) : (
        page && (
          <>
            {feed.flags.map((item) => (
              <FeedItemCard key={item.item_id} item={item} v={v} testId="flag-card" />
            ))}
            {stateAt === "top" && <StateCard v={v} />}
            <DoseSection v={v} />
            <SectionLabel>{s.today.forYou}</SectionLabel>
            {!fromPhone && top.length > 0 ? (
              <TopThree items={top} player={v.clipPlayer} />
            ) : (
              useFeed && feed.forYou.map((item) => <FeedItemCard key={item.item_id} item={item} v={v} testId="feed-card" />)
            )}
            {stateAt === "forYou" && <StateCard v={v} />}
            {!fromPhone && (
              <Card
                title={s.today.readingTitle}
                lines={[readingLead(now.getHours(), s)]}
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
            {nextVisit && !fromPhone && <VisitTile visit={nextVisit} />}
            {!fromPhone && <FamilyNote />}
          </>
        )
      )}
    </Shell>
  );
}

/** The chief's Home: "Ask about Pa" on top (the shell's); the State as its word with the
 *  drivers as chips and his blood pressures as a sparkline; what changed since she last looked,
 *  a dot in its tone on each line; the next visit and what to buy side by side; what the papers
 *  are missing; then the doses she may tap for him, and today's cards. */
function ChiefHome({ saved }: { saved: boolean }): JSX.Element {
  const v = useToday();
  const { s, page, blank, feed, fromPhone, unreached, top, useFeed, nextVisit, stateAt } = v;
  const drivers = page?.drivers ?? [];
  const hero = page ? homeHero(page, { flagged: feed.flags.length > 0, kept: fromPhone }, s) : null;
  const locale = LOCALE[language.value];
  const supply = page ? <SupplyTile lines={page.lines} /> : null;
  return (
    <Shell tab="today" testId="home-screen">
      {page && <span data-testid="today-ready" hidden />}
      {page && page.stateId !== null && page.word && hero && (
        <Hero label={hero.word ? s.home.mostLikely : undefined} figure={hero.word} words={hero.line} testId="home-hero">
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
          {/* Where the State came from and when, and the boundary it is shown under: with the
              State's word, never over a flag. */}
          {hero.word && (
            <>
              <p class="hero-sub" data-testid="home-from">
                {fill(s.today.fromState, { date: dateLine(new Date(page.computedAt ?? page.fetchedAt), locale) })}
              </p>
              {(page.boundary ?? []).length > 0 && (
                <div class="hero-boundary" data-testid="home-boundary">
                  {(page.boundary ?? []).map((line, at) => (
                    <p key={at}>{line}</p>
                  ))}
                </div>
              )}
            </>
          )}
        </Hero>
      )}
      <NotWellButton />
      <Notices v={v} saved={saved} />
      {blank ? (
        <Blank s={s} />
      ) : (
        page && (
          <>
            {feed.flags.map((item) => (
              <FeedItemCard key={item.item_id} item={item} v={v} testId="flag-card" />
            ))}
            {(stateAt === "top" || stateAt === "forYou") && <StateCard v={v} />}
            {!fromPhone && <WhatChanged />}
            {((nextVisit && !fromPhone) || supply) && (
              <div class="two-up">
                {nextVisit && !fromPhone && <NextVisitTile visit={nextVisit} />}
                {supply}
              </div>
            )}
            {nextVisit && !fromPhone && <GapsTile visit={nextVisit} />}
            <AskAboutPill />
            {/* F1: "Watching for {name}" and "Sent to {name} this week" (PanelList) go here. */}
            <DoseSection v={v} />
            <SectionLabel>{s.today.forYou}</SectionLabel>
            {!fromPhone && top.length > 0 ? (
              <TopThree items={top} player={v.clipPlayer} />
            ) : (
              useFeed && feed.forYou.map((item) => <FeedItemCard key={item.item_id} item={item} v={v} testId="feed-card" />)
            )}
            <PillButton onClick={() => go({ name: "feed" })} testId="open-feed">
              {s.feed.open}
            </PillButton>
            <DayOnToday stateId={page.stateId} live={!fromPhone && unreached === null} />
          </>
        )
      )}
    </Shell>
  );
}

// --- the pieces both read ------------------------------------------------------------------

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
function Blank({ s }: { s: Strings }): JSX.Element {
  return (
    <>
      <Card lines={[s.today.cannotReach]} testId="cannot-reach" />
      <Card title={s.today.emergencyTitle} lines={[s.today.emergencySoon]} testId="emergency-placeholder" />
    </>
  );
}

/** One of the feed's cards in the card grammar: its headline, its lines, its boundary, why it
 *  is here, and its spoken twin. A card with a consult clip keeps its player under its line. */
function FeedItemCard({ item, v, testId }: { item: FeedItemOut; v: TodayView; testId: string }): JSX.Element {
  const clips = clipsOf(item);
  const paper = density() === "patient" || item.supply === "flag";
  if (clips.size > 0) return <ClipCard item={item} clips={clips} player={v.clipPlayer} paper={paper} testId={testId} />;
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
function DoseSection({ v }: { v: TodayView }): JSX.Element | null {
  const { s, page, fromPhone, stateAt, dose, doseSource, justTook, busy, take } = v;
  if (!page) return null;
  const due = dose?.kind === "due" ? dueCards(page.slots, page.lines, s) : [];
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
              {s.today.taken}
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
    <>
      <SectionLabel>{s.home.nextVisit}</SectionLabel>
      <PaperTile testId="visit-tile">
        <div class="card-head">
          <span class="card-icon">
            <Icon name="visits" />
          </span>
          <h2 class="title">{when?.text ?? s.visit.title}</h2>
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
      </PaperTile>
    </>
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
    nura.changes(bearer, papers.profile_id, language.value).then(setFound, () => setFound(null));
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

/** The next visit as a figure — its day and time — and where, as the logistics card says. */
function NextVisitTile({ visit }: { visit: AppointmentOut }): JSX.Element {
  const s = t();
  const locale = LOCALE[language.value];
  const at = new Date(visit.scheduled_at);
  return (
    <GlassTile testId="next-visit-tile">
      <button type="button" class="tile-link" onClick={() => go({ name: "visit", appointmentId: visit.appointment_id })} data-testid="open-visit">
        <span class="tile-title">{s.home.nextVisit}</span>
        <Icon name="chevron" />
      </button>
      {/* The weekday once, large; the day and month and the time under it (never the weekday twice). */}
      <p class="number small">{weekdayOf(at, locale)}</p>
      <p class="source-line" data-testid="next-visit-date">{dayMonthLine(at, locale)}</p>
      <p class="source-line">{timeLine(at, locale)}</p>
    </GlassTile>
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
    <GlassTile testId="supply-tile">
      <button type="button" class="tile-link" onClick={() => openTab("medicines")} data-testid="open-medicines">
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
    </GlassTile>
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
