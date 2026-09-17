import { useEffect, useState } from "preact/hooks";
import type { JSX } from "preact";
import * as nura from "../api/nura";
import type { AreaOut, MeSummaryOut, SearchJobOut, SignalFamily, SignalsOut } from "../api/types";
import { closeMe, go, meOpen, reloadDoors, signOutEverywhere } from "../flow";
import { emergencyOnly } from "../offline/emergencyCache";
import { wantsHomeScreenHint } from "../offline/register";
import { startOnboarding } from "../onboarding/state";
import { backendFor, browserEnv, remindersState, turnOff, turnOn, type RemindersState } from "../push/reminders";
import { pushKey } from "../store/deployment";
import { density, densityChosen, me, profile, setDensity, setLanguage, token } from "../store/session";
import { fill, LANGUAGES, language, t, type Language } from "../strings";
import { proudLine } from "../today/model";
import { todayPage } from "../today/page";
import { Hear, Notice, Pill, Tile } from "../ui/components";
import { Sheet } from "../ui/kit";
import { Shell } from "./Shell";

/** Me (D1): a sheet from the header's avatar, over whatever screen is open — never a tab. Who
 *  is signed in; the number that only goes up; the language; how Nura looks; his family (the
 *  chief has Family as a tab); whose papers; setting up; reminders on this phone; sign out.
 *  Everything that was on the Me tab is here, one tap from any screen. */
export function MeSheet(): JSX.Element | null {
  const s = t();
  const open = meOpen.value;
  // Escape closes it; opening it puts the screen reader on its title.
  useEffect(() => {
    if (!open) return;
    const onKey = (event: KeyboardEvent) => {
      if (event.key === "Escape") closeMe();
    };
    document.addEventListener("keydown", onKey);
    document.getElementById("sheet-title")?.focus();
    return () => document.removeEventListener("keydown", onKey);
  }, [open]);
  return (
    <Sheet title={s.me.title} open={open} onClose={closeMe} closeLabel={s.shell.close} testId="me-sheet">
      <MeBody open={open} />
    </Sheet>
  );
}

/** The Profile tab (docs/design-direction.md): everything the Me sheet holds, as the tab's own
 *  screen — the same parts, so the two can never say different things. */
export function ProfileScreen(): JSX.Element {
  const s = t();
  return (
    <Shell tab="profile" testId="profile-screen">
      <h1 class="title place-title">{s.me.title}</h1>
      <MeBody open />
    </Shell>
  );
}

/** What Me holds, wherever it is drawn. `open`: whether it is on screen, so its reads wait. */
function MeBody({ open }: { open: boolean }): JSX.Element {
  const s = t();
  // A key to the emergency card alone: nothing here opens more of the papers than that.
  const only = profile.value ? emergencyOnly(profile.value) : false;
  const names: Record<Language, string> = { en: s.me.en, ms: s.me.ms, zh: s.me.zh };
  const bearer = token.value;
  const papers = profile.value;
  const patient = density() === "patient";
  // The number that only goes up (E17-04), on his own Me, in the backend's words.
  // "failed": the summary could not be read (offline) — then the count Today read stands in.
  const [summary, setSummary] = useState<MeSummaryOut | "failed" | null>(null);
  const owner = papers?.standing === "owner";
  useEffect(() => {
    if (!open || !bearer || !papers || !owner) return setSummary(null);
    nura.meSummary(bearer, papers.profile_id, language.value).then(setSummary, () => setSummary("failed"));
  }, [open, bearer, papers?.profile_id, language.value]);
  const said = summary !== null && summary !== "failed" ? summary : null;
  // His own count waits for his own words; anyone else's view, or his offline, is Today's.
  // Today's page stands in only for the papers it was read from: never another profile's count.
  const page = todayPage.value !== null && todayPage.value.profileId === papers?.profile_id ? todayPage.value.model : null;
  const standIn = page !== null && (!owner || summary === "failed");
  // Anyone else's view of the count, or his own when the summary cannot be read (offline):
  // the number Today read, never one counted here.
  const counted = page?.proud ?? null;
  const counts = proudLine(counted, s);
  return (
    <>
      {said ? (
        <Tile paper testId="me-proud">
          <div class="number" data-testid="me-proud-number">
            {said.proud_days}
          </div>
          <div class="lines" data-testid="me-proud-lines">
            {said.lines.map((line, at) => (
              <p key={at}>{line}</p>
            ))}
          </div>
          <p class="provenance">{s.today.fromDays}</p>
          <Hear lines={said.lines} />
        </Tile>
      ) : (
        standIn && (
          <Tile paper testId="proud">
            <div class="number" data-testid="proud-number">
              {counted ?? 0}
            </div>
            <p>{counts}</p>
            <p class="caption">{s.today.proudSub}</p>
            <p class="provenance">{s.today.fromDays}</p>
            <Hear lines={[counts, s.today.proudSub]} />
          </Tile>
        )
      )}
      <Tile paper>
        <p>{fill(s.me.signedInAs, { name: me.value?.display_name || "" })}</p>
      </Tile>
      <Tile paper>
        <p class="label">{s.me.language}</p>
        <div class="row" role="group" aria-label={s.me.language}>
          {LANGUAGES.map((code) => (
            <Pill key={code} chosen={language.value === code} onClick={() => void setLanguage(code)} testId={`lang-${code}`}>
              {names[code]}
            </Pill>
          ))}
        </div>
      </Tile>
      <Tile paper>
        <p class="label">{s.me.look}</p>
        <div class="row" role="group" aria-label={s.me.look}>
          <Pill chosen={density() === "patient"} onClick={() => void setDensity("patient")} testId="density-patient">
            {s.me.patient}
          </Pill>
          <Pill chosen={density() === "caregiver"} onClick={() => void setDensity("caregiver")} testId="density-caregiver">
            {s.me.caregiver}
          </Pill>
        </div>
        {densityChosen.value && (
          <Pill quiet onClick={() => void setDensity(null)}>
            {s.me.lookAuto}
          </Pill>
        )}
      </Tile>
      <Tile paper>
        <Pill onClick={() => void reloadDoors()} testId="switch-profile">
          {s.me.switchProfile}
        </Pill>
        {papers && !only && (
          <Pill onClick={() => void startOnboarding(papers)} testId="set-up">
            {s.me.setUp}
          </Pill>
        )}
        {profile.value && (profile.value.standing === "owner" || profile.value.scopes.includes("records")) && (
          <Pill onClick={() => go({ name: "papers" })} testId="open-papers">
            {s.papers.open}
          </Pill>
        )}
      </Tile>
      <Area />
      <WhatNuraUses />
      <Ramadan />
      <Reminders />
      {papers && (papers.standing === "owner" || papers.scopes.includes("emergency")) && (
        <Tile paper>
          <Pill
            onClick={() => {
              closeMe();
              go({ name: "emergency" });
            }}
            testId="me-emergency"
          >
            {s.today.emergencyTitle}
          </Pill>
        </Tile>
      )}
      {wantsHomeScreenHint() && (
        <Tile glass>
          <p>{s.today.homeScreen1}</p>
          <p>{s.today.homeScreen2}</p>
          <p>{s.today.homeScreen3}</p>
        </Tile>
      )}
      <Tile paper>
        <Pill onClick={() => void signOutEverywhere()} testId="sign-out">
          {s.me.signOut}
        </Pill>
      </Tile>
    </>
  );
}

/** "Get reminders on this phone" (Web Push, ADR 0001): only where this deployment has Web Push
 *  and this browser can take it. Nothing is asked of the phone until the button is tapped. */
function Reminders(): JSX.Element | null {
  const s = t();
  const env = browserEnv();
  const [state, setState] = useState<RemindersState>("unsupported");
  const [busy, setBusy] = useState(false);
  useEffect(() => {
    void remindersState(env).then(setState);
  }, []);
  const key = pushKey.value;
  const bearer = token.value;
  const profileId = profile.value?.profile_id;
  if (!key || !env || !bearer || !profileId || state === "unsupported") return null;
  const tap = async (on: boolean) => {
    setBusy(true);
    try {
      const backend = backendFor(bearer, profileId);
      setState(on ? await turnOn(env, key, backend) : await turnOff(env, backend));
    } catch {
      setState(await remindersState(env));
    } finally {
      setBusy(false);
    }
  };
  return (
    <Tile paper>
      {state === "on" && <p data-testid="reminders-on">{s.me.remindersOn}</p>}
      {state === "denied" && (
        <div data-testid="reminders-denied">
          <p>{s.me.remindersDenied1}</p>
          <p>{s.me.remindersDenied2}</p>
        </div>
      )}
      {state === "on" ? (
        <Pill onClick={() => void tap(false)} disabled={busy} testId="reminders-stop">
          {s.me.remindersStop}
        </Pill>
      ) : (
        state === "off" && (
          <Pill plum onClick={() => void tap(true)} disabled={busy} testId="reminders-get">
            {s.me.remindersGet}
          </Pill>
        )
      )}
    </Tile>
  );
}

/** Where he lives (E09-07), coarsely: a town from the region's list, set on his own yes — the
 *  town is asked back ("Do you live in Air Itam?") before it is kept. Nura uses it only to
 *  match a dengue or haze bulletin near him, on its own server; it is never sent to a search.
 *  His own key, or the steward's who holds his papers until he claims them, sets it; the chief
 *  who looks after his papers can read it (why a local card came), and this screen says so
 *  before he says yes. */
function Area(): JSX.Element | null {
  const s = t();
  const bearer = token.value;
  const papers = profile.value;
  const [view, setView] = useState<AreaOut | null>(null);
  const [choosing, setChoosing] = useState(false);
  const [asking, setAsking] = useState<string | null>(null);
  const [error, setError] = useState<unknown>(null);
  const [busy, setBusy] = useState(false);
  const mine = papers?.standing === "owner" || papers?.standing === "steward";
  useEffect(() => {
    if (!bearer || !papers || !mine) return setView(null);
    nura.area(bearer, papers.profile_id).then(setView, () => setView(null));
  }, [bearer, papers?.profile_id]);
  if (!bearer || !papers || !view || !view.may_set) return null;
  const keep = async (value: string | null) => {
    setBusy(true);
    setError(null);
    try {
      setView(await nura.setArea(bearer, papers.profile_id, value));
      setAsking(null);
      setChoosing(false);
    } catch (failure) {
      setError(failure);
    } finally {
      setBusy(false);
    }
  };
  return (
    <Tile paper testId="area">
      <h2 class="title">{s.me.areaTitle}</h2>
      <p>{s.me.areaLead}</p>
      <p>{s.me.areaWho}</p>
      <p data-testid="area-now">{view.area ? fill(s.me.areaIs, { area: view.area }) : s.me.areaNone}</p>
      {asking ? (
        <>
          <p data-testid="area-ask">{fill(s.me.areaAsk, { area: asking })}</p>
          <Pill plum onClick={() => void keep(asking)} disabled={busy} testId="area-yes">
            {s.me.areaYes}
          </Pill>
          <Pill onClick={() => setAsking(null)} disabled={busy} testId="area-no">
            {s.me.areaNo}
          </Pill>
        </>
      ) : choosing ? (
        <div class="choices" role="group" aria-label={s.me.areaChange}>
          {view.districts.map((district) => (
            <Pill key={district} onClick={() => setAsking(district)} testId="area-choice">
              {district}
            </Pill>
          ))}
        </div>
      ) : (
        <Pill onClick={() => setChoosing(true)} testId="area-change">
          {s.me.areaChange}
        </Pill>
      )}
      {view.area && !asking && !choosing && (
        <Pill quiet onClick={() => void keep(null)} disabled={busy} testId="area-clear">
          {s.me.areaClear}
        </Pill>
      )}
      <Notice error={error} />
    </Tile>
  );
}

const SIGNAL_FAMILIES: SignalFamily[] = ["food", "sleep", "steps", "water", "search_topics"];

/** "What Nura uses" (RE-05, docs/recommendation-engine.md §3.6): food, sleep, steps, water,
 *  what he asks — each a switch. Everyone who can open this profile reads them; only he or
 *  his chief may flip one (`SignalsOut.may_set`), so a caregiver's view shows them read-only
 *  and, through `t()`, says whose switches they are ("{patient}'s sleep"). Search-topic use
 *  starts off (owner decision D3): every other family starts on. */
function WhatNuraUses(): JSX.Element | null {
  const s = t();
  const bearer = token.value;
  const papers = profile.value;
  const [view, setView] = useState<SignalsOut | null>(null);
  const [error, setError] = useState<unknown>(null);
  const [busy, setBusy] = useState<SignalFamily | null>(null);
  useEffect(() => {
    if (!bearer || !papers) return setView(null);
    nura.signals(bearer, papers.profile_id).then(setView, () => setView(null));
  }, [bearer, papers?.profile_id]);
  if (!bearer || !papers || !view) return null;
  const flip = async (family: SignalFamily, on: boolean) => {
    setBusy(family);
    setError(null);
    try {
      setView(await nura.setSignal(bearer, papers.profile_id, family, on));
    } catch (failure) {
      setError(failure);
    } finally {
      setBusy(null);
    }
  };
  return (
    <Tile paper testId="what-nura-uses">
      <h2 class="title">{s.me.whatNuraUsesTitle}</h2>
      <p>{s.me.whatNuraUsesLead}</p>
      {!view.may_set && <p>{fill(s.me.whatNuraUsesReadOnly, { name: papers.display_name })}</p>}
      {SIGNAL_FAMILIES.map((family) => {
        const row = view.signals.find((one) => one.family === family);
        const on = row?.on ?? false;
        return (
          <div key={family}>
            <p class="label">{s.me.whatNuraUsesFamilies[family]}</p>
            <div class="row" role="group" aria-label={s.me.whatNuraUsesFamilies[family]}>
              {view.may_set ? (
                <Pill
                  chosen={on}
                  onClick={() => void flip(family, !on)}
                  disabled={busy !== null}
                  testId={`signal-${family}`}
                >
                  {on ? s.me.whatNuraUsesOn : s.me.whatNuraUsesOff}
                </Pill>
              ) : (
                <span data-testid={`signal-${family}`}>{on ? s.me.whatNuraUsesOn : s.me.whatNuraUsesOff}</span>
              )}
            </div>
          </div>
        );
      })}
      <Notice error={error} />
    </Tile>
  );
}

/** Ramadan (docs/health-feed-spec.md §2, seasonal): whether he fasts speaks of his faith, so
 *  it is his to say — on his own key, or the steward's who holds his papers — and Nura never
 *  guesses it from a name or a language. On his yes a weekly watch is added; two months before
 *  Ramadan it brings the card (plan it with the doctor, what to eat, what to do if shaky and
 *  sweaty). The screen says, before he says yes, that his chief will see it too. */
function Ramadan(): JSX.Element | null {
  const s = t();
  const bearer = token.value;
  const papers = profile.value;
  const [job, setJob] = useState<SearchJobOut | null | undefined>(undefined);
  const [error, setError] = useState<unknown>(null);
  const [busy, setBusy] = useState(false);
  const mine = papers?.standing === "owner" || papers?.standing === "steward";
  const find = (jobs: SearchJobOut[]) => jobs.find((one) => one.kind === "seasonal" && one.terms.includes("fasting month")) ?? null;
  useEffect(() => {
    if (!bearer || !papers || !mine) return setJob(undefined);
    nura.searchJobs(bearer, papers.profile_id, language.value).then((jobs) => setJob(find(jobs)), () => setJob(undefined));
  }, [bearer, papers?.profile_id]);
  if (!bearer || !papers || job === undefined) return null;
  const on = job !== null && job.enabled;
  const choose = async (yes: boolean) => {
    setBusy(true);
    setError(null);
    try {
      if (job) setJob(await nura.pauseSearchJob(bearer, papers.profile_id, job.job_id, yes, language.value));
      else if (yes) setJob(await nura.addSearchJob(bearer, papers.profile_id, "seasonal", ["fasting month"]));
    } catch (failure) {
      setError(failure);
    } finally {
      setBusy(false);
    }
  };
  return (
    <Tile paper testId="ramadan">
      <h2 class="title">{s.me.ramadanTitle}</h2>
      <p>{s.me.ramadanLead}</p>
      <p>{s.me.ramadanWho}</p>
      {on ? (
        <>
          <p data-testid="ramadan-on">{s.me.ramadanOn}</p>
          <Pill quiet onClick={() => void choose(false)} disabled={busy} testId="ramadan-stop">
            {s.me.ramadanStop}
          </Pill>
        </>
      ) : (
        <Pill plum onClick={() => void choose(true)} disabled={busy} testId="ramadan-yes">
          {s.me.ramadanYes}
        </Pill>
      )}
      <Notice error={error} />
    </Tile>
  );
}
