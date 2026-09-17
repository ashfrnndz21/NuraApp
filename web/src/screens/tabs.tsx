import { useEffect, useState } from "preact/hooks";
import type { JSX } from "preact";
import * as nura from "../api/nura";
import type { AppointmentOut, FeedItemOut, HomeCareCategory, ProviderSummaryOut } from "../api/types";
import { go } from "../flow";
import { careCards, clipOf, guideCards } from "../feed/model";
import { startOnboarding } from "../onboarding/state";
import { providerLines, kindWord, homeCareCategoryLabel } from "../record/model";
import { profile, token } from "../store/session";
import { fill, language, LOCALE, t, type Strings } from "../strings";
import { dateLine, feedLines, timeLine, whyLine } from "../today/model";
import { Card, Notice } from "../ui/components";
import { FeatureTile, FeedCard, Icon, PaperTile, PillButton, Poster, SectionLabel, type Tint } from "../ui/kit";
import { Shell } from "./Shell";

/** The Visits tab (D1, one tab set): his visits — the spine of the record — and, under them,
 *  getting ready for the next one. This is the surface the design system calls Visits for him
 *  and Plan for her; it is one screen for both, because it answers one question either way. */

function useOwner(): { own: boolean; name: string } {
  const papers = profile.value;
  return { own: papers?.standing === "owner", name: papers?.display_name ?? "" };
}

/** The visits: each one's day and time, what it is for, and — for the next one — its brief and
 *  its questions, as rows: an icon, the word, the way in. */
function VisitList(): JSX.Element | null {
  const s = t();
  const bearer = token.value;
  const papers = profile.value;
  const { own, name } = useOwner();
  const locale = LOCALE[language.value];
  const [visits, setVisits] = useState<AppointmentOut[] | null>(null);
  const [error, setError] = useState<unknown>(null);
  useEffect(() => {
    if (!bearer || !papers) return;
    nura.appointments(bearer, papers.profile_id).then(
      setVisits,
      (failure: unknown) => {
        setVisits([]);
        setError(failure);
      },
    );
  }, [bearer, papers?.profile_id]);
  if (!visits) return null;
  if (visits.length === 0) {
    return (
      <>
        <Notice error={error} />
        {!error && <Card lines={[own ? s.visit.none : fill(s.places.visitsNoneOther, { name })]} testId="no-visits" />}
      </>
    );
  }
  return (
    <>
      {visits.map((visit, at) => {
        const when = new Date(visit.scheduled_at);
        return (
          <PaperTile key={visit.appointment_id} testId="visit-item">
            <div class="card-head">
              <span class="card-icon">
                <Icon name="visits" />
              </span>
              <div>
                <h2 class="title">{dateLine(when, locale)}</h2>
                <p class="source-line">{timeLine(when, locale)}</p>
              </div>
            </div>
            {visit.purpose && <p>{visit.purpose}</p>}
            {at === 0 && (
              <nav class="place-rows" aria-label={s.visit.open}>
                <button type="button" class="place-row" onClick={() => go({ name: "visit", appointmentId: visit.appointment_id })} data-testid="visit-open">
                  <Icon name="visits" />
                  <span class="place-word">{s.visit.open}</span>
                  <Icon name="chevron" />
                </button>
                <button type="button" class="place-row" onClick={() => go({ name: "brief", appointmentId: visit.appointment_id })} data-testid="visit-brief">
                  <Icon name="records" />
                  <span class="place-word">{s.day.briefOpen}</span>
                  <Icon name="chevron" />
                </button>
                <button type="button" class="place-row" onClick={() => go({ name: "questions", appointmentId: visit.appointment_id })} data-testid="visit-questions">
                  <Icon name="note" />
                  <span class="place-word">{s.day.questionsOpen}</span>
                  <Icon name="chevron" />
                </button>
              </nav>
            )}
          </PaperTile>
        );
      })}
    </>
  );
}

/** Care services (D1, the concept board's Services screen): the local alerts already in the
 *  feed — dengue, haze, heat, a season — made for him and him alone (E09-07), and, under them,
 *  the doctors and clinics his own record names (E03-03). Nothing here is invented: every card
 *  is one the feed already rendered, every provider one the directory already holds, each with
 *  the way in it already has. A pure body, so owner and caregiver density are one prop away
 *  from a test, with no network of their own. */
export function CareBody({ s, own, name, cards, providers, dateOf }: { s: Strings; own: boolean; name: string; cards: readonly FeedItemOut[]; providers: readonly ProviderSummaryOut[]; dateOf: (iso: string) => string }): JSX.Element {
  const empty = cards.length === 0 && providers.length === 0;
  return (
    <>
      <SectionLabel>{s.places.careTitle}</SectionLabel>
      {empty ? (
        <PaperTile testId="care-empty">
          <p>{own ? s.places.careNoneOwn : fill(s.places.careNoneOther, { name })}</p>
        </PaperTile>
      ) : (
        <>
          {cards.map((item) => {
            const shown = feedLines(item);
            return <FeedCard key={item.item_id} icon="care" title={item.headline} lines={shown.lines} boundary={shown.boundary} why={whyLine(item)} testId="care-card" />;
          })}
          {providers.slice(0, 3).map((summary) => (
            <PaperTile key={summary.provider.provider_id} testId="care-provider">
              <div class="card-head">
                <span class="card-icon">
                  <Icon name="stethoscope" />
                </span>
                <div>
                  <h2 class="title">{summary.provider.name}</h2>
                  <p class="source-line">{kindWord(summary.provider.kind, s)}</p>
                </div>
              </div>
              <div class="lines">
                {providerLines(summary, dateOf, s).map((line, at) => (
                  <p key={at}>{line}</p>
                ))}
              </div>
              <nav class="place-rows" aria-label={s.record.seeDoctor}>
                <button type="button" class="place-row" onClick={() => go({ name: "record", at: { name: "provider", providerId: summary.provider.provider_id } })} data-testid="care-provider-open">
                  <Icon name="stethoscope" />
                  <span class="place-word">{s.record.seeDoctor}</span>
                  <Icon name="chevron" />
                </button>
              </nav>
            </PaperTile>
          ))}
          {providers.length > 0 && (
            <nav class="place-rows" aria-label={s.places.careTitle}>
              <button type="button" class="place-row" onClick={() => go({ name: "record", at: { name: "providers" } })} data-testid="care-providers-all">
                <Icon name="records" />
                <span class="place-word">{s.record.providers}</span>
                <Icon name="chevron" />
              </button>
            </nav>
          )}
        </>
      )}
    </>
  );
}

const HOME_CARE_CATEGORIES: readonly HomeCareCategory[] = ["nursing", "physio", "meals", "transport"];
const HOME_CARE_TINT: Record<HomeCareCategory, Tint> = { nursing: "blush", physio: "sage", meals: "butter", transport: "sky" };
const HOME_CARE_ICON: Record<HomeCareCategory, "care" | "steps" | "meal" | "transport"> = {
  nursing: "care",
  physio: "steps",
  meals: "meal",
  transport: "transport",
};

/** Services' "Help at home" grid (the concept board's Services screen, "Care services": four
 *  tiles — Nursing at home, Physio, Meals, Transport), backed by the same provider directory
 *  `CareBody` reads, told apart by `Provider.category`. A tile opens the directory filtered to
 *  that category, with "Near you" distances from his own area; a category with nothing near
 *  him says so once he opens it, rather than being hidden — every tile is always a real tap. */
const HOME_CARE_LINE: Record<HomeCareCategory, keyof Strings["homeCare"]> = {
  nursing: "nursingLine",
  physio: "physioLine",
  meals: "mealsLine",
  transport: "transportLine",
};

export function HomeCareGrid({ s, own, name, providers }: { s: Strings; own: boolean; name: string; providers: readonly ProviderSummaryOut[] }): JSX.Element {
  const counts: Record<HomeCareCategory, number> = { nursing: 0, physio: 0, meals: 0, transport: 0 };
  for (const each of providers) {
    if (each.provider.category) counts[each.provider.category] += 1;
  }
  return (
    <>
      <SectionLabel>{s.homeCare.title}</SectionLabel>
      <div class="do-grid" data-testid="home-care-grid">
        {HOME_CARE_CATEGORIES.map((category) => (
          <FeatureTile
            key={category}
            icon={HOME_CARE_ICON[category]}
            tint={HOME_CARE_TINT[category]}
            label={homeCareCategoryLabel(category, s)}
            caption={counts[category] > 0 ? fill(own ? s.homeCare.near : s.homeCare.nearOther, { name }) : s.homeCare[HOME_CARE_LINE[category]]}
            onClick={() => go({ name: "record", at: { name: "providers", category } })}
            testId={`home-care-${category}`}
          />
        ))}
      </div>
    </>
  );
}

/** Near you: the coarse area Nura keeps for him (`GET /profiles/{id}/area`, E09-07) — a town or
 *  a postcode's first digits, never a street. Nothing when Nura does not know it yet: an area
 *  guessed would be fiction, so the section is silent instead. */
export function NearYouBody({ s, own, name, area }: { s: Strings; own: boolean; name: string; area: string | null }): JSX.Element | null {
  if (!area) return null;
  return (
    <>
      <SectionLabel>{own ? s.places.nearYouOwn : fill(s.places.nearYouOther, { name })}</SectionLabel>
      <PaperTile testId="near-you">
        <p>{own ? fill(s.places.nearYouArea, { area }) : fill(s.places.nearYouAreaOther, { area, name })}</p>
      </PaperTile>
    </>
  );
}

/** A guide with no clip: the same lines and boundary Home's learning cards show, its why
 *  underneath. */
function GuideCard({ item }: { item: FeedItemOut }): JSX.Element {
  const shown = feedLines(item);
  return <FeedCard icon="resources" title={item.headline} lines={shown.lines} boundary={shown.boundary} why={whyLine(item)} testId="guide-card" />;
}

/** The clip's media slot, drawn from state alone (no hook of its own, so a test calls it like
 *  any other pure component): the poster is the whole button, and nothing plays until it is
 *  tapped — the tap is what "opens the player" (`clip-player`), whether or not the still or
 *  the excerpt has arrived yet. */
export function ClipMedia({ s, playing, poster, video, onPlay }: { s: Strings; playing: boolean; poster: string | null; video: string | null; onPlay: () => void }): JSX.Element {
  if (!playing) return <Poster label={s.feed.play} onPlay={onPlay} wide testId="guide-play" />;
  return (
    <div class="clip" data-testid="clip-player">
      {video ? (
        <video src={video} poster={poster ?? undefined} controls playsInline preload="none" style="max-width:100%" data-testid="clip-video" />
      ) : (
        poster && <img src={poster} alt="" style="max-width:100%" data-testid="clip-poster" />
      )}
    </div>
  );
}

/** A guide that is a clip (E09-06): `ClipMedia`'s poster is the button, and tapping it fetches
 *  the still and, where the publisher's licence allows one, the excerpt — the same two
 *  endpoints the vertical feed's clip uses (`ui/Player.tsx`'s single player, #189's rule: one
 *  player, never two). */
function GuideClip({ item }: { item: FeedItemOut }): JSX.Element {
  const s = t();
  const shown = feedLines(item);
  const clip = clipOf(item);
  const [playing, setPlaying] = useState(false);
  const [poster, setPoster] = useState<string | null>(null);
  const [video, setVideo] = useState<string | null>(null);
  useEffect(() => {
    if (!playing) return;
    const bearer = token.value;
    const profileId = profile.value?.profile_id;
    if (!bearer || !profileId) return;
    let live = true;
    const urls: string[] = [];
    const keep = (blob: Blob, set: (url: string) => void) => {
      if (!live) return;
      const url = URL.createObjectURL(blob);
      urls.push(url);
      set(url);
    };
    nura.clipPoster(bearer, profileId, item.item_id).then((blob) => keep(blob, setPoster), () => setPoster(null));
    if (clip?.excerpt) nura.clipVideo(bearer, profileId, item.item_id).then((blob) => keep(blob, setVideo), () => setVideo(null));
    return () => {
      live = false;
      for (const url of urls) URL.revokeObjectURL(url);
    };
  }, [playing, item.item_id, clip?.excerpt]);
  return (
    <FeedCard
      icon="resources"
      title={item.headline}
      lines={shown.lines}
      boundary={shown.boundary}
      why={whyLine(item)}
      testId="guide-clip"
      media={<ClipMedia s={s} playing={playing} poster={poster} video={video} onPlay={() => setPlaying(true)} />}
    />
  );
}

/** Guides: the same learning explainers and clips Home's learning section shows him, filtered
 *  to this screen — nothing seasonal or food-specific, which stay on Home. */
export function GuideBody({ s, cards }: { s: Strings; cards: readonly FeedItemOut[] }): JSX.Element | null {
  if (cards.length === 0) return null;
  return (
    <>
      <SectionLabel>{s.places.guidesTitle}</SectionLabel>
      {cards.map((item) => (clipOf(item) ? <GuideClip key={item.item_id} item={item} /> : <GuideCard key={item.item_id} item={item} />))}
    </>
  );
}

/** The feed pages one at a time (`PAGE_SIZE = 5` on the backend, `rank._endless`), so the
 *  local alerts and the learning cards a small profile has can sit past the first page's now
 *  and today cards. Care services and Guides read the same pages the pager itself would reach
 *  by "Keep going", walked here instead of on a tap — the same endpoint, never a fresh one,
 *  and capped so a very long history cannot spin this screen forever. */
async function wholeFeed(bearer: string, profileId: string): Promise<FeedItemOut[]> {
  const items: FeedItemOut[] = [];
  let cursor: string | undefined;
  for (let page = 0; page < 8; page += 1) {
    const got = await nura.feedPage(bearer, profileId, cursor);
    items.push(...got.items);
    if (!got.next_cursor) break;
    cursor = got.next_cursor;
  }
  return items;
}

/** The three sections the concept board's Services screen adds under his visits: Care
 *  services, Near you, Guides — the feed's own pages, the provider directory and his area,
 *  every one of them already there for another screen. No new backend data, and every card
 *  keeps the why line it was rendered with (`whyLine`). */
function ServiceCards(): JSX.Element | null {
  const s = t();
  const bearer = token.value;
  const papers = profile.value;
  const { own, name } = useOwner();
  const locale = LOCALE[language.value];
  const [items, setItems] = useState<FeedItemOut[] | null>(null);
  const [providers, setProviders] = useState<ProviderSummaryOut[] | null>(null);
  const [area, setArea] = useState<string | null>(null);
  const [areaKnown, setAreaKnown] = useState(false);
  const [error, setError] = useState<unknown>(null);
  useEffect(() => {
    if (!bearer || !papers) return;
    wholeFeed(bearer, papers.profile_id).then(setItems, (failure: unknown) => {
      setItems([]);
      setError(failure);
    });
    nura.providers(bearer, papers.profile_id).then(setProviders, () => setProviders([]));
    nura.area(bearer, papers.profile_id).then(
      (out) => {
        setArea(out.area);
        setAreaKnown(true);
      },
      () => setAreaKnown(true),
    );
  }, [bearer, papers?.profile_id]);
  if (!items || !providers || !areaKnown) return null;
  // The doctors-and-clinics directory (`CareBody`, the app's own "Care services") and the
  // board's home-care grid (`HomeCareGrid`, "Help at home") read the same directory, told
  // apart only by `Provider.category` — never two separate lists to fall out of step.
  const doctors = providers.filter((each) => !each.provider.category);
  return (
    <>
      <Notice error={error} />
      <HomeCareGrid s={s} own={own} name={name} providers={providers} />
      <CareBody s={s} own={own} name={name} cards={careCards(items)} providers={doctors} dateOf={(iso) => dateLine(new Date(iso), locale)} />
      <NearYouBody s={s} own={own} name={name} area={area} />
      <GuideBody s={s} cards={guideCards(items)} />
    </>
  );
}

/** Getting ready for the next visit: his day's routine, a blood pressure to write down, and
 *  setting up from the papers. One Plum button at most, so the rows carry the rest. */
function GettingReady(): JSX.Element {
  const s = t();
  const papers = profile.value;
  return (
    <>
      <SectionLabel>{s.places.planTitle}</SectionLabel>
      <PaperTile testId="plan-ready">
        <p>{s.places.planLead}</p>
        <nav class="place-rows" aria-label={s.places.planTitle}>
          {papers?.scopes.includes("medicines") && (
            <button type="button" class="place-row" onClick={() => go({ name: "record", at: { name: "routine" } })} data-testid="plan-routine">
              <Icon name="today" />
              <span class="place-word">{s.record.routine}</span>
              <Icon name="chevron" />
            </button>
          )}
          {papers?.scopes.includes("readings") && (
            <button type="button" class="place-row" onClick={() => go({ name: "reading" })} data-testid="plan-reading">
              <Icon name="records" />
              <span class="place-word">{s.today.readingTitle}</span>
              <Icon name="chevron" />
            </button>
          )}
        </nav>
        {papers && (
          <PillButton onClick={() => void startOnboarding(papers)} testId="plan-set-up">
            {s.me.setUp}
          </PillButton>
        )}
      </PaperTile>
    </>
  );
}

export function VisitsScreen(): JSX.Element {
  const s = t();
  const { own, name } = useOwner();
  const title = own ? s.places.visitsOwn : fill(s.places.visitsOther, { name });
  return (
    <Shell tab="services" testId="visits-screen" topBar={{ variant: "board", title, back: true }}>
      <VisitList />
      <GettingReady />
      <ServiceCards />
    </Shell>
  );
}
