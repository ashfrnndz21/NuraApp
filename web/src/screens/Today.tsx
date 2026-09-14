import { useEffect, useState } from "preact/hooks";
import type { JSX } from "preact";
import { Refused, Unreachable } from "../api/client";
import * as nura from "../api/nura";
import { go } from "../flow";
import { loadProudFloor, loadTakenDays, loadToday, rememberTakenDay, saveProudFloor, saveToday } from "../offline/todayCache";
import { wantsHomeScreenHint } from "../offline/register";
import { density, me, posture, profile, token } from "../store/session";
import { fill, language, LOCALE, t } from "../strings";
import { dateLine, dayKey, greeting, nextDose, stateLines, supplyLines, tookLine, type TodayModel } from "../today/model";
import { daysFromAudit, proudNumber } from "../today/proud";
import { Card, Hear, Notice, Pill, TabBar, Tile } from "../ui/components";

/** Today: the Now card, a reading prompt, two cards from State and the medicines, and the
 *  proud number. Vertical, one action per card, every card with its spoken twin. It opens
 *  on the last page kept on the phone and then, if the network is there, the fresh one. */
export function TodayScreen({ saved }: { saved?: boolean }): JSX.Element {
  const s = t();
  const bearer = token.value;
  const papers = profile.value;
  const [model, setModel] = useState<TodayModel | null>(null);
  const [offline, setOffline] = useState(false);
  const [error, setError] = useState<unknown>(null);
  const [proud, setProud] = useState<number | null>(null);
  const [justTook, setJustTook] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const load = async () => {
    if (!bearer || !papers) return;
    const cached = await loadToday(papers.profile_id);
    if (cached) {
      setModel(cached);
      posture.value = cached.posture;
    }
    const floor = await loadProudFloor(papers.profile_id);
    const local = await loadTakenDays(papers.profile_id);
    setProud(proudNumber(local, floor));
    try {
      const [state, lines, slots] = await Promise.all([
        nura.state(bearer, papers.profile_id).catch((failure: unknown) => {
          // A key without the record cannot read State; the wash stays where it was.
          if (failure instanceof Refused) return null;
          throw failure;
        }),
        nura.medicines(bearer, papers.profile_id, language.value),
        nura.dosesToday(bearer, papers.profile_id, language.value),
      ]);
      const fresh: TodayModel = {
        posture: state?.posture ?? cached?.posture ?? "stable",
        lines,
        slots,
        fetchedAt: new Date().toISOString(),
      };
      setModel(fresh);
      posture.value = fresh.posture;
      setOffline(false);
      await saveToday(papers.profile_id, fresh);
      try {
        const trail = await nura.medicinesAudit(bearer, papers.profile_id);
        const days = [...daysFromAudit(trail, (iso) => dayKey(new Date(iso))), ...local];
        const number = proudNumber(days, floor);
        setProud(number);
        await saveProudFloor(papers.profile_id, number);
      } catch {
        /* a key that cannot read the trail keeps the phone's own count */
      }
    } catch (failure) {
      if (failure instanceof Unreachable) setOffline(true);
      else setError(failure);
    }
  };

  useEffect(() => {
    void load();
  }, [bearer, papers?.profile_id, language.value]);

  const take = async (lineId: string, anchor: string) => {
    if (!bearer || !papers || busy) return;
    setBusy(true);
    setError(null);
    try {
      await nura.taken(bearer, papers.profile_id, lineId, anchor);
      const today = dayKey(new Date());
      const days = await rememberTakenDay(papers.profile_id, today);
      const floor = await loadProudFloor(papers.profile_id);
      const number = proudNumber(days, Math.max(floor, proud ?? 0));
      setProud(number);
      await saveProudFloor(papers.profile_id, number);
      setJustTook(tookLine(new Date().getHours(), s));
      // The next card, and the count that came down by one.
      const lines = await nura.medicines(bearer, papers.profile_id, language.value);
      const slots = await nura.dosesToday(bearer, papers.profile_id, language.value);
      if (model) {
        const fresh = { ...model, lines, slots, fetchedAt: new Date().toISOString() };
        setModel(fresh);
        await saveToday(papers.profile_id, fresh);
      }
    } catch (failure) {
      if (failure instanceof Unreachable) setOffline(true);
      else setError(failure);
    } finally {
      setBusy(false);
    }
  };

  const now = new Date();
  const name = papers?.display_name || me.value?.display_name || "";
  const hello = greeting(now.getHours(), name, s);
  const today = dateLine(now, LOCALE[language.value]);
  const nowCard = model ? nextDose(model.slots, model.lines) : null;
  const supply = model ? supplyLines(model.lines) : null;
  const proudLine =
    proud === null || proud === 0 ? s.today.proudNone : proud === 1 ? s.today.proudOne : fill(s.today.proud, { count: proud });

  return (
    <main class="screen" data-density={density()}>
      <header class="hero">
        <div class="greeting">{hello}</div>
        <div class="date">{today}</div>
      </header>

      {offline && (
        <Tile glass testId="offline">
          <p>{s.today.offline}</p>
          <p class="caption">{s.today.offlineSub}</p>
        </Tile>
      )}
      {saved && (
        <Tile paper>
          <p>{s.reading.saved}</p>
        </Tile>
      )}
      <Notice error={error} />

      <h2 class="section">{s.today.now}</h2>
      {nowCard?.kind === "dose" && (
        <Card
          title={nowCard.title}
          lines={[nowCard.sentence]}
          testId="now-card"
          action={
            <Pill plum onClick={() => take(nowCard.lineId, nowCard.anchor)} disabled={busy} testId="taken">
              {s.today.taken}
            </Pill>
          }
        />
      )}
      {nowCard?.kind === "allTaken" && (
        <Card title={s.today.allTaken} lines={[justTook ?? s.today.allTakenSub]} settled testId="all-taken" />
      )}
      {nowCard?.kind === "none" && <Card title={s.today.noMedicines} lines={[s.today.noMedicinesSub]} testId="no-medicines" />}
      {nowCard?.kind === "dose" && justTook && (
        <Tile paper settled>
          <p>{justTook}</p>
        </Tile>
      )}

      <Card
        title={s.today.readingTitle}
        lines={[s.today.readingLead]}
        testId="reading-prompt"
        action={
          <Pill onClick={() => go({ name: "reading" })} testId="write-reading">
            {s.today.readingButton}
          </Pill>
        }
      />

      <h2 class="section">{s.today.forYou}</h2>
      {model && <Card lines={stateLines(model.posture, s)} paper={density() === "patient"} testId="state-card" />}
      {supply && <Card title={s.today.supplyTitle} lines={supply} paper={density() === "patient"} testId="supply-card" />}

      <Tile paper testId="proud">
        <div class="number" data-testid="proud-number">{proud ?? 0}</div>
        <p>{proudLine}</p>
        <p class="caption">{s.today.proudSub}</p>
        <Hear lines={[proudLine, s.today.proudSub]} />
      </Tile>

      {wantsHomeScreenHint() && (
        <Tile glass>
          <p>{s.today.homeScreen1}</p>
          <p>{s.today.homeScreen2}</p>
        </Tile>
      )}

      <TabBar current="today" onSelect={(tab) => go(tab === "me" ? { name: "me" } : { name: "today" })} />
    </main>
  );
}
