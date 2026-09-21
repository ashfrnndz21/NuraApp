import { useEffect, useState } from "preact/hooks";
import { Refused, Unreachable } from "../api/client";
import * as nura from "../api/nura";
import type { AppointmentOut, FeedItemOut, ProfileOut, SlotOut } from "../api/types";
import { forgetFeed } from "../feed/session";
import { dropCard, keepsCard, loadCard, readCard, saveCard, wantsRead, type KeptCard } from "../offline/emergencyCache";
import { dropStaleFeed } from "../offline/feedCache";
import { hold, replay, tapId, waiting, type Tap } from "../offline/queue";
import { bindingOf, clearProfileData, loadToday, sameBinding, saveToday, shownUntil, zoneOf, type Binding, type TodayEntry } from "../offline/todayCache";
import { voice } from "../player/voice";
import { readFailure } from "../restore";
import { chooseProfile, posture, profile, setLargeText, token } from "../store/session";
import { language, t } from "../strings";
import { boundaryOf, feedCards, largeTextOf, nowCard, tookLine, type TodayModel } from "./model";
import { todayPage } from "./page";

/** His tap, sent with its moment (W4). A phone clock far enough from Nura's that the moment is
 *  not today on the region's clock (`TapNotToday`) wrote nothing, and is no reason to lose a tap
 *  made now: it is sent again at Nura's own moment. */
async function tapTaken(bearer: string, profileId: string, lineId: string, anchor: string, at: string): Promise<void> {
  try {
    await nura.taken(bearer, profileId, lineId, anchor, at);
  } catch (failure) {
    if (!(failure instanceof Refused && failure.refusal === "TapNotToday")) throw failure;
    await nura.taken(bearer, profileId, lineId, anchor);
  }
}

/** Today's page, for both personas (D1 split the screen, not the reading): the page the phone
 *  kept (bound to the key that read it, good until the local midnight), then the fresh one when
 *  the network is there. A kept page shows today's list and no Now card: only the backend can
 *  say what is due. A refused read — or a key that has narrowed — deletes what the phone kept
 *  of these papers and says so; nothing is swallowed.
 *
 *  Offline (E00-08, W4): *Taken* on a dose that came from a live read, tapped when the network
 *  has gone, is held on the phone with the moment he tapped (`offline/queue.ts`) and sent once,
 *  in order, when the network is back — the page reads again after. A no to a held tap is said
 *  in the backend's words. The emergency card is kept too (`offline/emergencyCache.ts`), read
 *  once a day, and opens with no network. */
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
  // Whether the visits read has come back at least once for this key (owner review round 3):
  // Home's own busy/quiet decision waits for this the same way it waits for `page` — an empty
  // `visits` that simply has not answered yet must never read as "no visit soon".
  const [visitsReady, setVisitsReady] = useState(false);
  // Today's top three (E11-02), read live; a kept page shows the feed's own cards instead.
  const [topThree, setTopThree] = useState<FeedItemOut[]>([]);
  // Taps held while offline, whether the last replay sent any, and what the backend said no to.
  const [held, setHeld] = useState<Tap[]>([]);
  const [sent, setSent] = useState(false);
  const [heldRefused, setHeldRefused] = useState<Refused[]>([]);
  // The emergency card as the phone kept it (W4): shown when Today cannot be.
  const [card, setCard] = useState<KeptCard | null>(null);

  const show = (next: TodayModel | null) => {
    setModel(next);
    todayPage.value = next && papers ? { profileId: papers.profile_id, model: next } : null;
  };

  /** A refusal, or anything that is not a lost network: nothing of these papers stays, and the
   *  no is said — it is not a lost network, whatever the page thought a moment ago. */
  const forget = async (profileId: string, failure: unknown) => {
    await clearProfileData(profileId);
    forgetFeed();
    // The recordings the player fetched under this key go too: none replays after a no.
    voice.forget();
    // His large-text setting came from his State: it goes with the rest.
    await setLargeText(false);
    show(null);
    setKept(null);
    setHeld([]);
    setCard(null);
    setUnreached(null);
    setError(failure);
  };

  /** The emergency card: read once a day (and in a new language), kept, and never allowed to
   *  stop Today. No network or a State behind the record keeps the card the phone has; a no to
   *  this key deletes it. */
  const refreshCard = async (current: ProfileOut, binding: Binding): Promise<void> => {
    if (!bearer) return;
    const id = current.profile_id;
    const had = await loadCard(id, binding);
    if (!wantsRead(had, language.value, new Date(), zoneOf(current.region))) {
      setCard(had);
      return;
    }
    try {
      setCard(await saveCard(id, await readCard(bearer, id, language.value), binding, new Date(), had));
    } catch (failure) {
      if (keepsCard(failure)) setCard(had);
      else {
        await dropCard(id);
        setCard(null);
      }
    }
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
      voice.forget();
      show(null);
      setKept(null);
      setHeld([]);
      setCard(null);
      await chooseProfile(current);
    }
    // One call at a time; any refusal stops here and the caller deletes the phone's copy.
    // The State reads under the records scope: a key without it (a helper's, for the
    // medicines) has no State, and Today is the medicines and the feed's cards.
    const state = current.scopes.includes("records") ? await nura.state(bearer, id, language.value) : null;
    // His own large-text setting, as his State holds it, on his own phone (E15-04).
    if (current.standing === "owner") {
      const large = largeTextOf(state);
      if (large !== null) await setLargeText(large);
    }
    // Together, not one at a time (#191 regression, CI run 35190070446): each of these is its
    // own turn in `api/client.ts`'s queue regardless, so nothing here is ever really sent at
    // once — but awaited one after another, the queue sits briefly empty between them, and a
    // red word spoken in exactly that gap can reach the flag while nothing of Today's is on
    // the wire to abort, so *his* call has nothing to overtake and a background read of this
    // chain (`proud` did, once) finishes on its own, ahead of him. Firing them together closes
    // every gap but the one after the last, the same protection `medicinesNow`/`feedToday`
    // already had in spirit with their own catch.
    const [lines, slots, counted, page, topThree, hero] = await Promise.all([
      nura.medicines(bearer, id, language.value),
      nura.dosesToday(bearer, id, language.value),
      nura.proud(bearer, id),
      nura.feed(bearer, id),
      nura
        .feedToday(bearer, id)
        .then((read) => read.items)
        .catch(() => [] as FeedItemOut[]),
      // The hero's number: the backend's count of what is due now, or next today.
      nura.medicinesNow(bearer, id, language.value).catch(() => null),
    ]);
    setTopThree(topThree);
    let chief: string | null = null;
    if (state?.posture === "act" && current.standing === "owner") {
      const holders = await nura.keys(bearer, id);
      chief = holders.find((key) => key.role === "chief" && !key.revoked_at && key.holder_display_name)?.holder_display_name ?? null;
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
    // Signed out (or into other papers) while this was being read: the page is not his any
    // more — it is neither shown nor kept, so nothing of it outlives the sign-out.
    if (token.value !== bearer || profile.value?.profile_id !== id) return;
    show(fresh);
    setKept(null);
    setUnreached(null);
    posture.value = fresh.posture;
    await saveToday(id, fresh, binding, new Date(), zoneOf(current.region));
    await refreshCard(current, binding);
  };

  /** Send the taps held while offline, once each and in order, before the page is read. */
  const replayHeld = async (): Promise<void> => {
    if (!bearer || !papers) return;
    const id = papers.profile_id;
    const binding = bindingOf(papers);
    const done = await replay(id, binding, new Date(), (tap) =>
      tap.kind === "taken" ? nura.taken(bearer, id, tap.lineId, tap.anchor, tap.at) : nura.feeling(bearer, id, tap.word, tap.language),
    );
    if (done.sent.length > 0) setSent(true);
    if (done.refused.length > 0) setHeldRefused((before) => [...before, ...done.refused.map((each) => each.failure)]);
    setHeld(await waiting(id, binding, new Date()));
  };

  const load = async () => {
    if (!bearer || !papers) return;
    setError(null);
    const binding = bindingOf(papers);
    const entry = await loadToday(papers.profile_id, binding, new Date());
    await dropStaleFeed(papers.profile_id, binding, new Date());
    setCard(await loadCard(papers.profile_id, binding));
    setHeld(await waiting(papers.profile_id, binding, new Date()));
    if (entry) {
      setKept(entry);
      show(entry.model);
      posture.value = entry.model.posture;
    }
    try {
      await replayHeld();
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

  // The network is back: the held taps go, then the page is read again.
  useEffect(() => {
    const back = () => void load();
    window.addEventListener("online", back);
    return () => window.removeEventListener("online", back);
  }, [bearer, papers?.profile_id, language.value]);

  useEffect(() => {
    setVisitsReady(false);
    // No `visits` scope: there is nothing to wait for — ready at once, not stuck forever.
    if (!bearer || !papers || !papers.scopes.includes("visits")) {
      setVisits([]);
      setVisitsReady(true);
      return;
    }
    nura.appointments(bearer, papers.profile_id).then(
      (got) => {
        setVisits(got);
        setVisitsReady(true);
      },
      () => {
        setVisits([]);
        setVisitsReady(true);
      },
    );
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
    // The tap's moment goes with it, and the held copy keeps the same one: a tap the backend
    // wrote whose answer the phone never got is sent again as the same tap, and written once.
    const at = new Date().toISOString();
    try {
      await tapTaken(bearer, papers.profile_id, lineId, anchor, at);
      setJustTook(tookLine(new Date().getHours(), s));
      await refresh();
    } catch (failure) {
      const kind = readFailure(failure);
      if (kind === "refused") await forget(papers.profile_id, failure);
      else if (kind === "network") {
        // No network: the tap is held on the phone with the moment he made it, and sent once
        // when the network is back. The dose shows as held, in place of Taken.
        if (failure instanceof Unreachable) {
          const tap: Tap = { id: tapId(), kind: "taken", lineId, anchor, at };
          setHeld((await hold(papers.profile_id, tap, bindingOf(papers), new Date(), zoneOf(papers.region))) ?? []);
        }
        setUnreached("network");
      } else setError(failure); // the tap did not land; the page stays, and he is told
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
  // A dose he tapped with no network is held on the phone: it shows as its own card, with when
  // he tapped, and the Now card is the next dose the backend marks due.
  const heldTapOf = (slot: SlotOut) => held.find((tap) => tap.kind === "taken" && tap.lineId === slot.line_id && tap.anchor === slot.anchor);
  const heldSlots = page && !fromPhone && !stale ? page.slots.filter((slot) => heldTapOf(slot) !== undefined) : [];
  const dose = page && !fromPhone && !stale ? nowCard(page.slots.filter((slot) => heldTapOf(slot) === undefined), page.lines, s) : null;
  const nextVisit = visits[0] ?? null;

  return {
    s,
    bearer,
    papers,
    page,
    kept,
    unreached,
    error,
    justTook,
    busy,
    take,
    fromPhone,
    blank,
    feed,
    act,
    stale,
    useFeed,
    top,
    stateAt,
    doseSource,
    dose,
    nextVisit,
    visitsReady,
    now,
    held,
    sent,
    heldRefused,
    card,
    heldSlots,
    heldTapOf,
  };
}

export type TodayView = ReturnType<typeof useToday>;
