import { useEffect, useState } from "preact/hooks";
import type { JSX } from "preact";
import * as nura from "../api/nura";
import type { AreaOut, MeSummaryOut } from "../api/types";
import { go, openTab, reloadDoors, signOutEverywhere } from "../flow";
import { wantsHomeScreenHint } from "../offline/register";
import { startOnboarding } from "../onboarding/state";
import { backendFor, browserEnv, remindersState, turnOff, turnOn, type RemindersState } from "../push/reminders";
import { pushKey } from "../store/deployment";
import { density, densityChosen, me, profile, setDensity, setLanguage, token } from "../store/session";
import { fill, LANGUAGES, language, t, type Language } from "../strings";
import { Header, Hear, Notice, Pill, TabBar, Tile } from "../ui/components";

/** Me: who is signed in, the language, how Nura looks, whose papers, sign out. */
export function MeScreen(): JSX.Element {
  const s = t();
  const names: Record<Language, string> = { en: s.me.en, ms: s.me.ms, zh: s.me.zh };
  const bearer = token.value;
  const papers = profile.value;
  // The number that only goes up (E17-04), on his own Me page, in the backend's words.
  const [proud, setProud] = useState<MeSummaryOut | null>(null);
  useEffect(() => {
    if (!bearer || !papers || papers.standing !== "owner") return setProud(null);
    nura.meSummary(bearer, papers.profile_id, language.value).then(setProud, () => setProud(null));
  }, [bearer, papers?.profile_id, language.value]);
  return (
    <main class="screen">
      <Header title={s.me.title} />
      {proud && (
        <Tile paper testId="me-proud">
          <div class="number" data-testid="me-proud-number">
            {proud.proud_days}
          </div>
          <div class="lines" data-testid="me-proud-lines">
            {proud.lines.map((line, at) => (
              <p key={at}>{line}</p>
            ))}
          </div>
          <p class="provenance">{s.today.fromDays}</p>
          <Hear lines={proud.lines} />
        </Tile>
      )}
      <Tile paper>
        <p>{fill(s.me.signedInAs, { name: me.value?.display_name || "" })}</p>
      </Tile>
      <Tile paper>
        <p class="label">{s.me.language}</p>
        <div class="row" role="group" aria-label={s.me.language}>
          {LANGUAGES.map((code) => (
            <Pill key={code} plum={language.value === code} onClick={() => void setLanguage(code)} testId={`lang-${code}`}>
              {names[code]}
            </Pill>
          ))}
        </div>
      </Tile>
      <Tile paper>
        <p class="label">{s.me.look}</p>
        <div class="row" role="group" aria-label={s.me.look}>
          <Pill plum={density() === "patient"} onClick={() => void setDensity("patient")} testId="density-patient">
            {s.me.patient}
          </Pill>
          <Pill plum={density() === "caregiver"} onClick={() => void setDensity("caregiver")} testId="density-caregiver">
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
        {profile.value && (
          <Pill onClick={() => void startOnboarding(profile.value!)} testId="set-up">
            {s.me.setUp}
          </Pill>
        )}
      </Tile>
      <Area />
      <Reminders />
      {wantsHomeScreenHint() && (
        <Tile glass>
          <p>{s.today.homeScreen1}</p>
          <p>{s.today.homeScreen2}</p>
        </Tile>
      )}
      <Tile paper>
        <Pill onClick={() => void signOutEverywhere()} testId="sign-out">
          {s.me.signOut}
        </Pill>
      </Tile>
      <TabBar current="me" onSelect={openTab} />
    </main>
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
 *  His own key, or the steward's who holds his papers until he claims them; nobody else sees
 *  this part. */
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
