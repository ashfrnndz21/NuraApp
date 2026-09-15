import { useEffect, useMemo, useState } from "preact/hooks";
import * as nura from "../api/nura";
import type { AppointmentOut, FeedItemOut } from "../api/types";
import { forgetFeed } from "../feed/session";
import { dropStaleFeed } from "../offline/feedCache";
import { bindingOf, clearProfileData, loadToday, sameBinding, saveToday, shownUntil, zoneOf, type TodayEntry } from "../offline/todayCache";
import { readFailure } from "../restore";
import { chooseProfile, posture, profile, token } from "../store/session";
import { language, t } from "../strings";
import { browserClipDeps, ClipPlayer } from "../visit/clip";
import { boundaryOf, feedCards, nowCard, tookLine, type TodayModel } from "./model";
import { todayPage } from "./page";

/** Today's page, for both personas (D1 split the screen, not the reading): the page the phone
 *  kept (bound to the key that read it, good until the local midnight), then the fresh one when
 *  the network is there. A kept page shows today's list and no Now card: only the backend can
 *  say what is due. A refused read — or a key that has narrowed — deletes what the phone kept
 *  of these papers and says so; nothing is swallowed. */
export function useToday() {
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
  // The visits, when the key reaches them: the next one is the first (E05-03).
  const [visits, setVisits] = useState<AppointmentOut[]>([]);
  // Today's top three (E11-02), read live; a kept page shows the feed's own cards instead.
  const [topThree, setTopThree] = useState<FeedItemOut[]>([]);
  // "Hear what Dr Tan said" on a card with a consult clip (E21-03): played on a tap only.
  const clipPlayer = useMemo(
    () => new ClipPlayer(browserClipDeps((artifactId, start, end) => nura.clip(bearer ?? "", papers?.profile_id ?? "", artifactId, start, end))),
    [bearer, papers?.profile_id],
  );
  useEffect(() => () => clipPlayer.forget(), [clipPlayer]);

  const show = (next: TodayModel | null) => {
    setModel(next);
    todayPage.value = next;
  };

  /** A refusal, or anything that is not a lost network: nothing of these papers stays. */
  const forget = async (profileId: string, failure: unknown) => {
    await clearProfileData(profileId);
    forgetFeed();
    show(null);
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
      show(null);
      setKept(null);
      await chooseProfile(current);
    }
    // One call at a time; any refusal stops here and the caller deletes the phone's copy.
    // The State reads under the records scope: a key without it (a helper's, for the
    // medicines) has no State, and Today is the medicines and the feed's cards.
    const state = current.scopes.includes("records") ? await nura.state(bearer, id, language.value) : null;
    const lines = await nura.medicines(bearer, id, language.value);
    const slots = await nura.dosesToday(bearer, id, language.value);
    const counted = await nura.proud(bearer, id);
    const page = await nura.feed(bearer, id);
    try {
      setTopThree((await nura.feedToday(bearer, id)).items);
    } catch {
      setTopThree([]);
    }
    // The hero's number: the backend's count of what is due now, or next today.
    let hero = null;
    try {
      hero = await nura.medicinesNow(bearer, id, language.value);
    } catch {
      hero = null;
    }
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
      hero,
      word: state?.word ?? null,
      line: state?.line ?? null,
      drivers: state?.drivers ?? [],
    };
    show(fresh);
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
      show(entry.model);
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

  useEffect(() => {
    if (!bearer || !papers || !papers.scopes.includes("visits")) return;
    nura.appointments(bearer, papers.profile_id).then(setVisits, () => setVisits([]));
  }, [bearer, papers?.profile_id]);

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
  // Today's top three in the backend's order, less a flag card already shown above.
  const top = topThree.filter((item) => !feed.flags.some((flag) => flag.item_id === item.item_id));
  // Where the State card goes: first when it says act; in place of the dose card when it is
  // stale; under "For you today" when the feed has nothing for today; else not at all.
  const stateAt: "none" | "top" | "now" | "forYou" =
    !page || page.stateId === null ? "none" : act ? "top" : stale && !fromPhone ? "now" : useFeed ? "none" : "forYou";
  // The all-taken and nothing-now cards speak of today's doses: the backend's source line.
  const doseSource = page?.slots[0]?.source ?? "";
  const dose = page && !fromPhone && !stale ? nowCard(page.slots, page.lines, s) : null;
  const nextVisit = visits[0] ?? null;

  return { s, bearer, papers, page, kept, unreached, error, justTook, busy, take, fromPhone, blank, feed, act, stale, useFeed, top, stateAt, doseSource, dose, clipPlayer, nextVisit, now };
}

export type TodayView = ReturnType<typeof useToday>;
