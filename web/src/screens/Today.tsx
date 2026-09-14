import { useEffect, useState } from "preact/hooks";
import type { JSX } from "preact";
import * as nura from "../api/nura";
import type { FeedItemOut } from "../api/types";
import { forgetFeed } from "../feed/session";
import { go } from "../flow";
import { dropStaleFeed } from "../offline/feedCache";
import { bindingOf, clearProfileData, loadToday, sameBinding, saveToday, shownUntil, zoneOf, type TodayEntry } from "../offline/todayCache";
import { readFailure } from "../restore";
import { wantsHomeScreenHint } from "../offline/register";
import { chooseProfile, density, me, posture, profile, token } from "../store/session";
import { fill, language, LOCALE, t } from "../strings";
import {
  dateLine,
  boundaryOf,
  feedCards,
  feedLines,
  greeting,
  medicinesCard,
  nowCard,
  readingLead,
  stateLines,
  timeLine,
  todayList,
  tookLine,
  whyLine,
  type TodayModel,
} from "../today/model";
import { Card, Hear, Notice, Pill, TabBar, Tile } from "../ui/components";

/** Today: the Now card, a reading prompt, today's cards and the proud number — every line the
 *  backend's or the catalogue's, every card with its source line and its spoken twin.
 *
 *  It opens on the page the phone kept (bound to the key that read it, good until the local
 *  midnight) and then, when the network is there, on the fresh one. A kept page shows today's
 *  list and no Now card: only the backend can say what is due. Past midnight, with no network,
 *  only the emergency card and one line show. A refused read — or a key that has narrowed —
 *  deletes what the phone kept of these papers and says so; nothing is swallowed. */
export function TodayScreen({ saved }: { saved?: boolean }): JSX.Element {
  const s = t();
  const bearer = token.value;
  const papers = profile.value;
  const [model, setModel] = useState<TodayModel | null>(null);
  const [kept, setKept] = useState<TodayEntry | null>(null);
  // Why the last read did not land: no network, or a server that could not answer.
  const [unreached, setUnreached] = useState<"network" | "server" | null>(null);
  const [error, setError] = useState<unknown>(null);
  const [justTook, setJustTook] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  /** A refusal, or anything that is not a lost network: nothing of these papers stays. */
  const forget = async (profileId: string, failure: unknown) => {
    await clearProfileData(profileId);
    forgetFeed();
    setModel(null);
    setKept(null);
    setError(failure);
  };

  const refresh = async (): Promise<void> => {
    if (!bearer || !papers) return;
    const id = papers.profile_id;
    // Whose papers, under which key and which parts, as of now. A key narrowed or changed
    // since the page was kept finds its copy deleted before anything else is read.
    const current = await nura.profile(bearer, id);
    const binding = bindingOf(current);
    if (!sameBinding(binding, bindingOf(papers))) {
      await clearProfileData(id);
      forgetFeed();
      setModel(null);
      setKept(null);
      await chooseProfile(current);
    }
    // One call at a time; any refusal stops here and the caller deletes the phone's copy.
    // The State reads under the records scope: a key without it (a helper's, for the
    // medicines) has no State card, and Today is the medicines and the feed's cards.
    const state = current.scopes.includes("records") ? await nura.state(bearer, id) : null;
    const lines = await nura.medicines(bearer, id, language.value);
    const slots = await nura.dosesToday(bearer, id, language.value);
    const counted = await nura.proud(bearer, id);
    const page = await nura.feed(bearer, id);
    let chief: string | null = null;
    if (state?.posture === "act" && current.standing === "owner") {
      const held = await nura.keys(bearer, id);
      chief = held.find((key) => key.role === "chief" && !key.revoked_at && key.holder_display_name)?.holder_display_name ?? null;
    }
    const fresh: TodayModel = {
      stateId: state?.state_id ?? null,
      posture: state?.posture ?? "stable",
      stale: state?.stale ?? null,
      computedAt: state?.computed_at ?? null,
      slots,
      lines,
      feed: page.items,
      proud: counted.days,
      chief,
      boundary: boundaryOf(state?.boundary),
      fetchedAt: new Date().toISOString(),
    };
    setModel(fresh);
    setKept(null);
    setUnreached(null);
    posture.value = fresh.posture;
    await saveToday(id, fresh, binding, new Date(), zoneOf(current.region));
  };

  const load = async () => {
    if (!bearer || !papers) return;
    setError(null);
    const entry = await loadToday(papers.profile_id, bindingOf(papers), new Date());
    await dropStaleFeed(papers.profile_id, bindingOf(papers), new Date());
    if (entry) {
      setKept(entry);
      setModel(entry.model);
      posture.value = entry.model.posture;
    }
    try {
      await refresh();
    } catch (failure) {
      const kind = readFailure(failure);
      if (kind === "refused") await forget(papers.profile_id, failure);
      else setUnreached(kind);
    }
  };

  useEffect(() => {
    void load();
  }, [bearer, papers?.profile_id, language.value]);

  // At midnight on the region's clock the page on screen is yesterday's: read today's.
  useEffect(() => {
    if (!model) return;
    const until = shownUntil(model.fetchedAt, kept?.expiresAt ?? null, zoneOf(papers?.region));
    const timer = setTimeout(() => void load(), Math.max(0, until.getTime() - Date.now()) + 1000);
    return () => clearTimeout(timer);
  }, [model, kept]);

  const take = async (lineId: string, anchor: string) => {
    if (!bearer || !papers || busy) return;
    setBusy(true);
    setError(null);
    try {
      await nura.taken(bearer, papers.profile_id, lineId, anchor);
      setJustTook(tookLine(new Date().getHours(), s));
      await refresh();
    } catch (failure) {
      const kind = readFailure(failure);
      if (kind === "refused") await forget(papers.profile_id, failure);
      else if (kind === "network") setUnreached("network");
      else setError(failure); // the tap did not land; the page stays, and he is told
    } finally {
      setBusy(false);
    }
  };

  const now = new Date();
  const locale = LOCALE[language.value];
  const name = papers?.display_name || me.value?.display_name || "";
  // What is on screen came from the phone's copy, not the network, while `kept` is set. No
  // page is shown past the midnight after it was read, on the region's clock — kept or
  // fresh, even if the app stayed open (the timer above reads the new day's page).
  const fromPhone = kept !== null;
  const until = model ? shownUntil(model.fetchedAt, kept?.expiresAt ?? null, zoneOf(papers?.region)) : null;
  const page = model && until && now < until ? model : null;
  const blank = unreached !== null && page === null;

  const feed = page ? feedCards(page.feed) : { flags: [], forYou: [] };
  const act = page?.posture === "act";
  const stale = page?.stale === true;
  const useFeed = feed.forYou.length > 0;
  // Where the State card goes: first when it says act; in place of the dose card when it is
  // stale; under "For you today" when the feed has nothing for today; else not at all.
  const stateAt = !page || page.stateId === null ? "none" : act ? "top" : stale && !fromPhone ? "now" : useFeed ? "none" : "forYou";
  // The all-taken and nothing-now cards speak of today's doses: the backend's source line.
  const doseSource = page?.slots[0]?.source ?? "";
  const dose = page && !fromPhone && !stale ? nowCard(page.slots, page.lines, s) : null;
  const medicines = page ? medicinesCard(page.lines, !useFeed) : null;
  const proud = page?.proud ?? null;
  const proudLine =
    proud === null || proud === 0 ? s.today.proudNone : proud === 1 ? s.today.proudOne : fill(s.today.proud, { count: proud });

  const feedCard = (item: FeedItemOut, testId: string) => (
    <Card
      key={item.item_id}
      title={item.headline}
      lines={feedLines(item).lines}
      boundary={feedLines(item).boundary}
      spoken={item.voice.length > 0 ? item.voice : undefined}
      provenance={whyLine(item)}
      paper={density() === "patient" || item.supply === "flag"}
      testId={testId}
    />
  );
  const stateCard = page && (
    <Card
      lines={stateLines(page, s, { flagAbove: feed.flags.length > 0, kept: fromPhone })}
      boundary={page.boundary ?? []}
      provenance={fill(s.today.fromState, { date: dateLine(new Date(page.computedAt ?? page.fetchedAt), locale) })}
      paper={density() === "patient" || act}
      testId="state-card"
    />
  );

  return (
    <main class="screen" data-density={density()}>
      <header class="hero">
        <div class="greeting">{greeting(now.getHours(), name, s)}</div>
        <div class="date">{dateLine(now, locale)}</div>
      </header>

      {blank ? (
        <>
          <Card lines={[s.today.cannotReach]} testId="cannot-reach" />
          <Card title={s.today.emergencyTitle} lines={[s.today.emergencySoon]} testId="emergency-placeholder" />
        </>
      ) : (
        <>
          {unreached && kept && page && (
            <Tile glass testId="offline">
              <p>{unreached === "network" ? s.today.offline : s.today.cannotReach}</p>
              <p>{s.today.offlineSub}</p>
              <p class="caption">
                {fill(s.today.asOf, { date: dateLine(new Date(kept.fetchedAt), locale), time: timeLine(new Date(kept.fetchedAt), locale) })}
              </p>
            </Tile>
          )}
          {saved && (
            <Tile paper>
              <p>{s.reading.saved}</p>
            </Tile>
          )}
          <Notice error={error} />

          {page && (
            <>
              {feed.flags.map((item) => feedCard(item, "flag-card"))}
              {stateAt === "top" && stateCard}

              <h2 class="section">{s.today.now}</h2>
              {fromPhone &&
                (page.slots.length > 0 ? (
                  <Card title={s.today.todayList} lines={todayList(page.slots)} provenance={s.today.fromToday} testId="today-list" />
                ) : (
                  <Card title={s.today.noMedicines} lines={[s.today.noMedicinesSub]} testId="no-medicines" />
                ))}
              {stateAt === "now" && stateCard}
              {dose?.kind === "due" && (
                <Card
                  title={dose.title}
                  lines={[dose.sentence]}
                  provenance={dose.provenance}
                  testId="now-card"
                  action={
                    <Pill plum onClick={() => take(dose.lineId, dose.anchor)} disabled={busy} testId="taken">
                      {s.today.taken}
                    </Pill>
                  }
                />
              )}
              {dose?.kind === "missed" && (
                <>
                  <h3 class="section">{s.today.earlierTitle}</h3>
                  <Card title={dose.title} lines={dose.lines} provenance={dose.provenance} testId="missed-card" />
                </>
              )}
              {dose?.kind === "allTaken" && (
                <Card title={s.today.allTaken} lines={[justTook ?? s.today.allTakenSub]} provenance={doseSource} settled testId="all-taken" />
              )}
              {dose?.kind === "nothingNow" && <Card lines={[justTook ?? s.today.nothingNow]} provenance={doseSource} testId="nothing-now" />}
              {dose?.kind === "none" && <Card title={s.today.noMedicines} lines={[s.today.noMedicinesSub]} testId="no-medicines" />}
              {justTook && (dose?.kind === "due" || dose?.kind === "missed") && (
                <Tile paper settled>
                  <p>{justTook}</p>
                </Tile>
              )}

              {!fromPhone && (
                <Card
                  title={s.today.readingTitle}
                  lines={[readingLead(now.getHours(), s)]}
                  testId="reading-prompt"
                  action={
                    <Pill onClick={() => go({ name: "reading" })} testId="write-reading">
                      {s.today.readingButton}
                    </Pill>
                  }
                />
              )}

              <h2 class="section">{s.today.forYou}</h2>
              {useFeed && feed.forYou.map((item) => feedCard(item, "feed-card"))}
              {stateAt === "forYou" && stateCard}
              <Pill onClick={() => go({ name: "feed" })} testId="open-feed">
                {s.feed.open}
              </Pill>
              {medicines && (
                <Card
                  title={s.today.supplyTitle}
                  lines={medicines.lines}
                  provenance={medicines.provenance}
                  paper={density() === "patient"}
                  testId="medicines-card"
                />
              )}
              <Tile paper testId="proud">
                <div class="number" data-testid="proud-number">
                  {proud ?? 0}
                </div>
                <p>{proudLine}</p>
                <p class="caption">{s.today.proudSub}</p>
                <p class="provenance">{s.today.fromDays}</p>
                <Hear lines={[proudLine, s.today.proudSub]} />
              </Tile>
            </>
          )}

          {wantsHomeScreenHint() && (
            <Tile glass>
              <p>{s.today.homeScreen1}</p>
              <p>{s.today.homeScreen2}</p>
              <p>{s.today.homeScreen3}</p>
            </Tile>
          )}
        </>
      )}

      <TabBar current="today" onSelect={(tab) => go(tab === "me" ? { name: "me" } : { name: "today" })} />
    </main>
  );
}
